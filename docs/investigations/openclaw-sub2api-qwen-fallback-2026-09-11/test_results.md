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

The local release preflight could not execute its shell phase because this host resolves `bash.exe` to an unavailable WSL service. The Linux target release preflight passed before configuration installation.

## Remote acceptance

Remote repository HEAD was `d9baadc` and the same 141-test set passed on Linux in 11.12 seconds.

The Qwen installer passed exact catalog visibility, strict `IntentFrame` smoke, atomic environment installation, service-account key readability, service restart, and post-restart config verification.

Both `/var/lib/openclaw/.openclaw/openclaw.json` and `/root/.openclaw/openclaw.json` registered Qwen and contained `openai-codex/hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S` as the sole default fallback.

A host-side forced primary failure selected Qwen in 4,675 ms with `fallback_used=true`. A separate generic model call returned exact `ok` through the same Qwen fallback. Final service state was active.
