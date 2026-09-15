import asyncio
from typing import Any
from uuid import uuid4

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from duragen.activities import (
    export_report,
    generate_diagnosis,
    plan_remediation,
    retrieve_evidence,
    retry_pipeline,
)
from duragen.models import (
    ApprovalDecision,
    ApprovalSignal,
    CheckType,
    InvestigationInput,
    InvestigationState,
    InvestigationStatus,
    QualityCheckFailure,
)
from duragen.workflows import InvestigationWorkflow

ACTIVITIES = [
    retrieve_evidence,
    generate_diagnosis,
    plan_remediation,
    retry_pipeline,
    export_report,
]


def investigation_input(investigation_id: str) -> InvestigationInput:
    return InvestigationInput(
        investigation_id=investigation_id,
        failure=QualityCheckFailure(
            quality_check_id=f"check-{investigation_id}",
            check_type=CheckType.FRESHNESS,
            dataset="orders",
            observed_value="120 minutes",
            expected_value="under 30 minutes",
            message="Orders data is stale.",
        ),
    )


async def wait_for_status(
    handle: Any,
    expected: InvestigationStatus,
) -> InvestigationState:
    async with asyncio.timeout(10):
        while True:
            state = await handle.query(InvestigationWorkflow.state)
            if state is not None and state.status is expected:
                return state
            await asyncio.sleep(0.01)


async def test_investigation_approval_and_rejection_paths() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        task_queue = f"investigation-tests-{uuid4()}"
        async with Worker(
            environment.client,
            task_queue=task_queue,
            workflows=[InvestigationWorkflow],
            activities=ACTIVITIES,
        ):
            approved_input = investigation_input("inv-approved")
            approved_handle = await environment.client.start_workflow(
                InvestigationWorkflow.run,
                approved_input,
                id=f"investigation/{approved_input.failure.quality_check_id}",
                task_queue=task_queue,
            )
            awaiting = await wait_for_status(
                approved_handle,
                InvestigationStatus.AWAITING_APPROVAL,
            )

            assert awaiting.retry is None
            assert awaiting.evidence is not None
            assert awaiting.diagnosis is not None
            assert awaiting.impact is not None
            assert awaiting.remediation is not None
            evidence_ids = {item.evidence_id for item in awaiting.evidence.items}
            assert all(
                set(hypothesis.evidence_ids) <= evidence_ids
                for hypothesis in awaiting.diagnosis.hypotheses
            )
            assert all(
                set(dataset.evidence_ids) <= evidence_ids
                for dataset in awaiting.impact.affected_datasets
            )

            await approved_handle.signal(
                InvestigationWorkflow.submit_approval,
                ApprovalSignal(
                    investigation_id="inv-approved",
                    plan_version="stale",
                    decision=ApprovalDecision.APPROVE,
                    approver="reviewer",
                ),
            )
            approval = ApprovalSignal(
                investigation_id="inv-approved",
                plan_version="v1",
                decision=ApprovalDecision.APPROVE,
                approver="reviewer",
            )
            await approved_handle.signal(InvestigationWorkflow.submit_approval, approval)
            await approved_handle.signal(InvestigationWorkflow.submit_approval, approval)
            await approved_handle.signal(
                InvestigationWorkflow.submit_approval,
                ApprovalSignal(
                    investigation_id="inv-approved",
                    plan_version="v1",
                    decision=ApprovalDecision.REJECT,
                    approver="reviewer",
                ),
            )

            approved = await approved_handle.result()

            assert approved.status is InvestigationStatus.COMPLETED
            assert approved.retry is not None
            assert approved.report is not None
            assert approved.approval is not None
            assert approved.approval.decision is ApprovalDecision.APPROVE
            assert approved.rejected_approval_signals == [
                "plan version is stale",
                "a different approval decision was already accepted",
            ]

            rejected_input = investigation_input("inv-rejected")
            rejected_handle = await environment.client.start_workflow(
                InvestigationWorkflow.run,
                rejected_input,
                id=f"investigation/{rejected_input.failure.quality_check_id}",
                task_queue=task_queue,
            )
            await wait_for_status(rejected_handle, InvestigationStatus.AWAITING_APPROVAL)
            await rejected_handle.signal(
                InvestigationWorkflow.submit_approval,
                ApprovalSignal(
                    investigation_id="inv-rejected",
                    plan_version="v1",
                    decision=ApprovalDecision.REJECT,
                    approver="reviewer",
                    comment="Resolve the upstream issue first.",
                ),
            )

            rejected = await rejected_handle.result()

            assert rejected.status is InvestigationStatus.COMPLETED
            assert rejected.retry is None
            assert rejected.report is not None
            assert rejected.approval is not None
            assert rejected.approval.decision is ApprovalDecision.REJECT
            assert rejected.report.summary.endswith("reject.")