#!/usr/bin/env python3
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "news" / "broadcast.json"
JOBS_PATH = Path("/var/lib/openclaw/.openclaw/cron/jobs.json")


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def fail(msg: str):
    raise SystemExit(msg)


def main():
    cfg = load_json(CONFIG_PATH)
    jobs_doc = load_json(JOBS_PATH)
    jobs = {job["name"]: job for job in jobs_doc.get("jobs", [])}

    for spec in cfg["jobs"]:
        job = jobs.get(spec["name"])
        if not job:
            fail(f"missing job: {spec['name']}")
        if job.get("schedule", {}).get("expr") != spec["schedule"]["expr"]:
            fail(f"bad schedule for {spec['name']}")
        if job.get("delivery", {}).get("to") != cfg["delivery"]["to"]:
            fail(f"bad delivery target for {spec['name']}")
        msg = job.get("payload", {}).get("message", "")
        required = [
            "1. 标题",
            "7. 信息来源概览",
            "禁止继续使用数字编号",
            "带数字编号的行只能是 1 到 7"
        ]
        for token in required:
            if token not in msg:
                fail(f"missing required token in {spec['name']}: {token}")

    print("VERIFY_OK")
    for spec in cfg["jobs"]:
        print(spec["name"])


if __name__ == "__main__":
    main()
