# OpenClaw encrypted SecretRef credentials

The active service receives `openclaw-secrets.json` through systemd `LoadCredentialEncrypted`. The tracked `config/openclaw/openclaw-secrets.json.cred` is host-bound ciphertext generated with `systemd-creds encrypt --with-key=host`.

OpenClaw resolves supported SecretRefs from `/run/credentials/openclaw.service/openclaw-secrets.json` into an in-memory snapshot. The host decrypts the committed `systemd-creds` ciphertext in `ExecStartPre` and removes that runtime plaintext in `ExecStopPost`; this avoids a systemd 257 credential-manager protocol error for the current unit layout. The migration plan contains refs only. Intent, research, model-fallback, Discord delivery, long-task supervision, weather-image generation, and direct-cron helpers read the same runtime credential when no explicit operator override is supplied. Ollama uses its `auth-profiles` SecretRef as the single credential owner, so no redundant provider `apiKey` is persisted.

## Rotation

1. Encrypt a replacement payload with `--with-key=host --name=openclaw-secrets.json`.
2. Replace the `.cred` file, reload systemd, restart the service, and run `openclaw secrets reload`.
3. Require a clean `openclaw secrets audit --check` and a configured-model request.

## Boundary

This host has no TPM and its systemd host key is stored on non-encrypted media. The ciphertext is safe to commit for repository-exposure resistance. Full-disk encryption or a TPM is required for stronger host-theft resistance. The root-mode OpenClaw process can access its own runtime credential, so SecretRefs are storage protection rather than root-process isolation.
## OAuth cleanup

On 2026-08-21, the unused `openai:default` OAuth profile and its `auth.order.openai` reference were removed. The active `openai-codex/gpt-5.5` route continues to use the encrypted ccnode API credential. The removal is implemented by the idempotent `scripts/openclaw/remove_legacy_openai_oauth.py` migration.
