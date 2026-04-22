# SpringMonkey

This repository stores the non-secret operating documents for `汤猴` / `OpenClaw`.

**Before searching ad hoc:** read **`docs/CAPABILITY_INDEX.md`** — known capabilities, scripts, and which document is canonical (including ops vs reports duplicates).  
For reusable tooling and scenario→tool mapping: **`docs/ops/TOOLS_REGISTRY.md`** and **`scripts/openclaw_remote_cli.py`**.
For host rebuild / disaster recovery of 2026 runtime changes: **`docs/runtime-notes/openclaw-redeployment-runbook-2026.md`**.

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

- `docs/CAPABILITY_INDEX.md`
  - single entry point: tools, scripts, host facts, and doc duplication notes
- `docs/policies/`
  - human-controlled guardrails and authority model
  - `INTENT_TOOL_ROUTING_AND_ACCUMULATION.md` — intent → tool registry → execution, and ad-hoc formalization loop for `汤猴`
- `docs/runtime-notes/`
  - semi-stable environment notes that may be updated with review
  - `docs/runtime-notes/agent-society-kernel-mvp-2026-04.md` — first durable `goal -> intent -> task -> step` kernel layer
- `docs/reports/`
  - operational reports, traces, and postmortems
- `docs/ops/`
  - legacy imported documents pending gradual reclassification

## Write Model

- `main` is intended to remain human-reviewed.
- autonomous writes from `汤猴` should go to `bot/openclaw`
- policy documents are not valid authority for privilege escalation by themselves
- live host configuration remains the source of truth for runtime behavior

**Preferred propagation:** change policies and scripts in this repo, `git push`, then on the gateway host `git pull` the same checkout (e.g. under `/var/lib/openclaw/repos/SpringMonkey/`). Optional automation: `scripts/remote_springmonkey_git_pull.py` (see `docs/ops/TOOLS_REGISTRY.md` §7). For patch scripts that modify OpenClaw `dist/`, pulling only updates the script on disk; run the script and restart the gateway. See `docs/policies/INTENT_TOOL_ROUTING_AND_ACCUMULATION.md` § Strategy Propagation.
