#!/usr/bin/env python3
"""
在汤猴宿主机（经 SSH）上为 LINE Webhook 增加 frp TCP 映射：
  本机 127.0.0.1:<LOCAL_PORT> -> frps 公网端口 <REMOTE_PORT>（默认 18789 -> 31879）。

前置（见 docs/ops/SSH_TOOLCHAIN.md、HOST_ACCESS.md）：
  OPENCLAW_SSH_PASSWORD 或 SSH_ROOT_PASSWORD
可选：
  FRPC_LINE_LOCAL_PORT  默认 18789
  FRPC_LINE_REMOTE_PORT 默认 31879
  OPENCLAW_SSH_HOST     默认 ccnode.briconbric.com
  OPENCLAW_SSH_PORT     默认 8822

说明：frp 0.52+ 常用 `[[proxies]]` 块；若检测到旧式 `[proxies.xxx]` 且无 `[[proxies]]`，则追加旧式 `[proxies.line_webhook]` 段。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint

# 与 remote_diag_openclaw_webhook.py 等保持一致，可被环境变量覆盖
HOST = os.environ.get("OPENCLAW_SSH_HOST", "ccnode.briconbric.com")
PORT = int(os.environ.get("OPENCLAW_SSH_PORT", "8822"))
USER = "root"

DEFAULT_LOCAL = 18789
DEFAULT_REMOTE = 31879


def _remote_py(lp: int, rp: int) -> str:
    """远端 python3 执行的源码（经 heredoc 传入）。外层 f-string 只替换端口数字。"""
    return f'''import shutil
from pathlib import Path
from datetime import datetime

p = Path("/etc/frp/frpc.toml")
if not p.is_file():
    raise SystemExit("missing /etc/frp/frpc.toml")

text = p.read_text(encoding="utf-8")
ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
bak = Path("/etc/frp/frpc.toml.bak-line-webhook-" + ts)
shutil.copy2(p, bak)
print("backup:", bak)

lines = text.splitlines()
new_lines = []
i = 0
updated = False

while i < len(lines):
    line = lines[i]
    s = line.strip()

    # toml array-of-tables: [[proxies]] + name="line_webhook"
    if s == "[[proxies]]":
        j = i + 1
        has_name = False
        while j < len(lines):
            sj = lines[j].strip()
            if sj.startswith("[[") or (sj.startswith("[") and not sj.startswith("[[")):
                break
            if sj.startswith("name") and "line_webhook" in sj:
                has_name = True
            j += 1
        if has_name:
            new_lines.extend(
                [
                    "[[proxies]]",
                    'name = "line_webhook"',
                    'type = "tcp"',
                    'localIP = "127.0.0.1"',
                    "localPort = " + str({lp}),
                    "remotePort = " + str({rp}),
                ]
            )
            updated = True
            i = j
            continue

    # legacy section: [proxies.line_webhook]
    if s == "[proxies.line_webhook]":
        j = i + 1
        while j < len(lines):
            sj = lines[j].strip()
            if sj.startswith("["):
                break
            j += 1
        new_lines.extend(
            [
                "[proxies.line_webhook]",
                'type = "tcp"',
                'localIP = "127.0.0.1"',
                "localPort = " + str({lp}),
                "remotePort = " + str({rp}),
            ]
        )
        updated = True
        i = j
        continue

    new_lines.append(line)
    i += 1

if not updated:
    use_new = "[[proxies]]" in text
    if use_new:
        block = [
            "[[proxies]]",
            'name = "line_webhook"',
            'type = "tcp"',
            'localIP = "127.0.0.1"',
            "localPort = " + str({lp}),
            "remotePort = " + str({rp}),
        ]
    else:
        block = [
            "[proxies.line_webhook]",
            'type = "tcp"',
            'localIP = "127.0.0.1"',
            "localPort = " + str({lp}),
            "remotePort = " + str({rp}),
        ]
    new_lines.extend([""] + block)
    print("APPENDED line_webhook mapping")
else:
    print("UPDATED existing line_webhook mapping")

# 必须用真实换行写入 TOML；勿用字面量 \\n 两个字符，否则 frpc 无法解析、frps 不会出现端口
p.write_text((chr(10)).join(new_lines).rstrip() + chr(10), encoding="utf-8")
raise SystemExit(0)
'''


def _verify_shell(local_port: int, remote_port: int) -> str:
    return f"""
set +e
echo "=== systemctl restart frpc ==="
systemctl restart frpc.service 2>&1
sleep 2
systemctl is-active frpc.service 2>&1
echo "=== ss 本机仅应看到 localPort={local_port}（remotePort 在 frps/ccnode 上监听，本机不会出现 :{remote_port}）==="
ss -tlnp 2>/dev/null | grep -E ':{local_port}' || true
echo "=== frpc 最近日志（查 login/proxy/error）==="
journalctl -u frpc.service -n 40 --no-pager 2>&1
echo "=== curl 本机 gateway /line/webhook ==="
curl -sS -o /dev/null -w "HTTP %{{http_code}} http://127.0.0.1:{local_port}/line/webhook\\n" --connect-timeout 5 "http://127.0.0.1:{local_port}/line/webhook" 2>&1
echo "=== 从本机试打 frps 域名:remotePort（若 frpc 已注册，ccnode 应对应端口有监听）==="
curl -sS -o /dev/null -w "HTTP %{{http_code}} http://ccnode.briconbric.com:{remote_port}/line/webhook\\n" --connect-timeout 5 "http://ccnode.briconbric.com:{remote_port}/line/webhook" 2>&1
echo "DONE"
"""


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        local_port = int(os.environ.get("FRPC_LINE_LOCAL_PORT", str(DEFAULT_LOCAL)))
        remote_port = int(os.environ.get("FRPC_LINE_REMOTE_PORT", str(DEFAULT_REMOTE)))
    except ValueError:
        print("FRPC_LINE_LOCAL_PORT / FRPC_LINE_REMOTE_PORT 必须是整数", file=sys.stderr)
        return 1

    try:
        import paramiko
    except ImportError:
        print(
            "缺少 paramiko。请执行：python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt",
            file=sys.stderr,
        )
        return 1

    remote_edit = _remote_py(local_port, remote_port)
    verify = _verify_shell(local_port, remote_port)
    bundle = f"""
set -e
python3 <<'PY'
{remote_edit}
PY
RC=$?
if [ "$RC" -ne 0 ]; then exit "$RC"; fi
{verify}
"""

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST,
        port=PORT,
        username=USER,
        password=pw,
        timeout=120,
        allow_agent=False,
        look_for_keys=False,
    )
    stdin, stdout, stderr = client.exec_command(bundle, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    ok = "DONE" in out
    if ok:
        print(
            f"\n[提示] LINE Webhook 对外 URL 形如："
            f"https://<你的域名>/line/webhook ；"
            f"反代上游可指向 ccnode 公网 TCP 端口 {remote_port}（HTTP 由你方 Nginx/Caddy + Let's Encrypt 终止）。",
            file=sys.stderr,
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
