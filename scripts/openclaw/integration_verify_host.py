#!/usr/bin/env python3
"""
宿主机集成验证（可选 SSH）：不依赖人工在 Discord 里发消息。

默认从环境变量读取 SSH 参数，避免把密码写进仓库：
  SPRINGMONKEY_SSH_HOST   默认 ccnode.briconbric.com
  SPRINGMONKEY_SSH_PORT   默认 8822
  SPRINGMONKEY_SSH_USER   默认 root
  SPRINGMONKEY_SSH_PASSWORD  必填（或扩展为密钥登录）
  SPRINGMONKEY_REPO         默认 /var/lib/openclaw/repos/SpringMonkey

步骤：
  1) git pull main（可选 --no-pull）
  2) 应用 v5 补丁 + restart openclaw（--apply-v5）
  3) dist 中应含 bypass classifier 字符串
  4) runuser -u openclaw 执行 test_cron_run_cli.sh

用法示例：
  SPRINGMONKEY_SSH_PASSWORD='***' python3 scripts/openclaw/integration_verify_host.py --apply-v5
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    import paramiko
except ImportError:
    paramiko = None  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-pull", action="store_true")
    parser.add_argument("--apply-v5", action="store_true", help="run patch v5 + systemctl restart openclaw")
    parser.add_argument("--skip-cron-cli", action="store_true")
    args = parser.parse_args()

    if paramiko is None:
        print("FAIL: pip install paramiko", file=sys.stderr)
        return 2

    host = os.environ.get("SPRINGMONKEY_SSH_HOST", "ccnode.briconbric.com")
    port = int(os.environ.get("SPRINGMONKEY_SSH_PORT", "8822"))
    user = os.environ.get("SPRINGMONKEY_SSH_USER", "root")
    password = os.environ.get("SPRINGMONKEY_SSH_PASSWORD", "")
    repo = os.environ.get("SPRINGMONKEY_REPO", "/var/lib/openclaw/repos/SpringMonkey")

    if not password:
        print("FAIL: set SPRINGMONKEY_SSH_PASSWORD", file=sys.stderr)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, port=port, username=user, password=password, timeout=45)

    def run(cmd: str, timeout: int = 300) -> tuple[int, str]:
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return code, out + err

    try:
        if not args.no_pull:
            code, out = run(
                f"git config --global --add safe.directory {repo} 2>/dev/null; true; "
                f"cd {repo} && git fetch origin && git checkout main && git pull --ff-only origin main"
            )
            print(out)
            if code != 0:
                return code

        if args.apply_v5:
            code, out = run(f"cd {repo} && python3 scripts/openclaw/patch_news_router_v5.py")
            print(out)
            if code != 0:
                return code
            code, out = run("systemctl restart openclaw.service && systemctl is-active openclaw.service")
            print(out)
            if code != 0:
                return code

        code, out = run(
            "grep -c 'bypass classifier' /usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js || true"
        )
        print("bypass_classifier_hits:", out.strip())
        if not out.strip().isdigit() or int(out.strip()) < 1:
            print("FAIL: v5 string not in dist (run with --apply-v5)", file=sys.stderr)
            return 5

        if not args.skip_cron_cli:
            code, out = run(
                f"runuser -u openclaw -- env HOME=/var/lib/openclaw bash {repo}/scripts/openclaw/test_cron_run_cli.sh",
                timeout=240,
            )
            print(out)
            if code != 0:
                return code

        print("INTEGRATION_OK")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
