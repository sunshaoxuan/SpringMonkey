#!/usr/bin/env python3
"""
宿主机集成验证（SSH）：策略补丁契约 + cron CLI，尽量避免「只能靠人工在 Discord 试」才发现问题。

环境变量：SPRINGMONKEY_SSH_*、SPRINGMONKEY_REPO、SPRINGMONKEY_POST_RESTART_WAIT_SEC（同前）

常用：
  --full-contract --no-pull   仅校验 dist 契约 + 单元脚本 + cron + 服务存活（推荐每次发版后 CI/本地一键）
  --full-contract --e2e-news-discord   拉代码后跑契约，再 ensure/apply/verify + 长跑 cron 直至 Discord 投递（默认 7200s）
  --apply-v6 --apply-v7       打补丁并重启后再跑契约（新环境或升级）

无参数调用本脚本时，若通过 _run_integration_with_hostaccess.py 包装，将默认 --full-contract --no-pull。
"""
from __future__ import annotations

import argparse
import json
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
    parser.add_argument(
        "--full-contract",
        action="store_true",
        help="dist 全量契约（v5–v7 + 禁止 spawnSync openclaw cron + 可选日志告警）",
    )
    parser.add_argument(
        "--fail-on-recent-deadlock-log",
        action="store_true",
        help="journalctl 最近 400 行若含 spawnSync openclaw ETIMEDOUT 则失败（易误伤旧日志，默认关）",
    )
    parser.add_argument("--skip-cron-cli", action="store_true")
    parser.add_argument(
        "--e2e-news-discord",
        action="store_true",
        help="跳过 180s 短冒烟，改为长跑 openclaw cron run 新闻任务（直至投递 Discord，默认超时 7200s）",
    )
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

    full = args.full_contract or os.environ.get("SPRINGMONKEY_FULL_CONTRACT", "").lower() in (
        "1",
        "true",
        "yes",
    )

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

    def count_grep(pat: str) -> int:
        """在远端用 Python 统计子串出现次数，避免 shell 引号问题。"""
        one_liner = (
            f"import pathlib;t=pathlib.Path({json.dumps(DIST)}).read_text(encoding='utf-8');"
            f"print(t.count({json.dumps(pat)}))"
        )
        code, o = run(f"python3 -c {json.dumps(one_liner)}", timeout=120)
        if code != 0:
            return -1
        try:
            return int(o.strip().split()[-1])
        except ValueError:
            return -1

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

        # —— 契约校验 ——
        bc = count_grep("bypass classifier")
        print("bypass_classifier_hits:", bc)
        if bc < 0:
            print("FAIL: could not count in dist (path/read error)", file=sys.stderr)
            return 4
        if bc < 1:
            print("FAIL: v5 bypass string missing in dist", file=sys.stderr)
            return 5

        v6_needed = (
            full
            or args.apply_v6
            or os.environ.get("SPRINGMONKEY_REQUIRE_V6_MARKERS", "").lower() in ("1", "true", "yes")
        )
        if v6_needed:
            for label, pat in (
                ("model_fallback", "model-fallback"),
                ("codex_fallback_log", "fallback to codex"),
                ("catch_degraded", "primary route failed"),
            ):
                n = count_grep(pat)
                print(f"{label}_hits:", n)
                if n < 0:
                    print(f"FAIL: could not count for {label}", file=sys.stderr)
                    return 6
                if n < 1:
                    print(f"FAIL: expected '{pat}' in dist", file=sys.stderr)
                    return 6

        v7_needed = (
            full
            or args.apply_v7
            or os.environ.get("SPRINGMONKEY_REQUIRE_V7_MARKERS", "").lower() in ("1", "true", "yes")
        )
        if v7_needed:
            n = count_grep("execResult = await new Promise")
            print("async_cron_spawn_hits:", n)
            if n < 0:
                print("FAIL: could not count v7 marker", file=sys.stderr)
                return 7
            if n < 1:
                print("FAIL: v7 async spawn not in dist", file=sys.stderr)
                return 7

        if full or v7_needed:
            # 网关中 queueFormalNewsJobRun 不得再 spawnSync openclaw cron（自死锁）
            bad = count_grep('spawnSync("openclaw", ["cron"')
            print("forbidden_spawnSync_openclaw_cron_hits:", bad)
            if bad < 0:
                print("FAIL: could not count forbidden spawnSync pattern", file=sys.stderr)
                return 8
            if bad != 0:
                print(
                    "FAIL: dist still contains spawnSync(openclaw cron) — v7 not applied or regressed",
                    file=sys.stderr,
                )
                return 8

        if full:
            code, out = run(f"cd {repo} && python3 scripts/openclaw/test_manual_news_heuristics.py")
            print(out)
            if code != 0:
                return code

        code, out = run("systemctl is-active openclaw.service")
        print("openclaw_active:", out.strip())
        if code != 0 or "active" not in out:
            print("FAIL: openclaw.service not active", file=sys.stderr)
            return 9

        if args.fail_on_recent_deadlock_log:
            _, o = run(
                "journalctl -u openclaw.service -n 400 --no-pager | grep -F 'spawnSync openclaw ETIMEDOUT' | tail -3"
            )
            if o.strip():
                print("FAIL: recent journal still shows spawnSync openclaw ETIMEDOUT:\n", o, file=sys.stderr)
                return 10

        run_quick_cron = not args.skip_cron_cli and not args.e2e_news_discord
        if run_quick_cron:
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

        if args.e2e_news_discord:
            for label, prep in (
                ("ensure_daily_memory", f"cd {repo} && python3 scripts/news/ensure_daily_memory.py"),
                ("apply_news_config", f"cd {repo} && python3 scripts/news/apply_news_config.py"),
                ("verify_runtime_readiness", f"cd {repo} && python3 scripts/news/verify_runtime_readiness.py"),
            ):
                code, out = run(prep, timeout=180)
                print(out)
                if code != 0:
                    print(f"FAIL: {label} exit {code}", file=sys.stderr)
                    return 12
            e2e_timeout = int(os.environ.get("SPRINGMONKEY_E2E_CRON_TIMEOUT_SEC", "7200"))
            job_name = os.environ.get("NEWS_CRON_JOB_NAME", "news-digest-jst-1700")
            ssh_budget = min(e2e_timeout + 600, 14_400)
            print(
                f"[integration] e2e-news-discord: cron run job={job_name} timeout={e2e_timeout}s (ssh {ssh_budget}s)..."
            )
            e2e_cmd = (
                f"runuser -u openclaw -- env HOME=/var/lib/openclaw "
                f"CRON_RUN_TIMEOUT_SEC={e2e_timeout} NEWS_CRON_JOB_NAME={job_name} "
                f"bash {repo}/scripts/openclaw/test_cron_run_cli.sh"
            )
            code, last_out = run(e2e_cmd, timeout=ssh_budget)
            print(last_out)
            if code != 0:
                print("FAIL: e2e-news-discord cron run", file=sys.stderr)
                return 11

            # cron run 只保证「入队」；子进程 stdout 未必进 journal，默认不盲等日志
            wait_sec = int(os.environ.get("SPRINGMONKEY_E2E_WAIT_PIPE_SEC", "0"))
            if wait_sec > 0:
                print(
                    f"[integration] polling journal for PIPELINE_OK (max {wait_sec}s; "
                    "若网关不落盘该串则会超时，仍以 Discord 为准)..."
                )
                deadline = time.time() + wait_sec
                found = False
                while time.time() < deadline:
                    code, o = run(
                        "journalctl -u openclaw.service --since '15 minutes ago' --no-pager 2>/dev/null | "
                        "grep -E 'PIPELINE_OK|run_news_pipeline\\.py|final_broadcast' | tail -3",
                        timeout=90,
                    )
                    if "PIPELINE_OK" in o or "run_news_pipeline.py" in o:
                        print("[integration] journal snippet:\n", o.strip()[:800])
                        found = True
                        break
                    time.sleep(20)
                if not found:
                    print(
                        "[integration] 未在 journal 中匹配到流水线关键字（常见）；"
                        "请直接查看 Discord 是否已出现新闻简报或网关会话回复。",
                        file=sys.stderr,
                    )

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
