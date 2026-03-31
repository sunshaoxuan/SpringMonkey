#!/usr/bin/env python3
import json
import os
import time
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "news" / "broadcast.json"
JOBS_PATH = Path("/var/lib/openclaw/.openclaw/cron/jobs.json")


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def build_message(cfg: dict, job: dict) -> str:
    outline = "\n".join(cfg["formatRules"]["outline"])
    require_links = cfg["formatRules"].get("requirePerItemSourceLink", False)
    require_link_newline = cfg["formatRules"].get("requireLinkOnNewLine", False)
    require_link_match = cfg["formatRules"].get("requireSourceLinkMatchesItem", False)

    link_rules = []
    if require_links:
        link_rules.append("- 每一条实际新闻条目后都必须带具体原文链接；不能只在文末统一列来源名，不得省略 URL。")
    if require_link_newline:
        link_rules.append("- 每条新闻的链接必须单独另起一行，格式为“链接：<具体原文 URL>”。")
        link_rules.append("- 不允许把链接塞在正文句尾。")
    if require_link_match:
        link_rules.append("- 链接必须与该条正文内容直接对应；如果点开后与正文不符，这条新闻不得发布。")
    if require_links:
        link_rules.append("- 如果拿不到该条新闻的具体原文链接，这条新闻不得发布。")
        link_rules.append("- 发出前自检：每一条新闻是否都带有一个可直接打开且与正文一致的原文链接；若有缺失或不匹配，先重写或删掉该条。")

    link_rule_text = "\n".join(link_rules)
    if link_rule_text:
        link_rule_text += "\n"

    return (
        "你要向 Discord public 频道发布新闻简报。严格使用以下固定结构：\n"
        f"{outline}\n\n"
        "强制格式规则：\n"
        "- 只有以上 7 个一级标题可以使用数字编号。\n"
        "- 在“3. 日本 / 4. 中国 / 5. 国际 / 6. 市场或风险提示 / 7. 信息来源概览”各节内部，禁止继续使用数字编号。\n"
        "- 各节内部的条目一律使用短横线项目符号 `- `。\n"
        "- 绝对不要出现类似“4. 中国”下面再写“4. 某条新闻”或“5. 某条新闻”的情况。\n"
        "- 发出前先自检：整篇中带数字编号的行只能是 1 到 7 这七个一级标题。若不满足，先重写再发送。\n"
        f"- 若某一地区没有足够重大且可确认的新条目，写一条项目符号说明“{cfg['formatRules']['fallbackNoMajorUpdateLine']}”，不要为了凑数乱编号。\n"
        f"{link_rule_text}"
        "- 语言使用中文。\n\n"
        f"本次任务的时间窗是：{job['windowLabel']}。"
        f" 优先使用公开可信来源；若 web_search 不可用，可使用 RSS、公开网页与已知权威媒体页面。"
        f" 重点覆盖日本 / 中国 / 国际三类重大新闻，并补充市场或风险提示。"
        f" 本时段参考窗口约 {job['windowHours']} 小时。完成后直接投递到 Discord。"
    )


def apply_job(cfg: dict, jobs_doc: dict, spec: dict):
    now_ms = int(time.time() * 1000)
    existing = None
    for job in jobs_doc.get("jobs", []):
        if job.get("name") == spec["name"]:
            existing = job
            break

    if existing is None:
        existing = {
            "id": str(uuid.uuid4()),
            "agentId": "main",
            "name": spec["name"],
            "createdAtMs": now_ms,
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {"kind": "agentTurn"},
            "delivery": {},
            "state": {}
        }
        jobs_doc.setdefault("jobs", []).append(existing)

    existing["description"] = spec["description"]
    existing["enabled"] = True
    existing["updatedAtMs"] = now_ms
    existing["schedule"] = {
        "kind": "cron",
        "expr": spec["schedule"]["expr"],
        "tz": spec["schedule"]["tz"],
        "staggerMs": 0
    }
    existing["payload"] = {
        "kind": "agentTurn",
        "message": build_message(cfg, spec),
        "model": cfg["model"]["name"],
        "thinking": cfg["model"]["thinking"],
        "timeoutSeconds": cfg["model"]["timeoutSeconds"],
        "lightContext": cfg["model"]["lightContext"],
        "allowUnsafeExternalContent": cfg["model"]["allowUnsafeExternalContent"]
    }
    existing["delivery"] = cfg["delivery"]


def main():
    cfg = load_json(CONFIG_PATH)
    jobs_doc = load_json(JOBS_PATH)
    if jobs_doc.get("version") != 1:
        raise SystemExit("Unsupported jobs.json version")

    expected_names = {spec["name"] for spec in cfg["jobs"]}
    jobs_doc["jobs"] = [
        job
        for job in jobs_doc.get("jobs", [])
        if not (
            str(job.get("name", "")).startswith("news-digest-jst-")
            and job.get("name") not in expected_names
        )
    ]

    for spec in cfg["jobs"]:
        apply_job(cfg, jobs_doc, spec)

    save_json(JOBS_PATH, jobs_doc)
    print("APPLY_OK")
    for spec in cfg["jobs"]:
        print(spec["name"])


if __name__ == "__main__":
    main()
