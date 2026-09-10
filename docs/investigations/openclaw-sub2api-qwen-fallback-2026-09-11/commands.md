# Command record

Sensitive credentials were loaded through existing credential projections and were never printed.

1. Read repository routing, fallback, installer, policy, and test files.
2. Read production fallback environment, OpenClaw model configuration, recent intent call records, and the live 49530 model catalog.
3. Query the local Sub2API model catalog and require the exact Qwen model ID.
4. Run a minimal strict JSON request through `/responses`.
5. Run a strict `IntentFrame` request through `/chat/completions`.
6. Run the complete 43,598-character Harness intent prompt through `/chat/completions`.
7. Run focused unit tests and release checks.
8. Deploy through the existing FRP SSH path, run host smoke and forced-failure acceptance, then inspect service and delivery evidence.
