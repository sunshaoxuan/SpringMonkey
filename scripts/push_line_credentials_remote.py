#!/usr/bin/env python3
"""
将 LINE Channel access token 与 Channel secret 写入远端 OpenClaw 主机并启用 channels.line。
仅通过环境变量读取机密，请勿把密钥写入本文件或提交到 Git。

环境变量：
  OPENCLAW_SSH_PASSWORD 或 SSH_ROOT_PASSWORD — root SSH 密码
  LINE_CHANNEL_ACCESS_TOKEN
  LINE_CHANNEL_SECRET

用法（在能访问 ccnode.briconbric.com:8822 的机器上）：
  export OPENCLAW_SSH_PASSWORD='...'
  export LINE_CHANNEL_ACCESS_TOKEN='...'
  export LINE_CHANNEL_SECRET='...'
  python3 scripts/push_line_credentials_remote.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint

HOST = "ccnode.briconbric.com"
PORT = 8822
USER = "root"


def main() -> int:
    pw = load_openclaw_ssh_password()
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    secret = os.environ.get("LINE_CHANNEL_SECRET", "").strip()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    if not token or not secret:
        print("缺少 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_CHANNEL_SECRET", file=sys.stderr)
        return 1

    try:
        import paramiko
    except ImportError:
        print(
            "缺少 paramiko。请执行一次：\n"
            "  python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt\n"
            "说明：SpringMonkey/docs/ops/SSH_TOOLCHAIN.md",
            file=sys.stderr,
        )
        return 1

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST,
        port=PORT,
        username=USER,
        password=pw,
        timeout=45,
        allow_agent=False,
        look_for_keys=False,
    )

    # 使用 base64 避免 heredoc/shell 对特殊字符的破坏
    import base64

    tb = base64.b64encode(token.encode("utf-8")).decode("ascii")
    sb = base64.b64encode(secret.encode("utf-8")).decode("ascii")

    remote = r"""set -e
OC_HOME="/var/lib/openclaw"
SECDIR="$OC_HOME/.openclaw/secrets"
install -d -m 700 -o openclaw -g openclaw "$SECDIR"
echo '__TB__' | base64 -d | sudo -u openclaw tee "$SECDIR/line-channel-access-token.txt" >/dev/null
echo '__SB__' | base64 -d | sudo -u openclaw tee "$SECDIR/line-channel-secret.txt" >/dev/null
chmod 600 "$SECDIR/line-channel-access-token.txt" "$SECDIR/line-channel-secret.txt"
chown openclaw:openclaw "$SECDIR/line-channel-access-token.txt" "$SECDIR/line-channel-secret.txt"
sudo -u openclaw python3 <<'PY'
import json
from pathlib import Path
p = Path("/var/lib/openclaw/.openclaw/openclaw.json")
with p.open(encoding="utf-8") as f:
    data = json.load(f)
data.setdefault("channels", {})
data["channels"]["line"] = {
    "enabled": True,
    "dmPolicy": "pairing",
    "tokenFile": "/var/lib/openclaw/.openclaw/secrets/line-channel-access-token.txt",
    "secretFile": "/var/lib/openclaw/.openclaw/secrets/line-channel-secret.txt",
}
with p.open("w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
sudo -u openclaw python3 -m json.tool "$OC_HOME/.openclaw/openclaw.json" >/dev/null
systemctl restart openclaw.service
sleep 2
systemctl is-active openclaw.service || true
journalctl -u openclaw -n 30 --no-pager || true
echo DONE
"""
    remote = remote.replace("__TB__", tb).replace("__SB__", sb)

    stdin, stdout, stderr = client.exec_command(remote, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
