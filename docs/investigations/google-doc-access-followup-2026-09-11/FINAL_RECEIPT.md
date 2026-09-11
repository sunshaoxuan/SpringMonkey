# Final receipt

Status: implementation deployed; existing-document access repair blocked by the FRP SSH banner gate

Implemented behavior:

- one host-side Google account mapping
- direct Viewer sharing only
- no public link permission
- no edit grant or ownership transfer
- post-write role verification
- proactive XHS sharing before delivery
- authoritative latest-artifact registration before delivery
- fresh access-agent session with explicit `openai-codex/gpt-5.6-sol`

Production evidence:

- host checkout reached `9c8691c`
- the current XHS document was recorded in the authoritative registry
- local focused regression suite passed with 122 tests
- the connected target Google account still receives `404 NOT_FOUND` for the current document
- three later SSH attempts were closed before authentication while reading the protocol banner, including attempts after conservative cooldown windows

Acceptance state:

- future-delivery behavior is deployed
- existing-document Viewer access is not independently verified
- completion requires one successful access-agent run followed by a successful metadata read from the target Google account

Rollback: revert the implementation commit, deploy the preceding revision, remove `OPENCLAW_OWNER_GOOGLE_EMAIL` from `/etc/openclaw/openclaw.env`, restore the preceding XHS cron payload, and restart `openclaw.service`.
