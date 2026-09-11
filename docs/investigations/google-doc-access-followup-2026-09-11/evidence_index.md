# Evidence index

| Claim | Evidence | Confidence | Limitation |
|---|---|---|---|
| The delivered XHS document exists as a recorded artifact | `docs/runtime-notes/xhs-cron-network-recovery-2026-09-10.md` | high | Repository record does not prove owner access |
| The connected owner account lacks access | Google Drive metadata read for the delivered document returned `NOT_FOUND` | high | Provider hides inaccessible file metadata |
| The access tool used an ambiguous recipient | `scripts/openclaw/artifact_access_followup_tool.py` before this repair | high | Historical agent text remains pending |
| The router is configured to execute the access agent | `config/openclaw/intent_tools.json` and `scripts/openclaw/intent_tool_router.py` | high | Production log correlation remains pending |
| The repaired workflow is private and role-bounded | Access tool prompt and XHS owner-access policy tests | high | Real production postcheck pending deployment |
