#!/usr/bin/env python3
"""
宿主机集成验证（可选 SSH）：不依赖人工在 Discord 里发消息。

环境变量：
  SPRINGMONKEY_SSH_HOST / PORT / USER / PASSWORD / REPO（同前）
  SPRINGMONKEY_POST_RESTART_WAIT_SEC  默认 25

步骤：
  1) git pull main（可选 --no-pull）
  2) --apply-v5：打 v5 补丁并重启（由旧基线升级时）
  3) --apply-v6：打 v6（Ollama 超时 + Codex 回退 + generate 探针）并重启
  4) --apply-v7：cron run 改为 async spawn（修复网关内 spawnSync 自死锁）
  5) 校验 dist 含关键标记；runuser 跑 test_cron_run_cli.sh

推荐一键：`--apply-v6 --apply-v7` 或仅 `--apply-v7`（若 v6 已在 dist）。

用法：
  SPRINGMONKEY_SSH_PASSWORD='***' python3 scripts/openclaw/integration_verify_host.py --apply-v6 --apply-v7
"""
from __future__ import annotations

import argparse
import os
import sys
import time

try:
    import paramiko
except ImportError:
    paramiko = None  # type: ignore

DIST = "/usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-pull", action="store_true")
    parser.add_argument("--apply-v5", action="store_true")
    parser.add_argument("--apply-v6", action="store_true")
    parser.add_argument("--apply-v7", action="store_true")
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

    def restart_and_wait() -> int:
        code, out = run("systemctl restart openclaw.service && systemctl is-active openclaw.service")
        print(out)
        if code != 0:
            return code
        wait = int(os.environ.get("SPRINGMONKEY_POST_RESTART_WAIT_SEC", "25"))
        print(f"[integration] waiting {wait}s for gateway...")
        time.sleep(wait)
        return 0

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
            if restart_and_wait() != 0:
                return 1

        if args.apply_v6:
            code, out = run(f"cd {repo} && python3 scripts/openclaw/patch_news_router_v6.py")
            print(out)
            if code != 0:
                return code
            if restart_and_wait() != 0:
                return 1

        if args.apply_v7:
            code, out = run(f"cd {repo} && python3 scripts/openclaw/patch_news_router_v7.py")
            print(out)
            if code != 0:
                return code
            if restart_and_wait() != 0:
                return 1

        def count_grep(pat: str) -> int:
            _, o = run(f"grep -c '{pat}' {DIST} 2>/dev/null || echo 0")
            try:
                return int(o.strip().split()[-1])
            except ValueError:
                return 0

        bc = count_grep("bypass classifier")
        print("bypass_classifier_hits:", bc)
        if bc < 1:
            print("FAIL: v5 bypass string missing in dist", file=sys.stderr)
            return 5

        if args.apply_v6 or os.environ.get("SPRINGMONKEY_REQUIRE_V6_MARKERS", "").lower() in ("1", "true", "yes"):
            for label, pat in (
                ("model_fallback", "model-fallback"),
                ("codex_fallback_log", "fallback to codex"),
                ("catch_degraded", "primary route failed"),
            ):
                n = count_grep(pat)
                print(f"{label}_hits:", n)
                if n < 1:
                    print(f"FAIL: expected '{pat}' in dist (run --apply-v6)", file=sys.stderr)
                    return 6

        if args.apply_v7 or os.environ.get("SPRINGMONKEY_REQUIRE_V7_MARKERS", "").lower() in ("1", "true", "yes"):
            n = count_grep("execResult = await new Promise")
            print("async_cron_spawn_hits:", n)
            if n < 1:
                print("FAIL: v7 async spawn not in dist (run --apply-v7)", file=sys.stderr)
                return 7

        if not args.skip_cron_cli:
            last_out = ""
            code = 1
            for attempt in range(1, 4):
                code, last_out = run(
                    f"runuser -u openclaw -- env HOME=/var/lib/openclaw bash {repo}/scripts/openclaw/test_cron_run_cli.sh",
                    timeout=240,
                )
                print(last_out)
                if code == 0:
                    break
                print(f"[integration] cron cli attempt {attempt} failed, retrying in 15s...")
                time.sleep(15)
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
