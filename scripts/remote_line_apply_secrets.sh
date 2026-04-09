#!/usr/bin/env bash
# 在 OpenClaw 网关宿主机上以 root 执行。
# 通过环境变量写入 LINE 密钥并启用 channels.line（不落盘到本仓库）。
#
# 用法（在服务器上）：
#   export LINE_CHANNEL_ACCESS_TOKEN='从 LINE Developers → Messaging API 签发的长期 Token'
#   export LINE_CHANNEL_SECRET='Basic settings 里的 Channel secret'
#   bash remote_line_apply_secrets.sh
#
# 注意：Channel ID 不是 Access Token，不要填错。

set -euo pipefail

OC_HOME="/var/lib/openclaw"
CFG="${OC_HOME}/.openclaw/openclaw.json"
SECDIR="${OC_HOME}/.openclaw/secrets"
TOKEN_FILE="${SECDIR}/line-channel-access-token.txt"
SECRET_FILE="${SECDIR}/line-channel-secret.txt"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "请以 root 执行" >&2
  exit 1
fi

if [[ -z "${LINE_CHANNEL_ACCESS_TOKEN:-}" || -z "${LINE_CHANNEL_SECRET:-}" ]]; then
  echo "请设置环境变量 LINE_CHANNEL_ACCESS_TOKEN 与 LINE_CHANNEL_SECRET" >&2
  exit 1
fi

install -d -m 700 -o openclaw -g openclaw "$SECDIR"

printf '%s\n' "$LINE_CHANNEL_ACCESS_TOKEN" | sudo -u openclaw tee "$TOKEN_FILE" >/dev/null
printf '%s\n' "$LINE_CHANNEL_SECRET" | sudo -u openclaw tee "$SECRET_FILE" >/dev/null
chmod 600 "$TOKEN_FILE" "$SECRET_FILE"
chown openclaw:openclaw "$TOKEN_FILE" "$SECRET_FILE"

sudo -u openclaw python3 <<'PY'
import json
from pathlib import Path
p = Path("/var/lib/openclaw/.openclaw/openclaw.json")
with p.open(encoding="utf-8") as f:
    data = json.load(f)
data.setdefault("channels", {})
line = data["channels"].setdefault("line", {})
line["enabled"] = True
line["dmPolicy"] = "pairing"
line["tokenFile"] = "/var/lib/openclaw/.openclaw/secrets/line-channel-access-token.txt"
line["secretFile"] = "/var/lib/openclaw/.openclaw/secrets/line-channel-secret.txt"
data["channels"]["line"] = line
with p.open("w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY

sudo -u openclaw python3 -m json.tool "$CFG" >/dev/null
echo "JSON OK"

systemctl restart openclaw.service
sleep 2
systemctl is-active openclaw.service || true
journalctl -u openclaw -n 40 --no-pager || true

echo "LINE 通道已启用（channels.line.enabled=true）。若日志报错请检查 Token 是否为 Messaging API 的长期 Access Token。"
