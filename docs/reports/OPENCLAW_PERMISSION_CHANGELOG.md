# OpenClaw Permission Changelog

Updated: 2026-03-26 (Asia/Tokyo)

## 2026-03-26: Task-Domain Exec Expansion

- `tools.exec.host = gateway`
- `tools.exec.security = full`
- `tools.exec.ask = off`

Reason:

- task-domain `apply / verify / git` chains were repeatedly blocked by `allowlist miss`

## 2026-03-26: Elevated Discord Path Enabled

- `tools.elevated.enabled = true`
- `tools.elevated.allowFrom.discord = ["*"]`

Reason:

- Discord-originated maintenance tasks needed an operable elevated path

Risk note:

- this increases the execution surface for the allowed Discord control path

## 2026-03-26: Invalid Elevated Config Key

- `tools.elevated.defaultLevel`

Status:

- invalid for the current public config schema
- must not be written back into `openclaw.json`

## 2026-03-26: Runtime Compatibility Patch

- patched file:
  - `/usr/lib/node_modules/openclaw/dist/auth-profiles-DRjqKE3G.js`
- backup:
  - `/usr/lib/node_modules/openclaw/dist/auth-profiles-DRjqKE3G.js.bak-20260326-elevated-full`

Reason:

- make Discord-originated elevated exec stop falling back to allowlist behavior

## 2026-03-26: Root-Side Auto Update Ownership

- OpenClaw update ownership moved to root-managed maintenance
- the agent may report updates, but root owns actual package replacement
