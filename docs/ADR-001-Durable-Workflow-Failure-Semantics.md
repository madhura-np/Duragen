# ADR-001: Durable Workflow and Failure Semantics

- **Status:** Proposed
- **Date:** 2026-09-05
- **Decision owners:** #todo Add owner or reviewer names.
- **Related:** [DurableAgent project one-pager](DurableAgent_Project_OnePager.md)

## Context

DurableAgent demonstrates a long-running AI investigation that must survive worker crashes and transient dependency failures without losing progress or repeating completed side effects. The workflow ingests a failed data-quality check, retrieves evidence, produces a diagnosis and downstream impact assessment, plans remediation, waits for human approval, performs a simulated pipeline retry, and exports a report.

Temporal provides durable workflow history and replay, but activity execution is at least once. A worker can fail after an external operation succeeds but before Temporal records the activity result. Therefore, workflow replay alone cannot guarantee that LLM requests, pipeline retries, or report exports occur only once. These operations need stable identities and application-level duplicate suppression.

This ADR defines the workflow state, durable boundaries, retry behavior, approval protocol, and idempotency rules. It targets exactly-once behavior from the application's perspective, not exactly-once delivery across arbitrary external systems.

## Decision

Use one Temporal workflow execution per investigation. Keep orchestration deterministic in workflow code, and place all I/O, model calls, clock access, trace emission, and side effects in activities. Activities exchange typed inputs and outputs; agent stages do not communicate through free-form conversation or process memory.

### Workflow Identity

- Temporal workflow ID: `investigation/{quality_check_id}`.
- Reject a second active workflow with the same ID.
- Treat a new investigation of the same quality check as a new logical attempt with an explicit attempt suffix or reset policy.
- #todo Choose the rerun identity: `investigation/{quality_check_id}/{attempt}` or a caller-supplied investigation ID.
- Attach the workflow ID and investigation ID to every Langfuse trace, activity log, and idempotency record.

Temporal run IDs are diagnostic metadata only. They must not be part of idempotency keys because a continue-as-new operation or workflow retry can change the run ID while preserving the same logical investigation.

### Persisted State Model

The workflow advances a typed `InvestigationState` through these states:

| State | Persisted output | Next transition |
|---|---|---|
| `RECEIVED` | Validated quality-check failure | Retrieve evidence |
| `EVIDENCE_COLLECTED` | Metadata, lineage, recent changes, prior incidents, citations | Generate diagnosis |
| `DIAGNOSED` | Root-cause hypotheses, confidence, evidence citations | Assess downstream impact |
| `IMPACT_ASSESSED` | Affected datasets and impact evidence | Plan remediation |
| `REMEDIATION_PLANNED` | Proposed actions, risks, expected result | Request approval |
| `AWAITING_APPROVAL` | Approval request and reason | Wait for signal |
| `APPROVED` | Approver, decision time, optional comment | Execute retry |
| `REJECTED` | Approver, decision time, optional comment | Export rejected report |
| `RETRY_COMPLETED` | Pipeline retry operation ID and result | Export report |
| `COMPLETED` | Report location and terminal summary | End |
| `FAILED` | Failure class, failed stage, attempts, and diagnostic reference | End or operator action |

State transitions are monotonic. The workflow does not move backward or erase a completed stage. Temporal event history is the authoritative durable record; typed state is also exposed through a query for demo inspection. For this bounded demo, continue-as-new is unnecessary unless history growth becomes material.

- #todo Decide whether rejection ends the investigation with a report, or allows a revised remediation plan and another approval cycle. Recommended for the 15-hour scope: end with a rejected report.

### Step and Activity Boundaries

