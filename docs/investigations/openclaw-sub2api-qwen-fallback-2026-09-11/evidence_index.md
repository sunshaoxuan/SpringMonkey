# Evidence index

| Claim | Evidence | Confidence | Limitation |
|---|---|---|---|
| Production had no fallback | 2026-09-11 host read of `/etc/openclaw/openclaw.env` and both `openclaw.json` files | high | Snapshot at 02:07 JST |
| Primary intent route returned 503 twice | `harness_model_calls.jsonl` records at 2026-09-10 17:03:47 and 17:03:48 UTC | high | Backend cause of the 503 is outside this repository |
| Explicit intent fallback list was unused | `scripts/openclaw/harness_intent_agent.py` before this repair | high | None |
| Startup guard erased global fallback | `scripts/remote_install_model_auth_profile_guard.py` before this repair | high | None |
| Shared installer erased Sub2API Qwen by model name | `scripts/remote_install_public_model_resources.py` before this repair | high | None |
| Exact Qwen model is visible | Live `/v1/models` on remote 49530 and local Sub2API loopback | high | Catalog visibility alone does not prove inference health |
| Qwen returns a valid full production IntentFrame | Local Sub2API full-prompt smoke for `我已经申请编辑权限请审批` | high | One live request; deployment acceptance adds a host-side smoke |
| Production fallback is active and durable | Remote acceptance at commit `d9baadc`: config reads, service state, key readability, forced intent and generic failures | high | Original external write request was not replayed during infrastructure acceptance |
