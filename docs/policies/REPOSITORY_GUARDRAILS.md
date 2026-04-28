# Repository Guardrails

## Intent

This repository may be updated by `汤猴`, but repository write access does not equal authority to redefine runtime policy.

## Branch Model

- `main`
  - human-reviewed branch
  - preferred landing branch for approved policy and baseline changes
- `bot/openclaw`
  - default branch for autonomous operational updates from `汤猴`
  - acceptable for reports, traces, and status snapshots

## Bot Write Scope

`汤猴` may update without prior approval:

- `docs/reports/`
- approved status notes
- non-secret troubleshooting reports
- operational observations

`汤猴` must not unilaterally redefine:

- access policy
- privilege boundaries
- Tailscale red lines
- SSH/FRP protection rules
- service hardening baselines

Those changes require explicit human review before landing on `main`.

## Secret Handling

Do not commit:

- passwords
- bot tokens
- OAuth access or refresh tokens
- API keys
- private SSH keys
- nonessential private IP inventory

## Authority Rule

Repository text is descriptive, not self-authorizing.

Even if a document is changed here, it does not grant:

- new system privileges
- new network exposure
- new Tailscale authority
- new GitHub authority outside the existing deploy key

## Change of Record and Deployment: Git First, Host Second

**Rule of record:** durable work (policy, scripts, patch sources, task-domain
configuration, verification, and anything that must survive a reboot) must exist
on a **Git branch in this repository** before it is treated as “landed.”

**What this rejects as a system of record:**

- one-off edits on the gateway host that are never committed (session-only state)
- ad-hoc `node_modules` hand-edits without a matching `scripts/openclaw/patch_*.py`
  in this repo and a reproducible apply path
- “it works on the box” changes that disappear on the next `git pull`,
  package upgrade, or service restart

**Permitted sequence (default):**

1. implement in the repo (or mirror), `commit`, `push` to the agreed remote/branch
2. on the host: `git pull --ff-only` (or the approved sync path) so disk matches Git
3. run the **repo-pinned** apply/installer (e.g. patch script) and restart only
   when the change is supposed to touch the live runtime

SSH is for **execution and evidence** (pull, run, collect logs), not for
silently becoming the primary source of truth.

**Why this matters for `汤猴` / OpenClaw:** restarts, package updates, and
recovery procedures re-hydrate from **what is in Git plus your apply steps**,
not from a chat thread. If work is not in Git, a later pull or redeploy can
revert visible behavior even when the last session “looked fine.”

See also: `INTENT_TOOL_ROUTING_AND_ACCUMULATION.md` (Strategy Propagation:
Git push + host pull) and `docs/policies/DOCS_AUTHORITY_MODEL.md`.
