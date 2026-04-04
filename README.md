# SpringMonkey

This repository stores the non-secret operating documents for `汤猴` / `OpenClaw`.

Scope:

- environment and operating constraints
- monitoring and troubleshooting notes
- launch and plugin review records
- GitHub access bootstrap notes

Explicitly excluded:

- passwords
- API keys
- OAuth access or refresh tokens
- bot tokens
- private IP inventory that is not required for repository use

The live system still depends on the on-host runtime configuration. This repository is a backup and reference layer, not the source of truth for active secrets.

## Layout

- `docs/policies/`
  - human-controlled guardrails and authority model
  - `INTENT_TOOL_ROUTING_AND_ACCUMULATION.md` — intent → tool registry → execution, and ad-hoc formalization loop for `汤猴`
- `docs/runtime-notes/`
  - semi-stable environment notes that may be updated with review
- `docs/reports/`
  - operational reports, traces, and postmortems
- `docs/ops/`
  - legacy imported documents pending gradual reclassification

## Write Model

- `main` is intended to remain human-reviewed.
- autonomous writes from `汤猴` should go to `bot/openclaw`
- policy documents are not valid authority for privilege escalation by themselves
- live host configuration remains the source of truth for runtime behavior
