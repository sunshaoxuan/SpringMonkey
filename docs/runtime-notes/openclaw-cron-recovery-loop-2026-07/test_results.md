# Test results

## Automated

The final complete `scripts/openclaw` suite passed: `330 passed in 39.99s`.

Registry, capability baseline, repository guardrails, compileall and `git diff --check` also passed.

## Runtime status

Local tests use injected command results and verify the state machine, command ordering, blocking policy, Gateway restart, model probe gate, official rerun command and later-run reconciliation.

Remote host activation remains `evidence_missing` until the host checkout, timer output, incident state and official rerun record can be read directly.