1. **Ingest:** Validate and normalize workflow input in deterministic workflow code. Invalid input fails permanently before any external operation.
2. **Retrieve evidence:** One read-only activity queries local metadata, lineage, change history, and prior incidents and returns a typed evidence bundle.
3. **Investigate:** One idempotent LLM activity returns structured, evidence-cited hypotheses and confidence.
4. **Assess impact:** One deterministic computation over lineage data when practical; use an activity only if it performs I/O.
5. **Plan remediation:** One idempotent LLM activity consumes the persisted diagnosis and impact assessment and returns a typed plan.
6. **Approve:** The workflow records an approval request and waits for a Temporal signal. A pipeline retry always requires approval. Low confidence is recorded as an additional approval reason rather than creating a separate gate.
7. **Retry pipeline:** One idempotent side-effecting activity invokes the simulated pipeline-control tool.
8. **Export report:** One idempotent activity writes a terminal report for completed, rejected, or failed investigations.

- #todo Set the low-confidence threshold. Recommended initial value: confidence `< 0.70`.
- #todo Decide whether a high-confidence investigation still needs approval before retry. The current decision assumes yes, matching the project success criteria.

### Retry and Timeout Policy

Errors are classified before retrying:

| Failure class | Examples | Policy |
|---|---|---|
| Retryable | Timeout, connection reset, HTTP 429, HTTP 5xx, transient trace failure | Exponential backoff with bounded attempts |
| Non-retryable | Invalid input, schema mismatch, unsupported check type, malformed structured model output after repair limit | Fail the stage and export diagnostics |
| Indeterminate side effect | Timeout after dispatching pipeline retry or report write | Retry with the same idempotency key and recover the stored result |
| Worker/process crash | Kill during any activity or wait state | Temporal schedules recovery; completed results are replayed from history |

Initial activity defaults:

- Evidence retrieval: 3 attempts, 10-second start-to-close timeout.
- LLM activities: 3 attempts, 60-second start-to-close timeout, 1-second initial backoff, coefficient 2, 15-second maximum backoff.
- Pipeline retry: 5 attempts, 30-second start-to-close timeout.
- Report export: 3 attempts, 10-second start-to-close timeout.
- Do not retry non-retryable application errors.
- Langfuse export failure must not fail the business workflow; record locally and allow best-effort telemetry retry.

- #todo Confirm these timeout and attempt values after choosing the model provider and local Temporal environment.
- #todo Choose approval expiry behavior and duration. Recommended demo behavior: no automatic expiry; expose cancellation as a separate signal.

### Idempotency Strategy

Every externally observable operation receives a stable key:

```text
{investigation_id}:{operation_name}:{operation_version}
```

Examples:

```text
inv-123:generate-diagnosis:v1
inv-123:plan-remediation:v1
inv-123:retry-pipeline:v1
inv-123:export-report:v1
```

Before executing an operation, the activity checks a durable idempotency record keyed by this value:

- `COMPLETED`: return the stored typed result without invoking the dependency.
- `IN_PROGRESS` with a valid lease: retry later rather than execute concurrently.
- Missing or expired `IN_PROGRESS`: atomically claim the key, perform the operation, then persist the result as `COMPLETED`.
- Failed before side-effect dispatch: release or mark the claim retryable.
- Outcome unknown after dispatch: reconcile by key with the target system before issuing another operation.

The idempotency record contains the key, operation type, input hash, status, lease expiry, attempt count, result or result reference, and timestamps. Reusing a key with a different input hash is a permanent error.

For the demo, use a transactional local store shared across worker restarts. The simulated pipeline-control operation and its idempotency record must commit atomically. Reports are written to a temporary file and atomically renamed to a deterministic path; an existing report with the same input hash is returned as success.

- #todo Choose the local idempotency store. Recommended: SQLite, because it supports atomic claims and survives worker restarts without adding infrastructure.
- #todo Choose the LLM provider and verify whether it accepts provider-side idempotency keys. Without that support, a crash after the provider completes but before the local result commits can cause a duplicate provider call and charge, although downstream application effects remain deduplicated. This limitation must be shown honestly in the README.

### Human Approval

The workflow enters `AWAITING_APPROVAL` before pipeline retry and waits without consuming a worker thread. Approval arrives through a named Temporal signal containing:

