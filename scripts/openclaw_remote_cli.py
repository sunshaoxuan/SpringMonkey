#!/usr/bin/env python3
"""
统一入口：从本机调用各远程 OpenClaw 运维脚本（子进程），避免记长路径。

用法示例：
  set OPENCLAW_SSH_PASSWORD=...
  python SpringMonkey/scripts/openclaw_remote_cli.py diag
  python SpringMonkey/scripts/openclaw_remote_cli.py doctor
  python SpringMonkey/scripts/openclaw_remote_cli.py line-install
  set LINE_CHANNEL_ACCESS_TOKEN=...
  set LINE_CHANNEL_SECRET=...
  python SpringMonkey/scripts/openclaw_remote_cli.py line-push

子命令与脚本对应关系见 docs/ops/TOOLS_REGISTRY.md
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# 子命令名 -> 脚本文件名（与本目录下现有脚本一致）
TOOLS: dict[str, str] = {
    "git-pull": "remote_springmonkey_git_pull.py",
    "diag": "remote_diag_openclaw_webhook.py",
    "doctor": "remote_openclaw_doctor_fix.py",
    "shared-capabilities": "remote_enable_shared_channel_capabilities.py",
    "browser-capabilities": "remote_enable_browser_capabilities.py",
    "browser-guardrails": "remote_install_browser_guardrails.py",
    "browser-backend": "remote_enable_persistent_browser_backend.py",
    "browser-human-helper": "remote_install_browser_human_control_helper.py",
    "reply-media-repair": "remote_repair_reply_media_images.py",
    "capability-awareness": "remote_refresh_capability_awareness.py",
    "memory-repair": "remote_repair_memory_lancedb.py",
    "memory-guard": "remote_install_memory_lancedb_guard.py",
    "agent-society-runtime": "remote_install_agent_society_runtime_guard.py",
    "agent-society-guard": "remote_install_agent_society_startup_guard.py",
    "intl-channels": "remote_enable_international_channels.py",
    "line-install": "remote_install_line_plugin_fix.py",
    "line-push": "push_line_credentials_remote.py",
    "frpc-line": "remote_frpc_line_webhook_map.py",
    "frpc-diag": "remote_diag_frpc_tunnel.py",
    "frpc-cat": "remote_cat_frpc_config.py",
    "frpc-restart": "remote_restart_frpc.py",
    "line-diag": "remote_diag_line_support.py",
    "line-force-open": "remote_line_force_open.py",
    "line-approve": "remote_line_pairing_approve.py",
    "line-connect": "remote_line_connect_now.py",
    "stabilize": "remote_stabilize_host.py",
    "cron-run": "remote_cron_run_by_name.py",
    "cron-enable": "remote_enable_cron_jobs.py",
}


def run_script(name: str, extra_args: list[str] | None = None) -> int:
    script = SCRIPT_DIR / TOOLS[name]
    if not script.is_file():
        print(f"找不到脚本: {script}", file=sys.stderr)
        return 2
    cmd = [sys.executable, str(script)]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.call(cmd)


def cmd_recover() -> int:
    """diag 后 doctor：只处理配置类问题，不自动改 LINE。"""
    r1 = run_script("diag")
    if r1 != 0:
        print("[recover] diag 失败，停止。", file=sys.stderr)
        return r1
    return run_script("doctor")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SpringMonkey 远程 OpenClaw 工具统一入口（委托本目录下各脚本）。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for cmd in TOOLS:
        p = sub.add_parser(cmd, help=f"运行 {TOOLS[cmd]}")
        p.add_argument("extra", nargs="*", help="传递给脚本的额外参数")
        p.set_defaults(_fn=lambda args, c=cmd: run_script(c, args.extra))

    sub.add_parser("list", help="列出子命令与对应脚本").set_defaults(_fn=lambda args: list_tools())
    sub.add_parser(
        "recover",
        help="依次执行 diag + doctor（配置修复流水线，不执行 line-push）",
    ).set_defaults(_fn=lambda args: cmd_recover())

    args = parser.parse_args()
    fn = getattr(args, "_fn", None)
    if fn is None:
        parser.print_help()
        return 1
    return int(fn(args))


def list_tools() -> int:
    print("子命令 -> 脚本")
    for k, v in sorted(TOOLS.items()):
        print(f"  {k:12} -> {v}")
    print("\nrecover -> diag 然后 doctor")
    print(
        "环境变量: OPENCLAW_SSH_PASSWORD；git-pull 可选 OPENCLAW_RESTART_AFTER_PULL=1；"
        "line-push 另需 LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET；"
        "line-approve 需 LINE_PAIRING_CODE 或改用: python .../remote_line_pairing_approve.py <CODE>"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
