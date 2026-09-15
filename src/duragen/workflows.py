from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, RetryState

with workflow.unsafe.imports_passed_through():
    from duragen.activities import (
        export_report,
        generate_diagnosis,
        plan_remediation,
        retrieve_evidence,
        retry_pipeline,
        verify_environment,
    )
    from duragen.models import (
        AffectedDataset,
        ApprovalDecision,
        ApprovalRecord,
        ApprovalRequest,
        ApprovalSignal,
        DiagnosisRequest,
        EvidenceRequest,
        FailureDetails,
        ImpactAssessment,
        InvestigationInput,
        InvestigationState,
        InvestigationStatus,
        PipelineRetryRequest,
        RemediationRequest,
        ReportRequest,
    )


EVIDENCE_RETRY_POLICY = RetryPolicy(maximum_attempts=3)
LLM_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2,
    maximum_interval=timedelta(seconds=15),
    maximum_attempts=3,
)
PIPELINE_RETRY_POLICY = RetryPolicy(maximum_attempts=5)
REPORT_RETRY_POLICY = RetryPolicy(maximum_attempts=3)


@workflow.defn
class EnvironmentSmokeWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        return await workflow.execute_activity(
            verify_environment,
            name,
            start_to_close_timeout=timedelta(seconds=10),
        )


