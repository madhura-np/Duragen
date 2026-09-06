# DurableAgent: Crash-Resilient Agent Workflows

## Project Definition

DurableAgent is an open-source reference implementation for long-running, tool-using AI workflows that survive process crashes and transient failures without losing progress or repeating completed side effects. It uses **Temporal** for durable orchestration and **Langfuse** for trace collection and visualization.

The demonstration workflow investigates a failed data-pipeline quality check:

1. Ingest a failed freshness, schema, volume, or null-rate check.
2. Retrieve evidence from local pipeline metadata, lineage, recent changes, and prior incidents.
3. Identify affected downstream datasets and generate evidence-cited root-cause hypotheses.
4. Propose a remediation, pausing for human approval when confidence is low or before triggering a pipeline retry.
5. Execute the approved simulated retry and export the investigation report.

Each step records durable state. LLM calls and tool operations use idempotency keys so that a worker can be killed and restarted without repeating successful work or triggering duplicate retries. The project is intentionally a reusable execution pattern, not a general-purpose workflow engine or a production data-observability product.

## Intended Impact

- Demonstrates how to make nondeterministic agent workflows reliable using checkpoints, retries, timeouts, idempotency, and human approval.
- Gives engineers a runnable template for workflows that may take minutes or hours and interact with unreliable models or external tools.
- Shows the distinction between workflow replay and repeated side effects, a central production concern for agentic systems.
- Extends proven distributed-systems and event-platform experience into agent orchestration, observability, and cost control.
- Provides direct evidence for Staff AI Platform and Agentic Platform roles without claiming ML research expertise.

## Architecture And Scope

- **Python worker and Temporal:** Durable workflow state, activity retries, timeouts, signals, and resume behavior.
- **Two agentic stages:** An evidence investigator and a remediation planner. They communicate through typed persisted state rather than free-form agent conversation.
- **Two tools:** Local metadata and lineage search, plus a simulated pipeline-control tool that retries a failed run and writes the final investigation report. Side effects are protected by idempotency keys.
- **Langfuse observability:** One trace per investigation, with spans for workflow stages, LLM generations, tool calls, retries, failures, token usage, cost, and latency. Temporal workflow IDs are attached as trace metadata for correlation.
- **Fault injection:** A deterministic switch kills or fails the worker after a selected step.
- **Tests:** Verify resume-from-checkpoint behavior and prove that completed LLM calls, pipeline retries, and report exports are not duplicated.

Out of scope: custom orchestration infrastructure, a custom trace backend, multi-tenant authentication, a polished web UI, vector-database deployment, Kubernetes, connections to production data systems, and automated remediation beyond a simulated retry.

## Demo Deliverable

A public repository and a three-to-five-minute recorded demo that shows:

1. Start an investigation for a failed data-quality check and inspect its Temporal execution.
2. Complete metadata and lineage retrieval, then generate an evidence-cited diagnosis and downstream impact assessment.
3. Kill the worker while it prepares the remediation plan.
4. Restart it and show the workflow resuming from durable state.
5. Verify through counters and idempotency records that completed retrieval and LLM operations were not repeated.
6. Pause before the proposed pipeline retry, submit human approval, and complete the workflow without creating a duplicate retry or report.
7. Open the correlated Langfuse trace to inspect the stage hierarchy, tool calls, failure and retry, token cost, and end-to-end latency.
8. Run the automated crash-recovery test suite.

Repository deliverables: runnable code, Docker Compose setup, sample quality-check failures, pipeline metadata, lineage, change history, and prior incidents, architecture diagram, failure-semantics ADR, automated tests, Langfuse screenshots or shared trace, and a short limitations section.

## Task Breakdown And Time Budget

| Task | Deliverable | Time |
|---|---|---:|
| Define workflow and failure semantics | State model, step boundaries, retry rules, idempotency strategy, and one-page ADR | 1.5 h |
| Scaffold local environment | Python project, Temporal dev server, worker, configuration, and sample data | 1.5 h |
| Implement durable workflow | Ingest, investigate, assess impact, plan remediation, approve, retry, and export using typed state | 3.0 h |
| Add agent tools and LLM integration | Local metadata and lineage search, structured diagnosis, citations, remediation, and confidence output | 2.0 h |
| Protect side effects | Stable idempotency keys, result persistence, duplicate suppression, timeouts, and retry policies | 1.5 h |
| Integrate Langfuse observability | Trace hierarchy, workflow correlation, LLM/tool spans, errors, retries, token usage, cost, and latency | 1.5 h |
| Build fault-injection tests | Kill/fail at controlled boundaries; verify resume and no duplicate operations | 1.5 h |
| Package demo | Demo script, Docker Compose command, architecture diagram, README, screenshots, and recorded walkthrough | 1.5 h |
| **Total** | | **14.0 h** |

The remaining **1 hour of the 15-hour cap** is contingency for SDK integration or local-environment issues. If unused, spend it adding one second failure scenario rather than expanding the UI.

## Success Criteria

- A workflow completes after a worker restart without manual state repair.
- Previously successful LLM calls, approved pipeline retries, and report exports execute exactly once from the application's perspective.
- Retryable failures are visible in both Temporal history and the correlated Langfuse trace.
- Low-confidence diagnoses and proposed pipeline retries pause for human approval and resume within the same workflow.
- The completed report identifies affected downstream datasets and ties each root-cause hypothesis and remediation to retrieved evidence.
- The trace reports model, token usage, estimated cost, latency, tool inputs/outputs, and errors without recording secrets.
- A new user can run the demo locally from documented commands in under ten minutes, excluding model and observability account setup.