# OpenClaw encrypted SecretRef credentials

The active service receives `openclaw-secrets.json` through systemd `LoadCredentialEncrypted`. The tracked `config/openclaw/openclaw-secrets.json.cred` is host-bound ciphertext generated with `systemd-creds encrypt --with-key=host`.

OpenClaw resolves supported SecretRefs from `/run/credentials/openclaw.service/openclaw-secrets.json` into an in-memory snapshot. The migration plan contains refs only. Intent, research, and model-fallback helpers read the same runtime credential when no explicit operator override is supplied. Ollama uses its `auth-profiles` SecretRef as the single credential owner, so no redundant provider `apiKey` is persisted.

## Rotation

1. Encrypt a replacement payload with `--with-key=host --name=openclaw-secrets.json`.
2. Replace the `.cred` file, reload systemd, restart the service, and run `openclaw secrets reload`.
3. Require a clean `openclaw secrets audit --check` and a configured-model request.

## Boundary

This host has no TPM and its systemd host key is stored on non-encrypted media. The ciphertext is safe to commit for repository-exposure resistance. Full-disk encryption or a TPM is required for stronger host-theft resistance. The root-mode OpenClaw process can access its own runtime credential, so SecretRefs are storage protection rather than root-process isolation.
