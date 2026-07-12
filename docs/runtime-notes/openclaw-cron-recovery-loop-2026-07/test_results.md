# Test results

## Automated

The final official-first complete `scripts/openclaw` suite passed: `339 passed in 32.74s`.

Registry, capability baseline, repository guardrails, compileall and `git diff --check` also passed.

## Runtime status

Local tests use injected command results and verify the state machine, command ordering, blocking policy, Gateway restart, model probe gate, official rerun command and later-run reconciliation.

Official-first tests additionally verify retry/backoff ownership, active-run blocking, one-shot retry slots, pre-rerun state refresh, per-job incident collapsing, new incident generations and official SQLite cron catalog fingerprint parity.

Remote host activation remains `evidence_missing` until the host checkout, timer output, incident state and official rerun record can be read directly.
