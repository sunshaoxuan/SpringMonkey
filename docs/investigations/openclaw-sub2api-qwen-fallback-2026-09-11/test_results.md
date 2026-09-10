# Test results

## Live model checks

The exact Qwen ID was present in both remote and local Sub2API catalogs.

Minimal strict intent smoke passed through `/responses`.

Minimal strict intent smoke passed through `/chat/completions` in 4,610 ms.

The complete Harness prompt passed through `/chat/completions` in 97,700 ms and produced `artifact/access` with tool candidate `openclaw.artifact.access_followup`.

## Unit tests

Initial focused result: 36 passed.

Final local routing, installer, guard, repository, cron, and weather regression result: 141 passed.

Python compilation and `git diff --check` passed.

A real local fault injection pointed the primary intent endpoint to an unavailable port. The production code selected the exact Sub2API Qwen fallback and returned a valid `chat/general/chat` frame with `fallback_used=true` in 6,836 ms.

The local release preflight could not execute its shell phase because this host resolves `bash.exe` to an unavailable WSL service. The same release preflight remains required on the Linux target before deployment acceptance.

Final release and remote acceptance results are recorded after deployment.
