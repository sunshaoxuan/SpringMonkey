# OpenClaw Permission Changelog

Updated: 2026-03-26 (Asia/Tokyo)

## Purpose

Track meaningful permission-surface changes made to `OpenClaw` and adjacent maintenance paths.

This file is focused on:

- what was opened
- why it was opened
- what remains constrained
- what proved incompatible

## 2026-03-26: Task-Domain Exec Expansion

### Change

- `tools.exec.host = gateway`
- `tools.exec.security = full`
- `tools.exec.ask = off`

### Why

- task-domain operations were repeatedly blocked by `allowlist miss`
- the news workflow now relies on:
  - config edits
  - apply scripts
  - verify scripts
  - git operations
- repeated manual approvals made the workflow unreliable

### Scope

- intended for task-domain operations
- not intended as blanket approval to redefine host security boundaries

### Remaining Boundaries

- remote access paths remain protected:
  - `frpc`
  - `tailscale`
  - `ssh`
- core root-managed maintenance still remains separate

## 2026-03-26: Elevated Discord Path Enabled

### Change

- `tools.elevated.enabled = true`
- `tools.elevated.allowFrom.discord = ["*"]`

### Why

- Discord-originated maintenance and repo-sync tasks were failing on elevated execution gates
- task-domain changes should be operable from the actual control surface in use

### Risk Note

- any Discord-triggered turn in the allowed control channel can enter the elevated path
- this was accepted to preserve operational usefulness, not because the risk disappeared

## 2026-03-26: Invalid Elevated Config Key Identified

### Change Attempt

- attempted to use:
  - `tools.elevated.defaultLevel`

### Result

- current OpenClaw version rejects this key in config schema
- writing it causes service crash loops

### Rule

- do not write `tools.elevated.defaultLevel` back into `openclaw.json`

## 2026-03-26: Runtime Compatibility Patch

### Change

- minimal patch applied to:
  - `/usr/lib/node_modules/openclaw/dist/auth-profiles-DRjqKE3G.js`
- backup created:
  - `/usr/lib/node_modules/openclaw/dist/auth-profiles-DRjqKE3G.js.bak-20260326-elevated-full`

### Why

- current public config surface was insufficient to make Discord-originated elevated exec reliably bypass allowlist checks
- runtime patch was used as a compatibility workaround

### Operational Consequence

- future OpenClaw upgrades may overwrite this patch
- any post-upgrade regression in Discord elevated exec should first check whether this patch is still present or needs to be re-evaluated against the new version

## 2026-03-26: Root-Side Auto Update Ownership

### Change

- OpenClaw package replacement moved to root-owned maintenance flow:
  - `/usr/local/lib/openclaw-maint/check_openclaw_update.sh`
  - `/usr/local/lib/openclaw-maint/apply_openclaw_update.sh`
  - `openclaw-update.service`
  - `openclaw-update.timer`

### Why

- `openclaw` user cannot safely replace the global package under `/usr/lib/node_modules/openclaw`
- self-upgrade by the agent mixes task authority with runtime replacement authority

### Boundary

- the agent may detect and report updates
- root-side maintenance owns actual package replacement and restart verification
