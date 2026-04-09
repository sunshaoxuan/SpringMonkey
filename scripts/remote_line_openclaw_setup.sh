#!/usr/bin/env bash
# 在 OpenClaw 网关宿主机上以 root 执行（通过 SSH 粘贴或 plink -m）。
# 作用：安装 @openclaw/line、备份 openclaw.json、写入 channels.line（占位密钥文件）、重启 openclaw.service。
# 不含任何密码或 LINE 密钥；填密钥请编辑下方两个 secrets 文件后再把 channels.line.enabled 改为 true。

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

echo "==> 安装 LINE 插件（openclaw 用户）"
if sudo -u openclaw -H bash -lc 'export HOME='"${OC_HOME}"' && cd "$HOME" && command -v openclaw >/dev/null 2>&1'; then
  sudo -u openclaw -H bash -lc 'export HOME='"${OC_HOME}"' && cd "$HOME" && openclaw plugins install @openclaw/line'
else
  echo "未找到 openclaw 命令，尝试 npx …"
  sudo -u openclaw -H bash -lc 'export HOME='"${OC_HOME}"' && cd "$HOME" && npx --yes @openclaw/cli plugins install @openclaw/line'
fi

echo "==> 备份 openclaw.json"
ts="$(date +%Y%m%d_%H%M%S)"
cp -a "$CFG" "${CFG}.bak.${ts}"
echo "备份: ${CFG}.bak.${ts}"

echo "==> 合并 channels.line"
sudo -u openclaw python3 <<'PY'
import json
from pathlib import Path
p = Path("/var/lib/openclaw/.openclaw/openclaw.json")
with p.open(encoding="utf-8") as f:
    data = json.load(f)
data.setdefault("channels", {})
data["channels"]["line"] = {
    "enabled": False,
    "dmPolicy": "pairing",
    "tokenFile": "/var/lib/openclaw/.openclaw/secrets/line-channel-access-token.txt",
    "secretFile": "/var/lib/openclaw/.openclaw/secrets/line-channel-secret.txt",
}
with p.open("w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY

echo "==> 密钥占位文件（请替换为 LINE Developers 真实值后再 enabled: true）"
install -d -m 700 -o openclaw -g openclaw "$SECDIR"
printf '%s\n' 'REPLACE_ME_PASTE_FROM_LINE_DEVELOPERS' | sudo -u openclaw tee "$TOKEN_FILE" >/dev/null
printf '%s\n' 'REPLACE_ME_PASTE_FROM_LINE_DEVELOPERS' | sudo -u openclaw tee "$SECRET_FILE" >/dev/null
chmod 600 "$TOKEN_FILE" "$SECRET_FILE"
chown openclaw:openclaw "$TOKEN_FILE" "$SECRET_FILE"

echo "==> 校验 JSON"
sudo -u openclaw python3 -m json.tool "$CFG" >/dev/null
echo "JSON OK"

echo "==> 重启 openclaw"
systemctl restart openclaw.service
sleep 2
systemctl is-active openclaw.service || true
journalctl -u openclaw -n 25 --no-pager || true

echo ""
echo "完成。下一步："
echo "1) 编辑 $TOKEN_FILE 与 $SECRET_FILE，写入 LINE Channel access token 与 Channel secret（各一行，无多余空格）。"
echo "2) 将 $CFG 中 channels.line.enabled 改为 true（可用相同 python3 片段或 jq）。"
echo "3) systemctl restart openclaw.service"
echo "4) LINE Webhook 需公网 HTTPS 指向 Gateway 的 /line/webhook（当前 Gateway 多为 loopback，需 Nginx/FRP 等）。"
echo ""
