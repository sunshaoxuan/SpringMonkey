#!/usr/bin/env python3
"""SSH 到汤猴宿主机，删除指定 OpenClaw session 映射与 session 文件。"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint

HOST = os.environ.get("OPENCLAW_SSH_HOST", "ccnode.briconbric.com")
PORT = int(os.environ.get("OPENCLAW_SSH_PORT", "8822"))
USER = "root"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Reset one OpenClaw session mapping on the host.")
    p.add_argument("--session-key", required=True, help="Exact session key, for example agent:main:discord:channel:...")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print(
            "缺少 paramiko。请执行一次：\n"
            "  python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt",
            file=sys.stderr,
        )
        return 1

    remote = f"""
set -euo pipefail
python3 <<'PY'
from pathlib import Path
from datetime import datetime
import json
import shutil

session_key = {args.session_key!r}
base = Path("/var/lib/openclaw/.openclaw/agents/main/sessions")
sessions_path = base / "sessions.json"
data = json.loads(sessions_path.read_text(encoding="utf-8"))
entry = data.get(session_key)
if not entry:
    print(json.dumps({{"reset": False, "reason": "SESSION_NOT_FOUND", "sessionKey": session_key}}, ensure_ascii=False))
    raise SystemExit(0)

ts = datetime.now().strftime("%Y%m%d-%H%M%S")
backup = sessions_path.with_name(f"sessions.json.bak-reset-session-{{ts}}")
shutil.copy2(sessions_path, backup)

session_file = entry.get("sessionFile")
data.pop(session_key, None)
sessions_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")

removed_file = False
if session_file:
    path = Path(session_file)
    if path.exists():
        path.rename(path.with_name(path.name + f".bak-reset-{{ts}}"))
        removed_file = True

print(json.dumps({{
    "reset": True,
    "sessionKey": session_key,
    "sessionId": entry.get("sessionId"),
    "sessionFile": session_file,
    "removedSessionFile": removed_file,
    "sessionsBackup": str(backup),
}}, ensure_ascii=False, indent=2))
PY
"""

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=pw, timeout=60, allow_agent=False, look_for_keys=False)
    _, so, se = c.exec_command(remote.strip(), get_pty=True)
    out = so.read().decode("utf-8", errors="replace")
    err = se.read().decode("utf-8", errors="replace")
    c.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    if err.strip():
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
