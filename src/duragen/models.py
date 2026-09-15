from dataclasses import dataclass, field
from enum import StrEnum


class CheckType(StrEnum):
    FRESHNESS = "freshness"
    SCHEMA = "schema"
    VOLUME = "volume"
    NULL_RATE = "null_rate"


class InvestigationStatus(StrEnum):
    RECEIVED = "received"
    EVIDENCE_COLLECTED = "evidence_collected"
    DIAGNOSED = "diagnosed"
    IMPACT_ASSESSED = "impact_assessed"
    REMEDIATION_PLANNED = "remediation_planned"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETRY_COMPLETED = "retry_completed"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"


@dataclass(frozen=True)
class QualityCheckFailure:
    quality_check_id: str
    check_type: CheckType
    dataset: str
    observed_value: str
    expected_value: str
    message: str


@dataclass(frozen=True)
class InvestigationInput:
    investigation_id: str
    failure: QualityCheckFailure
    attempt: int = 1


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source: str
    summary: str


@dataclass(frozen=True)
class EvidenceBundle:
    items: list[Evidence]
    downstream_datasets: list[str]


@dataclass(frozen=True)
class Hypothesis:
    summary: str
    confidence: float
    evidence_ids: list[str]


@dataclass(frozen=True)
class Diagnosis:
    hypotheses: list[Hypothesis]
    confidence: float


@dataclass(frozen=True)
class AffectedDataset:
    dataset: str
    severity: str
    evidence_ids: list[str]


@dataclass(frozen=True)
class ImpactAssessment:
    affected_datasets: list[AffectedDataset]


@dataclass(frozen=True)
class RemediationAction:
    description: str
    evidence_ids: list[str]


@dataclass(frozen=True)
class RemediationPlan:
    version: str
    actions: list[RemediationAction]
    risks: list[str]
    expected_result: str


@dataclass(frozen=True)
class ApprovalRequest:
    plan_version: str
    reasons: list[str]


@dataclass(frozen=True)
class ApprovalSignal:
    investigation_id: str
    plan_version: str
    decision: ApprovalDecision
    approver: str
    comment: str | None = None


@dataclass(frozen=True)
class ApprovalRecord:
    decision: ApprovalDecision
    approver: str
    decided_at: str
    comment: str | None = None


@dataclass(frozen=True)
class PipelineRetryResult:
    operation_id: str
    outcome: str


@dataclass(frozen=True)
class ReportResult:
    location: str
    summary: str


@dataclass(frozen=True)
class FailureDetails:
    failure_class: str
    failed_stage: str
    attempts: int
    diagnostic_reference: str


@dataclass
class InvestigationState:
    investigation_id: str
    failure: QualityCheckFailure
    status: InvestigationStatus = InvestigationStatus.RECEIVED
    evidence: EvidenceBundle | None = None
    diagnosis: Diagnosis | None = None
    impact: ImpactAssessment | None = None
    remediation: RemediationPlan | None = None
    approval_request: ApprovalRequest | None = None
    approval: ApprovalRecord | None = None
    retry: PipelineRetryResult | None = None
    report: ReportResult | None = None
    failure_details: FailureDetails | None = None
    rejected_approval_signals: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceRequest:
    investigation_id: str
    failure: QualityCheckFailure


@dataclass(frozen=True)
class DiagnosisRequest:
    investigation_id: str
    evidence: EvidenceBundle
    idempotency_key: str


@dataclass(frozen=True)
class RemediationRequest:
    investigation_id: str
    diagnosis: Diagnosis
    impact: ImpactAssessment
    idempotency_key: str


@dataclass(frozen=True)
class PipelineRetryRequest:
    investigation_id: str
    quality_check_id: str
    plan: RemediationPlan
    idempotency_key: str


@dataclass(frozen=True)
class ReportRequest:
    state: InvestigationState
    idempotency_key: str