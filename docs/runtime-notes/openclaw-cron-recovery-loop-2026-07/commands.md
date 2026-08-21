# Command log

```text
python -m compileall -q scripts/openclaw
python -m pytest scripts/openclaw/test_cron_recovery_guard.py scripts/openclaw/test_model_runtime_probe.py scripts/openclaw/test_cron_failure_self_heal.py scripts/openclaw/test_official_runtime_shadow_bridge.py -q
python -m pytest scripts/openclaw -q
python scripts/openclaw/test_intent_tool_registry.py
python scripts/openclaw/test_harness_registry.py
python scripts/openclaw/test_capability_baseline.py
python scripts/test_repository_guardrails.py
git diff --check
```
