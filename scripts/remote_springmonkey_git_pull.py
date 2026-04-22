#!/usr/bin/env python3
"""
在汤猴网关宿主机上对 SpringMonkey 仓库执行 git fetch + merge（可选 merge 后重启 openclaw）。

典型流程（与 docs/ops/TOOLS_REGISTRY.md §7 一致）：
  本地改完 push → 本脚本远程 fetch/merge → 按需 apply_news_config / 补丁 → 重启服务。

环境变量：
  OPENCLAW_SSH_PASSWORD 或 SSH_ROOT_PASSWORD — root SSH
  OPENCLAW_RESTART_AFTER_PULL — 设为 "1" 或 "true" 时在 merge 成功后执行 systemctl restart openclaw.service
  SPRINGMONKEY_REPO_PATH — 可选，默认 /var/lib/openclaw/repos/SpringMonkey

依赖：paramiko（见 requirements-ssh.txt）
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
DEFAULT_REPO = "/var/lib/openclaw/repos/SpringMonkey"


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1

    repo = os.environ.get("SPRINGMONKEY_REPO_PATH", DEFAULT_REPO).strip() or DEFAULT_REPO
    restart = os.environ.get("OPENCLAW_RESTART_AFTER_PULL", "").lower() in ("1", "true", "yes")

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

    restart_block = ""
    if restart:
        restart_block = """
echo "=== restart openclaw.service ==="
systemctl restart openclaw.service
sleep 2
systemctl is-active openclaw.service || true
"""

    remote = f"""
set -e
REPO="{repo}"
echo "=== git fetch/merge in $REPO ==="
cd "$REPO"
git status -sb || true
if [ -n "$(git status --porcelain)" ]; then
  STASH_NAME="autostash-before-origin-main-merge-$(date +%Y%m%d-%H%M%S)"
  echo "=== stash dirty repo state: $STASH_NAME ==="
  git stash push -u -m "$STASH_NAME"
fi
git fetch origin
git merge --no-edit origin/main
git status -sb
{restart_block}
echo "DONE"
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
