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
    fr = cfg["formatRules"]
    sp = cfg.get("sourcePolicy", {})
    tp = cfg.get("toolPolicy", {})
    sq = tp.get("searchQuotaPolicy", {})

    outline = "\n".join(fr["outline"])
    title_line = fr.get("titleLine", "新闻简报")
    show_window_plain = fr.get("showWindowAsPlainLine", False)

    link_rules = []
    if fr.get("requirePerItemSourceLink"):
        link_rules.append("- 每一条实际新闻条目后都必须带具体原文链接；不能只在文末统一列来源名，不得省略 URL。")
    if fr.get("requireLinkOnNewLine"):
        link_rules.append("- 每条新闻的链接必须单独另起一行，格式为“链接：<具体原文 URL>”。")
        link_rules.append("- 不允许把链接塞在正文句尾。")
    if fr.get("requireSourceLinkMatchesItem"):
        link_rules.append("- 链接必须与该条正文内容直接对应；如果点开后与正文不符，这条新闻不得发布。")
    if fr.get("forbidAggregatorLinksAsSource"):
        link_rules.append("- 聚合页链接不能直接作为原文信源；禁止使用 Google News、Yahoo News 等聚合链接冒充原始报道。")
    if fr.get("requireSourceVerifiedBeforeWriting"):
        link_rules.append("- 必须先验证来源链接可访问且内容与要写的事实相符，再组织成新闻条目；不能先写结论后补链接。")
    if fr.get("requirePerItemSourceLink"):
        link_rules.append("- 如果拿不到该条新闻的具体原文链接，这条新闻不得发布。")
        link_rules.append("- 发出前自检：每一条新闻是否都带有一个可直接打开且与正文一致的原文链接；若有缺失或不匹配，先重写或删掉该条。")

    blocked = ", ".join(sp.get("blockedDomains", []))
    aggregators = ", ".join(sp.get("aggregatorDomains", []))
    categories = "、".join(sp.get("coverageCategories", []))
    coverage_rule = sp.get("coverageRule", "")
    min_soft = sp.get("minimumSoftNewsCategoriesPerRegion", 0)
    pools = sp.get("sourcePools", {})
    pools_text = []
    for region in ("japan", "china", "world"):
        if pools.get(region):
            label = {"japan": "日本", "china": "中国", "world": "国际"}[region]
            pools_text.append(f"- {label}优先信源池：{'、'.join(pools[region])}。")

    intro = [
        "你要向 Discord public 频道发布新闻简报。",
        f"标题直接写成：{title_line}。",
        "时间窗口作为标题下的附加信息单独显示，不使用数字编号。" if show_window_plain else "",
        "从日本开始才允许使用编号，且只能使用以下一级标题：",
        outline,
        "",
        "强制格式规则：",
        "- 只有以上 4 个一级标题可以使用数字编号。",
        "- 标题和时间窗口不能编号。",
        "- 各节内部的条目一律使用短横线项目符号 `- `。",
        "- 绝对不要出现嵌套数字编号。",
        "- 发出前先自检：整篇中带数字编号的行只能是 1 到 4 这四个一级标题。若不满足，先重写再发送。",
        f"- 若某一地区没有足够重大且可确认的新条目，写一条项目符号说明“{fr['fallbackNoMajorUpdateLine']}”，不要为了凑数乱编号。",
    ]
    if fr.get("omitFinalSourceSummary"):
        intro.append("- 每条新闻既然已经单独附链接，文末不要再重复列一次所有来源概览。")
    intro.extend(link_rules)
    intro.extend([
        f"- 禁用信源域名：{blocked}。若候选链接命中这些域名，必须丢弃并改用其他来源。",
        f"- 聚合域名：{aggregators}。这些链接只能当线索，不能当原文信源。",
        "- 优先使用 web_search 获取线索，并直接用 web_fetch 抓取原文页面；不要为了搜索结果页再调用 browser。" if tp.get("preferWebSearchAndWebFetch") else "",
        "- 禁止把 Google、DuckDuckGo 等搜索结果页当成 browser 打开目标；搜索结果只能作为线索，后续必须直接抓原媒体或机构页面。" if tp.get("forbidBrowserSearchPages") else "",
        f"- {tp['browserFallbackPolicy']}" if tp.get("browserFallbackPolicy") else "",
        "- 搜索配额控制是硬约束，不得超过。" if sq else "",
        f"- 搜索顺序：先 RSS / 原媒体直链，再 {sq.get('primaryProvider')}。" if sq else "",
        f"- Brave 调用上限：每月 {sq.get('limits',{}).get('brave',{}).get('maxCalls')} 次。" if sq.get('limits',{}).get('brave',{}).get('maxCalls') else "",
        *[f"- {rule}" for rule in sq.get("enforcementRules", [])],
        f"- 每次都要主动覆盖这些类别：{categories}。",
        f"- {coverage_rule}" if coverage_rule else "",
        f"- 每个地区至少要纳入 {min_soft} 个软新闻类别（如社会、科技、娱乐、生活、体育、健康）中的有效条目，除非确实无可验证来源。" if min_soft else "",
        *pools_text,
        "- 语言使用中文。",
        "",
        f"本次任务的时间窗是：{job['windowLabel']}。",
        "优先使用公开可信来源；若 web_search 不可用，可使用 RSS、公开网页与已知权威媒体页面。",
        f"本时段参考窗口约 {job['windowHours']} 小时。完成后直接投递到 Discord。"
    ])

    return "\n".join([line for line in intro if line != ""])


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

],
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

