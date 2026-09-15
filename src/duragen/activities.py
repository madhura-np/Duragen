from temporalio import activity

from duragen.models import (
    Diagnosis,
    DiagnosisRequest,
    Evidence,
    EvidenceBundle,
    EvidenceRequest,
    Hypothesis,
    PipelineRetryRequest,
    PipelineRetryResult,
    RemediationAction,
    RemediationPlan,
    RemediationRequest,
    ReportRequest,
    ReportResult,
)


@activity.defn
async def verify_environment(name: str) -> str:
    return f"Duragen environment ready for {name}"


@activity.defn
async def retrieve_evidence(request: EvidenceRequest) -> EvidenceBundle:
    dataset = request.failure.dataset
    check_id = request.failure.quality_check_id
    return EvidenceBundle(
        items=[
            Evidence(
                evidence_id=f"metadata:{check_id}",
                source="metadata",
                summary=f"{dataset} failed its {request.failure.check_type.value} check.",
            ),
            Evidence(
                evidence_id=f"lineage:{check_id}",
                source="lineage",
                summary=f"Lineage for {dataset} includes curated and reporting datasets.",
            ),
            Evidence(
                evidence_id=f"change:{check_id}",
                source="recent_changes",
                summary=f"Recent pipeline changes associated with {dataset} were retrieved.",
            ),
            Evidence(
                evidence_id=f"incident:{check_id}",
                source="prior_incidents",
                summary=f"Prior incidents associated with {dataset} were retrieved.",
            ),
        ],
        downstream_datasets=[f"{dataset}_curated", f"{dataset}_reporting"],
    )


@activity.defn
async def generate_diagnosis(request: DiagnosisRequest) -> Diagnosis:
    evidence_ids = [item.evidence_id for item in request.evidence.items]
    return Diagnosis(
        hypotheses=[
            Hypothesis(
                summary="A recent upstream pipeline change is the most likely cause.",
                confidence=0.82,
                evidence_ids=evidence_ids,
            )
        ],
        confidence=0.82,
    )


@activity.defn
async def plan_remediation(request: RemediationRequest) -> RemediationPlan:
    evidence_ids = list(
        dict.fromkeys(
            evidence_id
            for hypothesis in request.diagnosis.hypotheses
            for evidence_id in hypothesis.evidence_ids
        )
    )
    return RemediationPlan(
        version="v1",
        actions=[
            RemediationAction(
                description="Retry the failed pipeline run after validating upstream inputs.",
                evidence_ids=evidence_ids,
            )
        ],
        risks=["The retry can fail again if the upstream condition is unresolved."],
        expected_result="The quality check passes on the retried pipeline output.",
    )


@activity.defn
async def retry_pipeline(request: PipelineRetryRequest) -> PipelineRetryResult:
    return PipelineRetryResult(
        operation_id=f"retry/{request.quality_check_id}/{request.plan.version}",
        outcome="simulated pipeline retry completed",
    )


@activity.defn
async def export_report(request: ReportRequest) -> ReportResult:
    state = request.state
    if state.failure_details is not None:
        summary = f"Investigation failed during {state.failure_details.failed_stage}."
    elif state.retry is not None:
        summary = "Investigation completed with an approved pipeline retry."
    else:
        decision = state.approval.decision.value if state.approval else "unknown"
        summary = f"Investigation completed without a retry: {decision}."
    return ReportResult(
        location=f"reports/{state.investigation_id}.md",
        summary=summary,
    )