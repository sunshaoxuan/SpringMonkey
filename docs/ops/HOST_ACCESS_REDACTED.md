# Host Access (Redacted)

Updated: 2026-03-26 (Asia/Tokyo)

## Target Host

- Hostname: `ubuntu-2625`

## Preferred Access

- Primary operational paths:
  - `Tailscale SSH`
  - `FRP SSH`
- Concrete IPs, passwords, and private network coordinates are intentionally excluded from this repository.

## Persistence

- `frpc.service`: enabled + active
- `tailscaled.service`: enabled + active
- `ssh.service`: enabled + active
- `docker.service`: enabled + active
- `NetworkManager.service`: enabled + active

## Notes

- Keep both `frpc` and `tailscale` as protected remote-access items during future cleanup.
- SSH latency can reflect the relay path rather than host load.

## Documentation Rules

- Record topology, service state, constraints, and operating decisions as completely as possible.
- Do not store high-sensitivity secrets here:
  - passwords
  - bot tokens
  - OAuth access / refresh tokens
  - API keys

## OpenClaw Runtime Constraints

- `openclaw.service` must not be reverted to direct `openclaw gateway run ...`.
- The stable form is `systemd` supervising `/usr/local/bin/openclaw-gateway-supervise`.
- `MemoryDenyWriteExecute=false` must remain in the service unit.
- Keep only `HOME=/var/lib/openclaw`.
- Do not reintroduce `OPENCLAW_HOME=/var/lib/openclaw/.openclaw`.
- Live OpenClaw directory: `/var/lib/openclaw/.openclaw`
- Runtime config must include `gateway.mode=local`.
- Do not retain the old root user service:
  - `/root/.config/systemd/user/openclaw-gateway.service`
- If supervisor logging is used, `ReadWritePaths` must include `/var/log/openclaw`.

- Current `tools.exec` runtime posture:
  - `host = gateway`
  - `security = full`
  - `ask = off`
- Purpose:
  - let task-domain `exec / git / python` chains run without repetitive approval churn

- Current `tools.elevated` posture remains:
  - `enabled = true`
  - `allowFrom.discord = ["*"]`
- Known compatibility warning:
  - `tools.elevated.defaultLevel` is not accepted by the current public config schema
  - do not write that key back into `openclaw.json`

- A small runtime compatibility patch exists on the host:
  - `/usr/lib/node_modules/openclaw/dist/auth-profiles-DRjqKE3G.js`
  - backup:
    `/usr/lib/node_modules/openclaw/dist/auth-profiles-DRjqKE3G.js.bak-20260326-elevated-full`

## Key Paths

- Service supervisor: `/usr/local/bin/openclaw-gateway-supervise`
- Audit logs:
  - `/var/log/openclaw/audit.jsonl`
  - `/var/log/openclaw/snapshots.jsonl`
  - `/var/log/openclaw/supervisor.log`

## Long-Term Memory

- Current LTM provider: `memory-lancedb`
- LanceDB path: `/var/lib/openclaw/.openclaw/memory/lancedb`
- Embedding backend:
  - Ollama-compatible `/v1/embeddings`
  - model `bge-m3:latest`
  - dimensions `1024`
- Current policy:
  - `autoCapture=true`
  - `autoRecall=true`

## Discord Entry Notes

- Server name: `PKROCOHR001`
- Control channel name: `public`
- Current bot display name: `汤猴`
- Channel policy currently allows plain text messages without mandatory `@`.
- Avoid role mention confusion when testing channel triggers.

## Tailscale Red Line

- Without explicit authorization, do not run commands that change Tailscale auth or exposure state.
- Forbidden without explicit instruction:
  - `tailscale up`
  - `tailscale login`
  - `tailscale logout`
  - `tailscale set ...`
  - `tailscale serve ...`
  - `tailscale funnel ...`
  - `tailscale switch ...`
- Allowed by default:
  - passive status reads
  - ordinary SSH to an existing Tailscale address
  - non-mutating network checks

## News Broadcast Notes

- Daily news cron exists in two slots:
  - `09:00 JST`
  - `16:30 JST`
- Delivery target is the Discord `public` channel.
- Current known degradations:
  - `web_search` lacks a search API key
  - browser operations may still time out
  - `web_fetch` can be blocked by upstream content defenses
- Public RSS and normal web fetch remain valid fallback sources.

- News broadcasting now has a dedicated task domain:
  - machine config:
    `config/news/broadcast.json`
  - apply tool:
    `scripts/news/apply_news_config.py`
  - verify tool:
    `scripts/news/verify_news_config.py`
  - note:
    `docs/runtime-notes/news-task-domain.md`
- Future changes should go through:
  - config change
  - apply
  - verify
  - then report

## Root-Side Auto Update

- Root now owns OpenClaw package replacement and restart verification.
- Deployed components:
  - `/usr/local/lib/openclaw-maint/check_openclaw_update.sh`
  - `/usr/local/lib/openclaw-maint/apply_openclaw_update.sh`
  - `/etc/systemd/system/openclaw-update.service`
  - `/etc/systemd/system/openclaw-update.timer`
- Log directory:
  - `/var/log/openclaw-maint`
- Verified update result on 2026-03-26:
  - before:
    `OpenClaw 2026.3.13`
  - after:
    `OpenClaw 2026.3.24`
