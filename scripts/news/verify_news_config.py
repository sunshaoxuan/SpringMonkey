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
    expected_names = {spec["name"] for spec in cfg["jobs"]}

    stale = [
        name
        for name in jobs
        if str(name).startswith("news-digest-jst-") and name not in expected_names
    ]
    if stale:
        fail(f"stale jobs present: {', '.join(sorted(stale))}")

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
        fr = cfg["formatRules"]
        if fr.get("requirePerItemSourceLink"):
            required.append("每一条实际新闻条目后都必须带具体原文链接")
            required.append("如果拿不到该条新闻的具体原文链接，这条新闻不得发布")
        if fr.get("requireLinkOnNewLine"):
            required.append("每条新闻的链接必须单独另起一行")
            required.append("不允许把链接塞在正文句尾")
        if fr.get("requireSourceLinkMatchesItem"):
            required.append("链接必须与该条正文内容直接对应；如果点开后与正文不符，这条新闻不得发布")
        if fr.get("forbidAggregatorLinksAsSource"):
            required.append("聚合页链接不能直接作为原文信源")
        if fr.get("requireSourceVerifiedBeforeWriting"):
            required.append("必须先验证来源链接可访问且内容与要写的事实相符，再组织成新闻条目")
        for token in required:
            if token not in msg:
                fail(f"missing required token in {spec['name']}: {token}")

    print("VERIFY_OK")
    for spec in cfg["jobs"]:
        print(spec["name"])


if __name__ == "__main__":
    main()
