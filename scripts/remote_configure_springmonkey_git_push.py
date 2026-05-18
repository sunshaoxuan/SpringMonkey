#!/usr/bin/env python3
"""Configure the remote SpringMonkey checkout to use its GitHub deploy key.

The OpenClaw host has a writable deploy key under /var/lib/openclaw/.ssh, but
some older maintenance scripts changed origin back to plain HTTPS. That lets
root/local operators fetch, but autonomous non-interactive pushes fail with:

    fatal: could not read Username for 'https://github.com'
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint

HOST = "ccnode.briconbric.com"
PORT = 8822
USER = "root"
REPO = "/var/lib/openclaw/repos/SpringMonkey"
SSH_CONFIG = "/var/lib/openclaw/.ssh/config"
SSH_REMOTE = "git@github-springmonkey:sunshaoxuan/SpringMonkey.git"


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1

    try:
        import paramiko
    except ImportError:
        print("Missing paramiko. Install scripts/requirements-ssh.txt.", file=sys.stderr)
        return 1

    remote = f"""
set -e
cd {REPO}
git remote set-url origin {SSH_REMOTE}
git config core.sshCommand 'ssh -F {SSH_CONFIG}'
git ls-remote origin HEAD
git push --dry-run origin main
git remote -v
git status -sb
"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=60, allow_agent=False, look_for_keys=False)
    _stdin, stdout, stderr = client.exec_command(remote, get_pty=True, timeout=180)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    client.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
