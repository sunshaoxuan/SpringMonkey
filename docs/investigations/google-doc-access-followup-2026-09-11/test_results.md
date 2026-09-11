# Test results

## Initial focused suite

Command scope: artifact access tool, XHS installer, intent router, intent agent, Harness execution chains, and capability baseline.

Result: 118 passed.

Python compilation passed for the changed runtime scripts. `git diff --check` passed.

## Pending production acceptance

- The host-only owner email profile is deployed.
- `openclaw.service` and the XHS owner-access policy were verified during the first production deployment.
- Production checkout reached `9c8691c` and the current document was recorded in the authoritative registry.
- Run the access follow-up against the existing document.
- Read the document metadata through the connected owner Google Drive account.

## First production attempt

Commit `bdac5cf` deployed successfully. The owner profile, service state, and XHS owner-access policy passed verification. The real access repair failed before browser work because the default main session was already at context overflow. UUID-based session isolation was added for the retry.

The same attempt selected an older cached document. Production showed that the formal cron session identifier was not available in the assumed transcript shape, so that scanner and the legacy cache fallback were removed. Final tests cover atomic artifact registry writes, explicit URL precedence, authoritative registry resolution, fresh UUID sessions, and explicit `gpt-5.6-sol` selection.

## Final production attempts

The focused regression suite passed again with 122 tests. Python compilation and `git diff --check` passed.

The first `9c8691c` production session deployed the commit and recorded the current XHS document. A CLI validation typo supplied an unsupported `--source` argument to the `latest` subcommand, so strict shell error handling stopped before access execution. The one-time command was corrected and smoke-tested locally.

Three later SSH connections were closed by the FRP endpoint while reading the protocol banner, before authentication or remote command execution. Attempts included conservative cooldown windows longer than the earlier observed gate. A connected target-account metadata read still returned `404 NOT_FOUND`, so Viewer access is not accepted.
