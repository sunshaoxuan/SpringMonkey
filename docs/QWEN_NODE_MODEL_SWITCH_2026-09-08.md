# Qwen node model configuration update

Request: replace qwen3:14b calls routed through 192.168.20.54 or ccnode.briconbric.com with hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S.

Updated the matching local configuration and runtime defaults. Provider-qualified OpenClaw values retain their ollama/ prefix; the Ollama request must preserve the full hf.co model identifier. Existing endpoints, credentials, embedding models and unrelated providers retain their current values.

This change does not deploy remote services. At investigation time, ccnode.briconbric.com:22545/api/tags and 192.168.20.54:11434/api/tags timed out. Remote model availability and generation remain unverified.

Validation: focused local configuration, request payload and provider-prefix tests. See the task receipt in C:/workspace/codex-work/qwen-node-model-switch for actual results and scan limitations.

Rollback: revert the dedicated model-switch commit. For ignored AnySQL config.yaml, restore only llm.chat_model to the previously recorded qwen3:14b value if rollback is required.
