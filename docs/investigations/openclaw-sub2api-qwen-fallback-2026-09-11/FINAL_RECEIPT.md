# Final receipt

Status: deployed and accepted at 2026-09-11 03:00 JST

Deployed commit: `d9baadc`

Primary model: `gpt-5.3-codex-spark`

Fallback model: `hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S`

Fallback endpoint: `http://ccnode.briconbric.com:49530/v1`

Fallback timeout: 180 seconds

Acceptance: Linux release preflight passed, 141 remote tests passed, `openclaw.service` is active, both OpenClaw configs contain the Qwen fallback, the service account can read the dedicated key file, and forced primary failures succeeded through both the intent and generic fallback paths.

Rollback: revert the task commit, redeploy the preceding repository revision, run the model auth profile guard installer, and restart `openclaw.service`.
