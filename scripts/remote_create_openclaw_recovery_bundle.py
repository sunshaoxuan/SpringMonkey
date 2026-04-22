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
USER = os.environ.get("OPENCLAW_SSH_USER", "root")
LOCAL_OUT_DIR = Path(os.environ.get("OPENCLAW_RECOVERY_BUNDLE_DIR", str(Path("var") / "recovery-bundles"))).resolve()

REMOTE = r"""
set -euo pipefail

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="/var/backups/openclaw-recovery"
BASENAME="openclaw-recovery-${STAMP}"
WORKDIR="${ROOT}/${BASENAME}"
ARCHIVE="${ROOT}/${BASENAME}.tar.gz"

mkdir -p "$WORKDIR"
mkdir -p "${WORKDIR}/meta"

python3 <<'PY'
import json
import os
import subprocess
from pathlib import Path

workdir = Path(os.environ["WORKDIR"])
meta = workdir / "meta"
meta.mkdir(parents=True, exist_ok=True)

manifest = {}
manifest["service_name"] = "openclaw.service"
manifest["health_url"] = "http://127.0.0.1:18789/healthz"

def run(cmd: str) -> str:
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as exc:
        return f"ERROR: {exc.output.strip()}"

manifest["systemctl_is_active"] = run("systemctl is-active openclaw.service")
manifest["repo_head"] = run("cd /var/lib/openclaw/repos/SpringMonkey && git rev-parse HEAD")
manifest["repo_status"] = run("cd /var/lib/openclaw/repos/SpringMonkey && git status --short")
manifest["dist_files"] = run("find /usr/lib/node_modules/openclaw/dist -maxdepth 1 -type f -name '*.js' | sort")

(meta / "host-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

copy_if_exists() {
  src="$1"
  dest="$2"
  if [ -e "$src" ]; then
    mkdir -p "$(dirname "$dest")"
    cp -a "$src" "$dest"
  fi
}

copy_if_exists /var/lib/openclaw/.openclaw/openclaw.json "${WORKDIR}/openclaw.json"
copy_if_exists /var/lib/openclaw/.openclaw/cron/jobs.json "${WORKDIR}/cron/jobs.json"
copy_if_exists /var/lib/openclaw/.openclaw/workspace "${WORKDIR}/workspace"
copy_if_exists /var/lib/openclaw/.openclaw/state "${WORKDIR}/state"
copy_if_exists /var/lib/openclaw/.openclaw/agents/main/sessions "${WORKDIR}/agents/main/sessions"
copy_if_exists /var/lib/openclaw/.openclaw/memory/lancedb "${WORKDIR}/memory/lancedb"
copy_if_exists /etc/systemd/system/openclaw.service.d "${WORKDIR}/systemd/openclaw.service.d"
copy_if_exists /etc/openclaw/openclaw.env "${WORKDIR}/etc/openclaw.env"
copy_if_exists /usr/local/lib/openclaw "${WORKDIR}/usr-local-lib/openclaw"

find /usr/lib/node_modules/openclaw/dist -maxdepth 1 -type f -name '*.js' | sort > "${WORKDIR}/meta/dist-files.txt" || true
systemctl cat openclaw.service > "${WORKDIR}/meta/openclaw.service.txt" || true
journalctl -u openclaw.service -n 300 --no-pager > "${WORKDIR}/meta/openclaw.service.journal.txt" || true

tar -C "$ROOT" -czf "$ARCHIVE" "$BASENAME"
echo "$ARCHIVE"
"""


def main() -> int:
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

    LOCAL_OUT_DIR.mkdir(parents=True, exist_ok=True)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=120, allow_agent=False, look_for_keys=False)

    transport = client.get_transport()
    if transport is None:
        client.close()
        print("SSH transport unavailable", file=sys.stderr)
        return 1

    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True, timeout=1800)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        sys.stderr.write(err)
    if not out:
        client.close()
        print("remote bundle path not returned", file=sys.stderr)
        return 1
    remote_archive = out.splitlines()[-1].strip()

    sftp = client.open_sftp()
    try:
        local_archive = LOCAL_OUT_DIR / Path(remote_archive).name
        sftp.get(remote_archive, str(local_archive))
    finally:
        sftp.close()
        client.close()

    print(f"REMOTE_ARCHIVE {remote_archive}")
    print(f"LOCAL_ARCHIVE {local_archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
