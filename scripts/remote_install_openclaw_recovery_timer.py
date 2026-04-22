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

REMOTE = r"""
set -euo pipefail

install -d -m 755 /usr/local/lib/openclaw
install -d -m 755 /etc/systemd/system

cat >/usr/local/lib/openclaw/create_openclaw_recovery_bundle.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="/var/backups/openclaw-recovery"
BASENAME="openclaw-recovery-${STAMP}"
WORKDIR="${ROOT}/${BASENAME}"
ARCHIVE="${ROOT}/${BASENAME}.tar.gz"

mkdir -p "$WORKDIR"
mkdir -p "${WORKDIR}/meta"
export WORKDIR

python3 <<'PY'
import json
import os
import subprocess
from pathlib import Path

workdir = Path(os.environ["WORKDIR"])
meta = workdir / "meta"
meta.mkdir(parents=True, exist_ok=True)

def run(cmd: str) -> str:
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as exc:
        return f"ERROR: {exc.output.strip()}"

manifest = {
    "service_name": "openclaw.service",
    "health_url": "http://127.0.0.1:18789/healthz",
    "systemctl_is_active": run("systemctl is-active openclaw.service"),
    "repo_head": run("cd /var/lib/openclaw/repos/SpringMonkey && git rev-parse HEAD"),
    "repo_status": run("cd /var/lib/openclaw/repos/SpringMonkey && git status --short"),
    "created_at": run("date --iso-8601=seconds"),
}
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
rm -rf "$WORKDIR"
echo "$ARCHIVE"
EOF

chmod 755 /usr/local/lib/openclaw/create_openclaw_recovery_bundle.sh

cat >/usr/local/lib/openclaw/prune_openclaw_recovery_bundles.py <<'EOF'
#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import re

ROOT = Path("/var/backups/openclaw-recovery")
PATTERN = re.compile(r"openclaw-recovery-(\d{8})-(\d{6})\.tar\.gz$")

KEEP_DAILY = 7
KEEP_WEEKLY = 8
KEEP_MONTHLY = 6


def parse_stamp(path: Path):
    m = PATTERN.fullmatch(path.name)
    if not m:
        return None
    return datetime.strptime("".join(m.groups()), "%Y%m%d%H%M%S")


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(ROOT.glob("openclaw-recovery-*.tar.gz")):
        stamp = parse_stamp(path)
        if stamp is not None:
            items.append((stamp, path))
    items.sort(reverse=True)

    keep = set()

    for stamp, path in items[:KEEP_DAILY]:
        keep.add(path)

    weekly = defaultdict(list)
    for stamp, path in items:
        weekly[(stamp.isocalendar().year, stamp.isocalendar().week)].append(path)
    for _, paths in sorted(weekly.items(), reverse=True)[:KEEP_WEEKLY]:
        keep.add(paths[0])

    monthly = defaultdict(list)
    for stamp, path in items:
        monthly[(stamp.year, stamp.month)].append(path)
    for _, paths in sorted(monthly.items(), reverse=True)[:KEEP_MONTHLY]:
        keep.add(paths[0])

    for _, path in items:
        if path not in keep:
            path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
EOF

chmod 755 /usr/local/lib/openclaw/prune_openclaw_recovery_bundles.py

cat >/etc/systemd/system/openclaw-recovery-backup.service <<'EOF'
[Unit]
Description=Create OpenClaw recovery bundle
After=network-online.target

[Service]
Type=oneshot
User=root
ExecStart=/usr/local/lib/openclaw/create_openclaw_recovery_bundle.sh
ExecStartPost=/usr/bin/python3 /usr/local/lib/openclaw/prune_openclaw_recovery_bundles.py
EOF

cat >/etc/systemd/system/openclaw-recovery-backup.timer <<'EOF'
[Unit]
Description=Daily OpenClaw recovery bundle backup

[Timer]
OnCalendar=*-*-* 03:35:00
Persistent=true
RandomizedDelaySec=20m

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now openclaw-recovery-backup.timer
systemctl start openclaw-recovery-backup.service
sleep 2
systemctl is-active openclaw-recovery-backup.timer
systemctl status openclaw-recovery-backup.service --no-pager -n 20 || true
find /var/backups/openclaw-recovery -maxdepth 1 -type f -name 'openclaw-recovery-*.tar.gz' | sort | tail -n 20
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

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=120, allow_agent=False, look_for_keys=False)
    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True, timeout=1800)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "active" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
