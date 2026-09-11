# Evidence index

| Claim | Evidence | Confidence | Limitation |
|---|---|---|---|
| The delivered XHS document exists as a recorded artifact | `docs/runtime-notes/xhs-cron-network-recovery-2026-09-10.md` | high | Repository record does not prove owner access |
| The connected owner account lacks access | Google Drive metadata read for the delivered document returned `NOT_FOUND` | high | Provider hides inaccessible file metadata |
| The access tool used an ambiguous recipient | `scripts/openclaw/artifact_access_followup_tool.py` before this repair | high | Historical agent text remains pending |
| The router executed the intended access path | Production intent audit records for repeated access requests show `artifact/access`, `execute_agent=true`, and passed audit | high | Tool result lacked independent account-side access verification |
| The repaired workflow is private and role-bounded | Access tool prompt, XHS owner-access policy tests, and production host at `9c8691c` | high | Existing-document postcheck remains blocked |
| Default-session reuse can block a short repair | First production repair after `bdac5cf` failed with `context_overflow` before tool work | high | Independent session retry pending |
| Long-task cache can point at an older document | First production repair selected the older `1KA...` artifact while the accepted XHS run delivered the newer `1Ac...` artifact | high | Corrected resolver pending production retry |
| Live cron session layout did not satisfy the initial scanner | Production implicit-resolution test after `f368bfe` still selected the old cache entry | high | Scanner removed in favor of authoritative registry |
| UUID isolation alone did not pass static precheck | Explicit access retry under `f368bfe` again returned `context_overflow` with a 327-character current turn | high | Explicit `gpt-5.6-sol` implementation is deployed; execution remains blocked by FRP |
| The current artifact is authoritative on the host | Production `artifact_registry.py record` and `latest` migration at `9c8691c` | high | Viewer access is a separate acceptance gate |
| The target account still lacks access | Post-deployment Google Drive metadata read returned `404 NOT_FOUND` | high | Google hides inaccessible metadata |
| The remaining operational blocker is before host authentication | Repeated Paramiko attempts ended with `Error reading SSH protocol banner`, including attempts after extended cooldown | high | Host-side access agent did not start |