- Investigation ID and expected plan version.
- Decision: `APPROVE`, `REJECT`, or `CANCEL`.
- Approver identity and optional comment.
- Decision timestamp supplied by workflow time, not wall-clock code in an activity.

The workflow accepts only the first valid decision for the current plan version. Duplicate identical signals are no-ops. Conflicting or stale signals are recorded and rejected. Approval authorizes only the exact persisted remediation plan and does not itself execute the retry.

- #todo Define who may approve in the demo. Recommended: accept a CLI-provided non-empty approver name and state clearly that production authorization is out of scope.

### Observability and Failure Injection

- Create one Langfuse trace per investigation and one span per workflow stage, activity attempt, model generation, and tool call.
- Record operation names, idempotency keys, attempt numbers, latency, model/token/cost data, failure class, and Temporal identifiers.
- Do not record secrets or unrestricted prompts/tool outputs; use allow-listed structured fields.
- Make telemetry resilient to replay by assigning stable observation IDs where supported.
- Inject deterministic failures at named activity boundaries, including after an operation commits but before its result is returned.

The required recovery tests kill or fail the worker after evidence retrieval, after an LLM result is stored, after pipeline retry commits, and after report creation. On restart, they assert terminal completion and exactly one completed record for each protected operation.

- #todo Select the primary crash point for the recorded demo. Recommended: after remediation-plan persistence and before approval, with the after-side-effect cases covered by automated tests.

## Invariants

1. Workflow code performs no direct I/O or nondeterministic computation.
2. A completed activity result is consumed from Temporal history during replay.
3. Every LLM call and externally visible write has a stable idempotency key.
4. A pipeline retry cannot begin without approval for the current plan version.
5. Replaying workflow history cannot create a second pipeline retry or report.
6. Every hypothesis, impact claim, and remediation references persisted evidence IDs.
7. Terminal state includes enough information to explain failure without exposing secrets.

## Consequences

### Positive

- Worker restarts require no manual state repair.
- Temporal history makes orchestration progress auditable, while idempotency records make side-effect behavior demonstrable.
- Typed stage outputs constrain nondeterministic model behavior and simplify testing.
- The design clearly separates replay safety from external exactly-once claims.

### Tradeoffs

- The idempotency store adds a second durable data mechanism alongside Temporal.
- Leases and reconciliation add complexity for operations whose outcome is unknown.
- LLM provider behavior limits the strength of the no-duplicate-call guarantee.
- Ending rejected investigations avoids approval-loop complexity but limits plan revision in the demo.

## Alternatives Considered

**Store all progress only in Temporal history.** Rejected because Temporal prevents re-execution of recorded completed activities during replay, but cannot eliminate the activity completion gap after an external side effect.

**Run the entire investigation in one activity.** Rejected because retries would repeat too much work, obscure stage-level failures, and make approval and observability awkward.

**Use free-form multi-agent conversation as state.** Rejected because it is difficult to validate, version, replay, cite, and test compared with typed persisted outputs.

**Claim end-to-end exactly-once execution.** Rejected because external model APIs may not support atomic result persistence or idempotency. The supported guarantee is exactly once from DurableAgent's application perspective, with explicit limitations.

## Acceptance Checks

- Kill the worker at each named fault boundary, restart it, and verify the workflow reaches the expected terminal or approval state.
- Assert retrieval, diagnosis, remediation planning, pipeline retry, and report counters do not increase after their result has been durably recorded.
- Deliver duplicate and conflicting approval signals and verify only one valid transition occurs.
- Simulate retryable and non-retryable failures and verify their configured policies and trace annotations.
- Reuse an idempotency key with changed input and verify the operation fails without dispatch.
- Verify every report claim references an evidence ID present in the persisted evidence bundle.
- Correlate the Temporal workflow and Langfuse trace using the investigation and workflow IDs.

## Deferred Decisions

Resolve every `#todo` before changing this ADR to **Accepted**. Authentication, production data-system integration, multi-tenant isolation, Kubernetes deployment, and automated remediation remain out of scope.