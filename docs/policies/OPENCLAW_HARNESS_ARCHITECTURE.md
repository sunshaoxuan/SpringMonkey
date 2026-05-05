# OpenClaw Harness Architecture

## Purpose

OpenClaw Harness is the repository-owned contract that separates frontend channel handling from long-running business execution.

The gateway process is a dispatcher. It may normalize inbound events, classify intent, check permission, send typing/ack, dispatch to a registered worker, and deliver the final result. It must not hide long-running business work inside the frontend response path.

## Layers

The machine-readable source is `config/openclaw/harness.json`.

| Layer | Responsibility | Current baseline |
|---|---|---|
| Agent Runtime | Task envelope, agent loop, state, failure recovery | `agent_society_kernel.py`, `job_orchestrator.py`, `harness_runtime.py` |
| Skill Layer | Skill version, tests, publish/rollback state | `config/openclaw/skills.json` |
| Tool Layer | Tool registry, routing, permission, invocation log | `config/openclaw/intent_tools.json`, `intent_tool_router.py` |
| Context Layer | Prompt builder, memory/RAG/business context loading | `harness_context.py` |
| Governance Layer | Permission guard, approval, policy, audit | `harness_governance.py` |
| Observability Layer | Trace ID, model/tool logs, latency, evaluation, report delivery | `harness_observability.py`, `harness_reporter.py` |

## Three Chains

OpenClaw runtime behavior is verified as three chained contracts.

| Chain | Required flow | Boundary |
|---|---|---|
| Analysis | `Gateway Event -> Context Builder -> intentAgent -> Tool Binder -> Semantic Reviewer` | The model owns semantic judgment. Registry hints describe capabilities only; keyword/pattern functions are diagnostic-only and must not be the default DM execution path. |
| Execution | `Governance -> Worker -> ToolInvocationRecord -> Result Evaluator -> Recovery` | Workers may only execute registered entrypoints. Write operations require owner DM, confirmation/idempotency policy, and postcheck contract. |
| Reporting | `ReportEnvelope -> owner DM/public policy -> delivery log` | Owner DM receives execution reports and failures. Public channels receive only formal successful public payloads; stack traces, RSS logs, model errors, and raw stderr stay in backend logs. |

## SubAgent Pool

The SubAgent pool is a contract before it is a process model. v1 may implement workers as scripts or in-process dispatch, but every durable task must name its owner worker.

| Agent | Boundary |
|---|---|
| `intentAgent` | classifies chat/task/tool/gap; never performs business writes |
| `plannerAgent` | creates step plans and result contracts |
| `toolWorker` | invokes deterministic read/general tools |
| `browserWorker` | owns browser/CDP/login/confirmation/post-check work |
| `newsWorker` | owns news collection, processing, draft verification, and publish formatting |
| `timescarWorker` | owns TimesCar query/book/cancel/adjust/report flows |
| `recoveryWorker` | owns gaps, helper generation, bounded retry, self-repair |
| `evaluatorAgent` | checks result contracts before success is reported |

## Rules

- Public channels cannot trigger super-console write operations.
- Owner DM write tools must declare permission, confirmation policy, idempotency, owner agent, input/output schema, and invocation log policy.
- Timed jobs must not load chat context unless explicitly registered as a DM continuation.
- Final user replies must distinguish submission from post-check confirmation.
- Every DM task report must include task, stage, tool, write-operation flag, postcheck state, failure type when present, and trace/log reference.
- A public channel failure diagnostic is a policy violation; failures are reported to owner DM only.
- Harness rules, prompts, registries, patch source, and tests must be committed, pushed, pulled by the host, and verified before being treated as deployed.

## Verification

Minimum local gate:

```bash
python -m compileall -q scripts/openclaw scripts/timescar scripts/weather
python scripts/openclaw/verify_intent_tool_registry.py
python scripts/openclaw/verify_harness_registry.py
python scripts/test_repository_guardrails.py
python scripts/openclaw_behavior_rule_gate.py --skip-pushed-check
python -m pytest -q scripts/openclaw/test_harness_three_chains.py
```
