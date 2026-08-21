#!/usr/bin/env bash
set -euo pipefail

readonly RUNTIME_DIR="/run/credentials/openclaw.service"
rm -f -- "$RUNTIME_DIR/openclaw-secrets.json"
rmdir --ignore-fail-on-non-empty "$RUNTIME_DIR" 2>/dev/null || true
