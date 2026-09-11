# Evidence index

| Claim | Evidence | Confidence | Limitation |
|---|---|---|---|
| The delivered XHS document exists as a recorded artifact | `docs/runtime-notes/xhs-cron-network-recovery-2026-09-10.md` | high | Repository record does not prove owner access |
| The connected owner account lacks access | Google Drive metadata read for the delivered document returned `NOT_FOUND` | high | Provider hides inaccessible file metadata |
| The access tool used an ambiguous recipient | `scripts/openclaw/artifact_access_followup_tool.py` before this repair | high | Historical agent text remains pending |
| The router executed the intended access path | Production intent audit records for repeated access requests show `artifact/access`, `execute_agent=true`, and passed audit | high | Tool result lacked independent account-side access verification |
| The repaired workflow is private and role-bounded | Access tool prompt and XHS owner-access policy tests | high | Real production postcheck pending deployment |
| Default-session reuse can block a short repair | First production repair after `bdac5cf` failed with `context_overflow` before tool work | high | Independent session retry pending |
