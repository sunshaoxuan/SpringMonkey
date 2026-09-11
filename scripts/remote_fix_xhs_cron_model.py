#!/usr/bin/env python3
"""Set the XHS recurring writing cron job to the explicit Codex primary model."""
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
REPO = os.environ.get("SPRINGMONKEY_REPO_PATH", "/var/lib/openclaw/repos/SpringMonkey")
JOB_NAME = os.environ.get("OPENCLAW_XHS_CRON_NAME", "xhs-recommendation-every-3-days")
TARGET_MODEL = os.environ.get("OPENCLAW_XHS_CRON_MODEL", "openai-codex/gpt-5.6-sol")
TARGET_DELIVERY_TO = os.environ.get("OPENCLAW_XHS_CRON_DELIVERY_TO", "1497009159940608020")
SUBAGENT_POLICY_MARKER = "[xhs-current-run-only]"
OWNER_ACCESS_POLICY_MARKER = "[xhs-owner-access]"
OWNER_GOOGLE_EMAIL = os.environ.get("OPENCLAW_OWNER_GOOGLE_EMAIL", "").strip()

REMOTE = r"""
set -euo pipefail
cd "$SPRINGMONKEY_REPO_PATH"

install -d -m 755 /etc/openclaw /etc/systemd/system/openclaw.service.d
touch /etc/openclaw/openclaw.env
chmod 640 /etc/openclaw/openclaw.env
if [ -n "${REQUESTED_OWNER_GOOGLE_EMAIL:-}" ]; then
  python3 - <<'PY' /etc/openclaw/openclaw.env "$REQUESTED_OWNER_GOOGLE_EMAIL"
from pathlib import Path
import sys

path = Path(sys.argv[1])
owner_email = sys.argv[2].strip()
lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
lines = [line for line in lines if not line.startswith("OPENCLAW_OWNER_GOOGLE_EMAIL=")]
lines.append(f"OPENCLAW_OWNER_GOOGLE_EMAIL={owner_email}")
path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
PY
fi
set -a
. /etc/openclaw/openclaw.env
set +a
: "${OPENCLAW_OWNER_GOOGLE_EMAIL:?OPENCLAW_OWNER_GOOGLE_EMAIL is required}"
OWNER_GOOGLE_EMAIL="$OPENCLAW_OWNER_GOOGLE_EMAIL"

cat >/etc/systemd/system/openclaw.service.d/10-shared-capabilities.conf <<'EOF'
[Service]
EnvironmentFile=-/etc/openclaw/openclaw.env
EOF
systemctl daemon-reload
systemctl restart openclaw.service
systemctl is-active --quiet openclaw.service

TMP_MESSAGE="$(mktemp /tmp/xhs-cron-message.XXXXXX)"
TMP_JOB_ID="$(mktemp /tmp/xhs-cron-id.XXXXXX)"
python3 - <<'PY' "$TMP_MESSAGE" "$TMP_JOB_ID" "$JOB_NAME" "$OWNER_GOOGLE_EMAIL"
import json
import subprocess
import sys

message_path = sys.argv[1]
job_id_path = sys.argv[2]
job_name = sys.argv[3]
owner_email = sys.argv[4]
policy = (
    "[xhs-current-run-only]\n"
    "Complete this scheduled workflow in the current agent run. Do not call sessions_spawn or delegate any part to a subagent. "
    "Research, browser work, Google Docs writing, verification, and final delivery must all remain in this run so the configured model and timeouts stay authoritative. "
    "Keep research bounded: use at most 8 product or image source page fetches and at most 12 browser snapshots for the entire run. "
    "Read only the relevant page sections and never copy full-page HTML or full-page text into the conversation. "
    "Retry a failed page or tool at most once, then use another source. Once one real product and the required three images are verified, stop researching and write the Google Doc immediately. "
    "Reuse one Google Docs tab and keep only concise source facts in context.\n"
    "[xhs-owner-access]\n"
    f"Before delivery, share the Google Doc directly with {owner_email} as Viewer. "
    "Do not create an anyone-with-link permission, grant edit access, or transfer ownership. "
    "Reopen the sharing settings and verify that exact email is listed as Viewer before reporting success. "
    "If sharing or verification fails, report the concrete blocker and do not claim successful delivery.\n"
)

proc = subprocess.run(
    ["openclaw", "--no-color", "cron", "list", "--json"],
    check=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    stdout=subprocess.PIPE,
)
data = json.loads(proc.stdout)
jobs = data if isinstance(data, list) else data.get("jobs") or data.get("items") or data.get("data") or []
for job in jobs:
    if not isinstance(job, dict):
        continue
    if job.get("name") == job_name:
        from pathlib import Path

        message = job.get("payload", {}).get("message", "")
        marker = policy.splitlines()[0]
        if marker in message:
            message = message.split(marker, 1)[0].rstrip()
        Path(message_path).write_text(f"{message.rstrip()}\n\n{policy}", encoding="utf-8")
        Path(job_id_path).write_text(str(job.get("id") or ""), encoding="utf-8")
        print(json.dumps(job, ensure_ascii=False, indent=2))
        break
else:
    raise SystemExit(f"job not found: {job_name}")
PY

JOB_ID_VALUE="$(cat "$TMP_JOB_ID")"
MESSAGE_VALUE="$(cat "$TMP_MESSAGE")"

openclaw --no-color cron edit "$JOB_ID_VALUE" \
  --name "$JOB_NAME" \
  --description "每三天产出一篇小红书推荐文，写入 Google Docs 等待确认，不自动发布" \
  --cron "0 10 */3 * *" \
  --tz "Asia/Tokyo" \
  --message "$MESSAGE_VALUE" \
  --channel discord \
  --to "$TARGET_DELIVERY_TO" \
  --announce \
  --account default \
  --model "$TARGET_MODEL" \
  --fallbacks "" \
  --thinking low \
  --timeout-seconds 3600 \
  --agent main \
  --session isolated \
  --wake now \
  --light-context \
  --enable \
  --timeout 60000

rm -f "$TMP_MESSAGE" "$TMP_JOB_ID"

echo "=== verify cron status ==="
python3 scripts/openclaw/cron_status_tool.py --topic xhs

echo "=== verify payload model ==="
python3 - <<'PY' "$JOB_NAME" "$TARGET_MODEL" "$TARGET_DELIVERY_TO" "$SUBAGENT_POLICY_MARKER" "$OWNER_ACCESS_POLICY_MARKER" "$OWNER_GOOGLE_EMAIL"
import json
import subprocess
import sys

job_name, target_model, target_delivery_to, policy_marker, owner_policy_marker, owner_email = sys.argv[1:7]
proc = subprocess.run(
    ["openclaw", "--no-color", "cron", "list", "--json"],
    check=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    stdout=subprocess.PIPE,
)
data = json.loads(proc.stdout)
jobs = data if isinstance(data, list) else data.get("jobs") or data.get("items") or data.get("data") or []
for job in jobs:
    if not isinstance(job, dict):
        continue
    if job.get("name") == job_name:
        model = job.get("payload", {}).get("model")
        message = job.get("payload", {}).get("message", "")
        delivery_to = job.get("delivery", {}).get("to")
        print(f"MODEL={model}")
        print(f"DELIVERY_TO={delivery_to}")
        print(f"CURRENT_RUN_ONLY={policy_marker in message}")
        print(f"OWNER_ACCESS_POLICY={owner_policy_marker in message and owner_email in message}")
        if model != target_model:
            raise SystemExit(f"model mismatch: expected {target_model}, got {model}")
        if delivery_to != target_delivery_to:
            raise SystemExit(f"delivery mismatch: expected {target_delivery_to}, got {delivery_to}")
        if policy_marker not in message:
            raise SystemExit(f"missing current-run-only policy: {policy_marker}")
        if owner_policy_marker not in message or owner_email not in message:
            raise SystemExit("missing configured owner access policy")
        break
else:
    raise SystemExit(f"job not found: {job_name}")
PY

echo DONE
"""


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print("缺少 paramiko。请执行：python -m pip install -r scripts/requirements-ssh.txt", file=sys.stderr)
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=90, allow_agent=False, look_for_keys=False)
    exports = "\n".join(
        [
            f"export SPRINGMONKEY_REPO_PATH={REPO!r}",
            f"export JOB_NAME={JOB_NAME!r}",
            f"export TARGET_MODEL={TARGET_MODEL!r}",
            f"export TARGET_DELIVERY_TO={TARGET_DELIVERY_TO!r}",
            f"export SUBAGENT_POLICY_MARKER={SUBAGENT_POLICY_MARKER!r}",
            f"export OWNER_ACCESS_POLICY_MARKER={OWNER_ACCESS_POLICY_MARKER!r}",
            f"export REQUESTED_OWNER_GOOGLE_EMAIL={OWNER_GOOGLE_EMAIL!r}",
        ]
    )
    _, stdout, stderr = client.exec_command(exports + "\n" + REMOTE.strip(), get_pty=True, timeout=600)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    if err.strip():
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
    return 0 if "DONE" in out and f"MODEL={TARGET_MODEL}" in out and f"DELIVERY_TO={TARGET_DELIVERY_TO}" in out and "CURRENT_RUN_ONLY=True" in out and "OWNER_ACCESS_POLICY=True" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())

