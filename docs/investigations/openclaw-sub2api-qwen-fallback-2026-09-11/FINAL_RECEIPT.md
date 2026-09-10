# Final receipt

Status: implementation complete, deployment pending

Primary model: `gpt-5.3-codex-spark`

Fallback model: `hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S`

Fallback endpoint: `http://ccnode.briconbric.com:49530/v1`

Fallback timeout: 180 seconds

Rollback: revert the task commit, redeploy the preceding repository revision, run the model auth profile guard installer, and restart `openclaw.service`.
