# Google Docs access follow-up investigation

## Question

Why did TangHou reject repeated Discord requests to grant access to the Google Docs produced by the XHS job, and how should the workflow become durable?

## Findings

1. The XHS job produced and delivered a real Google Docs URL, while the connected owner Google account received `NOT_FOUND` when reading its Drive metadata. This verifies that the delivered account lacked access.
2. The registered artifact access tool already had owner-DM write governance and `execute_agent=true`. Its execution prompt referred only to `current owner` and contained no durable Google account mapping.
3. The repository had no `OPENCLAW_OWNER_GOOGLE_EMAIL` mapping. A new conversation therefore could not reconstruct the intended Google recipient from system state.
4. The access agent relied on a logged-in browser to interpret the ambiguous recipient. The repaired contract supplies one host-side email, grants Viewer only, prohibits broad link sharing, and requires post-write verification.
5. The XHS job now applies the same contract before delivery so future documents do not require a separate repair conversation.
6. The first production repair attempt reused the default main agent session and failed precheck with `context_overflow`. The access tool now supplies a new UUID through the documented `openclaw agent --session-id` selector for every bounded repair run.
7. That attempt also resolved an older cached artifact URL instead of the latest XHS cron document. A first session-scanning repair did not match the live cron session format and was removed. Resolution now uses an explicit URL or one authoritative host-side artifact registry written by the producing workflow.
8. A UUID-isolated retry still failed static prompt precheck under the default main model. Access runs now select the task-authoritative `openai-codex/gpt-5.6-sol` model explicitly.

## Boundary

The account identifier stays in `/etc/openclaw/openclaw.env` on the host and is not committed. The latest artifact URL stays in the owner-controlled OpenClaw workspace state. The workflow does not create public links, grant edit access, or transfer ownership.

## Runtime evidence gap

The first production SSH read completed remotely but its local output hit a CP932 encoding failure. A later combined deployment recovered the historical route records. They show repeated `artifact/access` selection, `execute_agent=true`, and passed intent audit. This rules out lost conversational intent as the primary cause.
