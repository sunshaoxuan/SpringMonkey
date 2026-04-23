#!/usr/bin/env python3
from __future__ import annotations

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

REMOTE = r"""
set -euo pipefail
REPO=/var/lib/openclaw/repos/SpringMonkey
SRC="${REPO}/scripts/timescar"
DST=/var/lib/openclaw/.openclaw/workspace/scripts
if [ ! -d "$SRC" ]; then
  echo "missing repo source: $SRC" >&2
  exit 1
fi
install -d -m 755 "$DST"
install -m 755 "$SRC"/timescar_task_guard.py "$DST"/timescar_task_guard.py
install -m 755 "$SRC"/task_runtime.py "$DST"/task_runtime.py
install -m 755 "$SRC"/timescar_fetch_reservations.py "$DST"/timescar_fetch_reservations.py
install -m 755 "$SRC"/timescar_next24h_notice.py "$DST"/timescar_next24h_notice.py
install -m 755 "$SRC"/timescar_book_sat_3weeks.py "$DST"/timescar_book_sat_3weeks.py
install -m 755 "$SRC"/timescar_extend_sun_3weeks.py "$DST"/timescar_extend_sun_3weeks.py
install -m 755 "$SRC"/timescar_daily_report_render.py "$DST"/timescar_daily_report_render.py
python3 -m py_compile \
  "$DST"/timescar_task_guard.py \
  "$DST"/task_runtime.py \
  "$DST"/timescar_fetch_reservations.py \
  "$DST"/timescar_next24h_notice.py \
  "$DST"/timescar_book_sat_3weeks.py \
  "$DST"/timescar_extend_sun_3weeks.py \
  "$DST"/timescar_daily_report_render.py
echo "TIMESCAR_RUNTIME_INSTALLED"
"""


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print("缺少 paramiko。请执行：python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt", file=sys.stderr)
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=120, allow_agent=False, look_for_keys=False)
    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "TIMESCAR_RUNTIME_INSTALLED" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
