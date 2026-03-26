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
