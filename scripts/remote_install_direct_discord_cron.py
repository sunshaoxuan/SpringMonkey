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

DM_CHANNEL="1497009159940608020"
PUBLIC_CHANNEL="1483636573235843072"
REPO="/var/lib/openclaw/repos/SpringMonkey"
OPENCLAW_HOME="/var/lib/openclaw/.openclaw"
HELPER="/usr/local/lib/openclaw/direct_cron_to_discord.py"
CRON_FILE="/etc/cron.d/openclaw-direct-discord"
JOBS_FILE="${OPENCLAW_HOME}/cron/jobs.json"
TS="$(date +%Y%m%d-%H%M%S)"

install -d -m 755 /usr/local/lib/openclaw
install -d -m 755 "${OPENCLAW_HOME}/logs"

cat >"${HELPER}" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

OPENCLAW_HOME = Path("/var/lib/openclaw/.openclaw")
CONFIG = OPENCLAW_HOME / "openclaw.json"
LOG_DIR = OPENCLAW_HOME / "logs" / "direct_discord_cron"
DEFAULT_DM_CHANNEL = "1497009159940608020"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one command and deliver stdout to Discord DM.")
    parser.add_argument("--name", required=True)
    parser.add_argument("--channel-id", default=DEFAULT_DM_CHANNEL)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--skip-output", action="append", default=[])
    parser.add_argument("--run-as-openclaw", action="store_true")
    parser.add_argument("--command", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        raise SystemExit("missing command")
    return args


def discord_token() -> str:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    token = cfg.get("channels", {}).get("discord", {}).get("token")
    if not token:
        raise RuntimeError("missing channels.discord.token")
    return str(token)


def mark_published_after_delivery(name: str, stdout: str, command: list[str]) -> str:
    # News items become broadcasted only after Discord delivery succeeds.
    if not name.startswith("news-digest-"):
        return "not-news"
    command_text = " ".join(command)
    if "--broadcast-mode test" in command_text or "--no-record-recent" in command_text:
        return "test-or-no-record"
    run_dir = ""
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("PIPELINE_OK ") and "skip_finalize" not in line:
            run_dir = line.split(None, 1)[1].strip()
    if not run_dir:
        repo = Path("/var/lib/openclaw/repos/SpringMonkey")
        candidates = sorted((repo / "var" / "news-runs").glob(f"*_{name}"), key=lambda p: p.stat().st_mtime, reverse=True)
        for candidate in candidates:
            if (candidate / "selected_items.json").is_file() and (candidate / "final_broadcast.md").is_file():
                run_dir = str(candidate)
                break
    if not run_dir:
        return "no-run-dir"
    script = "/var/lib/openclaw/repos/SpringMonkey/scripts/news/run_news_pipeline.py"
    proc = subprocess.run(
        ["python3", script, "--job", name, "--mark-published-run-dir", run_dir],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if proc.returncode != 0:
        return f"failed:{proc.returncode}:{(proc.stderr or proc.stdout)[-500:]}"
    return proc.stdout.strip() or "marked"


def send_discord(channel_id: str, content: str) -> int:
    token = discord_token()
    chunks = []
    text = content or ""
    while text:
        chunks.append(text[:1900])
        text = text[1900:]
    if not chunks:
        chunks = [""]
    for index, chunk in enumerate(chunks, 1):
        if len(chunks) > 1:
            chunk = f"[{index}/{len(chunks)}]\n{chunk}"
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            data=json.dumps({"content": chunk}).encode("utf-8"),
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
                "User-Agent": "DiscordBot (openclaw-direct-cron, 1.0)",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    return len(chunks)


def public_failure_message(name: str, returncode: int | str, stdout: str, stderr: str) -> str:
    detail = "\n".join(x for x in (stderr, stdout) if x).strip()
    if name.startswith("news-digest-"):
        if "openclaw infer failed" in detail and "gateway" in detail:
            reason = "新闻已抓取到原始条目，但 OpenClaw gateway 的 Codex 订阅模型通道不可用，无法完成中文整理。"
        elif "missing OPENAI_API_KEY" in detail and (
            "fallback_failed" in detail or "RemoteDisconnected" in detail or "processor_unavailable" in detail
        ):
            reason = "新闻已抓取到原始条目，但任务错误地请求了裸 OPENAI_API_KEY，且 Qwen/Ollama 兜底服务也不可用；需要修正为 OpenClaw 订阅模型通道。"
        elif "processor_unavailable" in detail:
            reason = "新闻已抓取到原始条目，但模型处理器不可用，无法完成中文整理。"
        elif "PIPELINE_FAIL no_eligible_items" in detail:
            reason = "本轮没有符合时间窗口和去重规则的新新闻条目。"
        elif "PIPELINE_FAIL" in detail:
            reason = "新闻流水线未完成，已保留内部日志供排查。"
        else:
            reason = "新闻任务执行失败，已保留内部日志供排查。"
        return (
            f"{name} 未能完成播报。\n"
            f"原因：{reason}\n"
            "处理：本次不会标记为已正式播报；详细诊断只保留在后台日志。"
        )
    if returncode == "timeout":
        return f"{name} 未能完成：超过执行时间限制。详细诊断已保留在后台日志。"
    return f"{name} 未能完成。详细诊断已保留在后台日志。"


def main() -> int:
    args = parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now().isoformat(timespec="seconds")
    result_payload: dict[str, object] = {
        "name": args.name,
        "started": started,
        "command": args.command,
    }
    try:
        command = args.command
        if args.run_as_openclaw:
            command = ["runuser", "-u", "openclaw", "--", *command]
        result_payload["command"] = command
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=args.timeout,
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        result_payload.update(
            {
                "returncode": proc.returncode,
                "stdout": stdout,
                "stderr": stderr[-4000:],
            }
        )
        if proc.returncode == 0:
            if stdout in set(args.skip_output):
                result_payload["delivery"] = "skipped"
                return 0
            message = stdout or f"{args.name}: completed with no output."
            sent_chunks = send_discord(args.channel_id, message)
            result_payload["delivery"] = "delivered"
            result_payload["sentChunks"] = sent_chunks
            result_payload["publishedMark"] = mark_published_after_delivery(args.name, stdout, command)
            return 0
        sent_chunks = send_discord(
            args.channel_id,
            public_failure_message(args.name, proc.returncode, stdout, stderr),
        )
        result_payload["delivery"] = "failure-delivered"
        result_payload["sentChunks"] = sent_chunks
        return proc.returncode or 1
    except subprocess.TimeoutExpired as exc:
        result_payload.update({"returncode": "timeout", "stderr": str(exc)})
        send_discord(args.channel_id, public_failure_message(args.name, "timeout", "", str(exc)))
        return 124
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        result_payload.update({"returncode": "delivery-error", "stderr": f"HTTP {exc.code}: {body}"})
        return 2
    except Exception as exc:
        result_payload.update({"returncode": "exception", "stderr": f"{type(exc).__name__}: {exc}"})
        return 1
    finally:
        result_payload["finished"] = datetime.now().isoformat(timespec="seconds")
        (LOG_DIR / f"{args.name}.latest.json").write_text(
            json.dumps(result_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    raise SystemExit(main())
PY
chmod 755 "${HELPER}"

if [ -f "${JOBS_FILE}" ]; then
  cp -a "${JOBS_FILE}" "${JOBS_FILE}.bak-direct-discord-${TS}"
  python3 <<'PY'
from pathlib import Path
import json

jobs_path = Path("/var/lib/openclaw/.openclaw/cron/jobs.json")
dm_channel = "1497009159940608020"
direct_names = {
    "weather-report-jst-0700",
    "news-digest-jst-0900",
    "news-digest-jst-1700",
    "timescar-daily-report-2200",
    "timescar-book-sat-3weeks",
    "timescar-extend-sun-3weeks",
    "timescar-ask-cancel-next24h-2300",
    "timescar-ask-cancel-next24h-0000",
    "timescar-ask-cancel-next24h-0100",
    "timescar-ask-cancel-next24h-0700",
    "timescar-ask-cancel-next24h-0800",
}
data = json.loads(jobs_path.read_text(encoding="utf-8"))
changed = []
for job in data.get("jobs", []):
    name = job.get("name")
    if name in direct_names:
        job["enabled"] = False
        delivery = job.setdefault("delivery", {})
        delivery["channel"] = "discord"
        if name.startswith("timescar-"):
            delivery["to"] = dm_channel
        else:
            delivery["to"] = "1483636573235843072"
        delivery["accountId"] = delivery.get("accountId") or "default"
        delivery["mode"] = delivery.get("mode") or "announce"
        job.setdefault("state", {})["disabledReason"] = "replaced by host direct cron to Discord DM"
        changed.append(name)
jobs_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("UPDATED_JOBS", ",".join(changed))
PY
fi

cat >"${CRON_FILE}" <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Direct Discord delivery for script-like jobs. These bypass OpenClaw model turns.
0 7 * * * root ${HELPER} --name weather-report-jst-0700 --channel-id ${PUBLIC_CHANNEL} --timeout 120 --run-as-openclaw --command python3 ${REPO}/scripts/weather/discord_weather_report.py

0 9 * * * root ${HELPER} --name news-digest-jst-0900 --channel-id ${PUBLIC_CHANNEL} --timeout 5400 --command bash -lc "set -e; OUT=\$(python3 ${REPO}/scripts/news/jobs/news_digest_jst_0900.py); DIR=\$(echo \"\\\$OUT\" | sed -n 's/^PIPELINE_OK //p' | tail -n1); test -n \"\\\$DIR\"; cat \"\\\$DIR/final_broadcast.md\""
0 17 * * * root ${HELPER} --name news-digest-jst-1700 --channel-id ${PUBLIC_CHANNEL} --timeout 5400 --command bash -lc "set -e; OUT=\$(python3 ${REPO}/scripts/news/jobs/news_digest_jst_1700.py); DIR=\$(echo \"\\\$OUT\" | sed -n 's/^PIPELINE_OK //p' | tail -n1); test -n \"\\\$DIR\"; cat \"\\\$DIR/final_broadcast.md\""

0 22 * * * root ${HELPER} --name timescar-daily-report-2200 --channel-id ${DM_CHANNEL} --timeout 900 --run-as-openclaw --command python3 ${REPO}/scripts/timescar/timescar_daily_report_render.py
0 23 * * * root ${HELPER} --name timescar-ask-cancel-next24h-2300 --channel-id ${DM_CHANNEL} --timeout 900 --skip-output NO_REPLY --run-as-openclaw --command python3 ${REPO}/scripts/timescar/timescar_next24h_notice.py
0 0 * * * root ${HELPER} --name timescar-ask-cancel-next24h-0000 --channel-id ${DM_CHANNEL} --timeout 900 --skip-output NO_REPLY --run-as-openclaw --command python3 ${REPO}/scripts/timescar/timescar_next24h_notice.py
0 1 * * * root ${HELPER} --name timescar-ask-cancel-next24h-0100 --channel-id ${DM_CHANNEL} --timeout 900 --skip-output NO_REPLY --run-as-openclaw --command python3 ${REPO}/scripts/timescar/timescar_next24h_notice.py
0 7 * * * root ${HELPER} --name timescar-ask-cancel-next24h-0700 --channel-id ${DM_CHANNEL} --timeout 900 --skip-output NO_REPLY --run-as-openclaw --command python3 ${REPO}/scripts/timescar/timescar_next24h_notice.py
0 8 * * * root ${HELPER} --name timescar-ask-cancel-next24h-0800 --channel-id ${DM_CHANNEL} --timeout 900 --skip-output NO_REPLY --run-as-openclaw --command python3 ${REPO}/scripts/timescar/timescar_next24h_notice.py

15 0 * * 6 root ${HELPER} --name timescar-book-sat-3weeks --channel-id ${DM_CHANNEL} --timeout 1800 --run-as-openclaw --command python3 ${REPO}/scripts/timescar/timescar_book_sat_3weeks.py
15 0 * * 0 root ${HELPER} --name timescar-extend-sun-3weeks --channel-id ${DM_CHANNEL} --timeout 1800 --run-as-openclaw --command python3 ${REPO}/scripts/timescar/timescar_extend_sun_3weeks.py
EOF
chmod 644 "${CRON_FILE}"

if [ "${RUN_DIRECT_DISCORD_SMOKE:-0}" = "1" ]; then
  python3 "${HELPER}" --name weather-report-jst-0700-smoke --channel-id "${PUBLIC_CHANNEL}" --timeout 120 --run-as-openclaw --command python3 "${REPO}/scripts/weather/discord_weather_report.py"
fi

echo "=== cron file ==="
cat "${CRON_FILE}"
echo "=== disabled jobs ==="
python3 <<'PY'
from pathlib import Path
import json
data=json.loads(Path("/var/lib/openclaw/.openclaw/cron/jobs.json").read_text(encoding="utf-8"))
for job in data.get("jobs", []):
    if job.get("name", "").startswith("timescar-") or job.get("name") in {"weather-report-jst-0700", "news-digest-jst-0900", "news-digest-jst-1700"}:
        print(job.get("name"), "enabled=", job.get("enabled"), "to=", job.get("delivery", {}).get("to"))
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
        print("缺少 paramiko。请执行：python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt", file=sys.stderr)
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=120, allow_agent=False, look_for_keys=False)
    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True, timeout=900)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
