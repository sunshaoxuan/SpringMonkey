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
  - morning JST run
  - afternoon JST run
- Delivery target is the Discord `public` channel.
- Current known degradations:
  - `web_search` lacks a search API key
  - browser operations may still time out
  - `web_fetch` can be blocked by upstream content defenses
- Public RSS and normal web fetch remain valid fallback sources.
