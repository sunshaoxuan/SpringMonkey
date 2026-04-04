#!/usr/bin/env bash
# 在网关宿主机上以当前用户（应为 openclaw 或已具备 gateway 权限）验证 cron run CLI。
# 推荐：runuser -u openclaw -- env HOME=/var/lib/openclaw bash scripts/openclaw/test_cron_run_cli.sh
set -euo pipefail

export HOME="${HOME:-/var/lib/openclaw}"
JOB_NAME="${NEWS_CRON_JOB_NAME:-news-digest-jst-1700}"
TIMEOUT_SEC="${CRON_RUN_TIMEOUT_SEC:-180}"

echo "[test_cron_run_cli] HOME=$HOME"
if ! command -v openclaw >/dev/null 2>&1; then
  echo "FAIL: openclaw not in PATH"
  exit 2
fi

JSON="$(openclaw cron list --json)" || { echo "FAIL: cron list"; exit 2; }

JOB_ID="$(echo "$JSON" | JOB_NAME="$JOB_NAME" python3 -c "
import json, os, sys
name = os.environ['JOB_NAME']
data = json.load(sys.stdin)
for j in data.get('jobs') or []:
    if j.get('name') == name:
        print(j.get('id') or '')
        break
")"

if [[ -z "${JOB_ID}" ]]; then
  echo "FAIL: job id not found for name=$JOB_NAME"
  exit 3
fi

echo "[test_cron_run_cli] openclaw cron run $JOB_ID (timeout ${TIMEOUT_SEC}s)..."
if command -v timeout >/dev/null 2>&1; then
  OUT="$(timeout "${TIMEOUT_SEC}" openclaw cron run "$JOB_ID" 2>&1)" && RC=0 || RC=$?
else
  OUT="$(openclaw cron run "$JOB_ID" 2>&1)" && RC=0 || RC=$?
fi

if [[ "$RC" -ne 0 ]]; then
  echo "FAIL: cron run exit $RC"
  echo "$OUT"
  exit 4
fi
echo "$OUT"
echo "[test_cron_run_cli] OK"