@workflow.defn
class InvestigationWorkflow:
    def __init__(self) -> None:
        self._state: InvestigationState | None = None
        self._decision: ApprovalSignal | None = None

    @workflow.run
    async def run(self, investigation: InvestigationInput) -> InvestigationState:
        self._validate_input(investigation)
        self._state = InvestigationState(
            investigation_id=investigation.investigation_id,
            failure=investigation.failure,
        )

        stage = "retrieve_evidence"
        try:
            self._state.evidence = await workflow.execute_activity(
                retrieve_evidence,
                EvidenceRequest(
                    investigation_id=investigation.investigation_id,
                    failure=investigation.failure,
                ),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=EVIDENCE_RETRY_POLICY,
            )
            self._state.status = InvestigationStatus.EVIDENCE_COLLECTED

            stage = "generate_diagnosis"
            self._state.diagnosis = await workflow.execute_activity(
                generate_diagnosis,
                DiagnosisRequest(
                    investigation_id=investigation.investigation_id,
                    evidence=self._state.evidence,
                    idempotency_key=self._operation_key("generate-diagnosis"),
                ),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=LLM_RETRY_POLICY,
            )
            self._state.status = InvestigationStatus.DIAGNOSED

            self._state.impact = self._assess_impact()
            self._state.status = InvestigationStatus.IMPACT_ASSESSED

            stage = "plan_remediation"
            self._state.remediation = await workflow.execute_activity(
                plan_remediation,
                RemediationRequest(
                    investigation_id=investigation.investigation_id,
                    diagnosis=self._state.diagnosis,
                    impact=self._state.impact,
                    idempotency_key=self._operation_key("plan-remediation"),
                ),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=LLM_RETRY_POLICY,
            )
            self._state.status = InvestigationStatus.REMEDIATION_PLANNED
            self._state.approval_request = self._build_approval_request()
            self._state.status = InvestigationStatus.AWAITING_APPROVAL

            await workflow.wait_condition(lambda: self._decision is not None)
            self._record_decision()

            if self._decision and self._decision.decision is ApprovalDecision.APPROVE:
                self._state.status = InvestigationStatus.APPROVED
                stage = "retry_pipeline"
                self._state.retry = await workflow.execute_activity(
                    retry_pipeline,
                    PipelineRetryRequest(
                        investigation_id=investigation.investigation_id,
                        quality_check_id=investigation.failure.quality_check_id,
                        plan=self._state.remediation,
                        idempotency_key=self._operation_key("retry-pipeline"),
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=PIPELINE_RETRY_POLICY,
                )
                self._state.status = InvestigationStatus.RETRY_COMPLETED
            else:
                self._state.status = InvestigationStatus.REJECTED

            stage = "export_report"
            self._state.report = await workflow.execute_activity(
                export_report,
                ReportRequest(
                    state=self._state,
                    idempotency_key=self._operation_key("export-report"),
                ),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=REPORT_RETRY_POLICY,
            )
            self._state.status = InvestigationStatus.COMPLETED
            return self._state
        except ActivityError as error:
            return await self._record_failure(stage, error)

    @workflow.query
    def state(self) -> InvestigationState | None:
        return self._state

    @workflow.signal
    def submit_approval(self, decision: ApprovalSignal) -> None:
        if self._decision is not None:
            if decision != self._decision:
                self._reject_approval("a different approval decision was already accepted")
            return
        if self._state is None or self._state.status is not InvestigationStatus.AWAITING_APPROVAL:
            self._reject_approval("workflow is not awaiting approval")
            return
        if decision.investigation_id != self._state.investigation_id:
            self._reject_approval("investigation ID does not match")
            return
        if (
            self._state.remediation is None
            or decision.plan_version != self._state.remediation.version
        ):
            self._reject_approval("plan version is stale")
            return
        if not decision.approver.strip():
            self._reject_approval("approver is required")
            return
        self._decision = decision

    @staticmethod
    def _validate_input(investigation: InvestigationInput) -> None:
        required_values = {
            "investigation_id": investigation.investigation_id,
            "quality_check_id": investigation.failure.quality_check_id,
            "dataset": investigation.failure.dataset,
            "observed_value": investigation.failure.observed_value,
            "expected_value": investigation.failure.expected_value,
            "message": investigation.failure.message,
        }
        missing = [name for name, value in required_values.items() if not value.strip()]
        if missing or investigation.attempt < 1:
            reason = (
                f"missing required values: {', '.join(missing)}"
                if missing
                else "attempt must be positive"
            )
            raise ApplicationError(reason, non_retryable=True)

    def _assess_impact(self) -> ImpactAssessment:
        assert self._state is not None
        assert self._state.evidence is not None
        lineage_ids = [
            item.evidence_id for item in self._state.evidence.items if item.source == "lineage"
        ]
        return ImpactAssessment(
            affected_datasets=[
                AffectedDataset(
                    dataset=dataset,
                    severity="high",
                    evidence_ids=lineage_ids,
                )
                for dataset in self._state.evidence.downstream_datasets
            ]
        )

    def _build_approval_request(self) -> ApprovalRequest:
        assert self._state is not None
        assert self._state.diagnosis is not None
        assert self._state.remediation is not None
        reasons = ["Every pipeline retry requires human approval."]
        if self._state.diagnosis.confidence < 0.70:
            reasons.append("Diagnosis confidence is below 0.70.")
        return ApprovalRequest(
            plan_version=self._state.remediation.version,
            reasons=reasons,
        )

    def _record_decision(self) -> None:
        assert self._state is not None
        assert self._decision is not None
        self._state.approval = ApprovalRecord(
            decision=self._decision.decision,
            approver=self._decision.approver,
            decided_at=workflow.now().isoformat(),
            comment=self._decision.comment,
        )

    def _reject_approval(self, reason: str) -> None:
        if self._state is not None:
            self._state.rejected_approval_signals.append(reason)

    def _operation_key(self, operation: str) -> str:
        assert self._state is not None
        return f"{self._state.investigation_id}:{operation}:v1"

    async def _record_failure(
        self,
        stage: str,
        error: ActivityError,
    ) -> InvestigationState:
        assert self._state is not None
        configured_attempts = {
            "retrieve_evidence": 3,
            "generate_diagnosis": 3,
            "plan_remediation": 3,
            "retry_pipeline": 5,
            "export_report": 3,
        }
        attempts = (
            configured_attempts[stage]
            if error.retry_state is RetryState.MAXIMUM_ATTEMPTS_REACHED
            else 1
        )
        self._state.status = InvestigationStatus.FAILED
        self._state.failure_details = FailureDetails(
            failure_class="activity_error",
            failed_stage=stage,
            attempts=attempts,
            diagnostic_reference=f"temporal-activity:{stage}",
        )
        if stage != "export_report":
            self._state.report = await workflow.execute_activity(
                export_report,
                ReportRequest(
                    state=self._state,
                    idempotency_key=self._operation_key("export-report"),
                ),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=REPORT_RETRY_POLICY,
            )
        return self._state