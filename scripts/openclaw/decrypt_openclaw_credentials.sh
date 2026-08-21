#!/usr/bin/env bash
set -euo pipefail

readonly CIPHERTEXT="/var/lib/openclaw/repos/SpringMonkey/config/openclaw/openclaw-secrets.json.cred"
readonly RUNTIME_DIR="/run/credentials/openclaw.service"
readonly RUNTIME_FILE="$RUNTIME_DIR/openclaw-secrets.json"

[[ -f "$CIPHERTEXT" ]]
install -d -m 0700 "$RUNTIME_DIR"
scratch="$(mktemp -d /run/openclaw-credential-source.XXXXXX)"
temporary="$(mktemp "$RUNTIME_DIR/.openclaw-secrets.XXXXXX")"
cleanup() {
  rm -f -- "$temporary"
  rm -rf -- "$scratch"
}
trap cleanup EXIT
install -m 0600 "$CIPHERTEXT" "$scratch/openclaw-secrets.json"
systemd-creds decrypt "$scratch/openclaw-secrets.json" - > "$temporary"
chmod 0400 "$temporary"
mv -f -- "$temporary" "$RUNTIME_FILE"
