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
    outline = "\n".join(fr["outline"])
    blocked = ", ".join(sp.get("blockedDomains", []))
    aggregators = ", ".join(sp.get("aggregatorDomains", []))
    categories = "、".join(sp.get("coverageCategories", []))
    pools = sp.get("sourcePools", {})
    pool_lines = []
    for key, label in (("japan", "日本"), ("china", "中国"), ("world", "国际")):
        if pools.get(key):
            pool_lines.append(f"- {label}优先信源池：{'、'.join(pools[key])}。")
    return "\n".join([
        "你要向 Discord public 频道发布新闻简报。",
        f"标题只允许写成：{fr['titleLine']}。",
        "时间窗口只允许作为标题下的一行普通文本显示，绝对不能编号。",
        "正确模板如下：",
        "新闻简报",
        "",
        "时间窗口：XXXX",
        "",
        "1. 日本",
        "- 条目正文",
        "链接：<具体原文 URL>",
        "",
        "2. 中国",
        "- 条目正文",
        "链接：<具体原文 URL>",
        "",
        "3. 国际",
        "- 条目正文",
        "链接：<具体原文 URL>",
        "",
        "4. 市场或风险提示",
        "- 条目正文",
        "",
        "只允许以下四个一级标题使用数字编号：",
        outline,
        "强制规则：",
        "- 标题和时间窗口绝对不能编号。",
        "- 整篇中带数字编号的行只能是 1 到 4 这四个一级标题。",
        "- 不允许出现 5.、6.、7.，也不允许出现嵌套数字编号。",
        "- 各节内部条目一律使用短横线 `- `，不得使用数字列表。",
        f"- 每个地区至少要纳入 {sp.get('minimumSoftNewsCategoriesPerRegion', 0)} 个软新闻类别（社会、科技、娱乐、生活、体育、健康）中的有效条目，除非确实无可验证来源。",
        f"- 每次都要主动覆盖这些类别：{categories}。",
        f"- {sp.get('coverageRule', '')}",
        "- 每一条实际新闻条目后都必须带具体原文链接；不能只在文末统一列来源名，不得省略 URL。",
        "- 每条新闻的链接必须单独另起一行，格式为“链接：<具体原文 URL>”。",
        "- 不允许把链接塞在正文句尾。",
        "- 链接必须与该条正文内容直接对应；如果点开后与正文不符，这条新闻不得发布。",
        "- 聚合页链接不能直接作为原文信源；禁止使用 Google News、Yahoo News 等聚合链接冒充原始报道。",
        "- 必须先验证来源链接可访问且内容与要写的事实相符，再组织成新闻条目；不能先写结论后补链接。",
        "- 如果拿不到该条新闻的具体原文链接，这条新闻不得发布。",
        f"- 禁用信源域名：{blocked}。若候选链接命中这些域名，必须丢弃并改用其他来源。",
        f"- 聚合域名：{aggregators}。这些链接只能当线索，不能当原文信源。",
        *pool_lines,
        "- 每条新闻既然已经单独附链接，文末不要再重复列一次所有来源概览。",
        f"- 若某一地区没有足够重大且可确认的新条目，写一条项目符号说明“{fr['fallbackNoMajorUpdateLine']}”，不要为了凑数乱编号。",
        f"本次任务的时间窗是：{job['windowLabel']}。",
        f"本时段参考窗口约 {job['windowHours']} 小时。完成后直接投递到 Discord。"
    ])

def apply_job(cfg: dict, jobs_doc: dict, spec: dict):
    now_ms = int(time.time() * 1000)
    existing = next((j for j in jobs_doc.get("jobs", []) if j.get("name") == spec["name"]), None)
    if existing is None:
        existing = {
            "id": str(uuid.uuid4()), "agentId": "main", "name": spec["name"],
            "createdAtMs": now_ms, "sessionTarget": "isolated", "wakeMode": "now",
            "payload": {"kind": "agentTurn"}, "delivery": {}, "state": {}
        }
        jobs_doc.setdefault("jobs", []).append(existing)
    existing["description"] = spec["description"]
    existing["enabled"] = True
    existing["updatedAtMs"] = now_ms
    existing["schedule"] = {"kind": "cron", "expr": spec["schedule"]["expr"], "tz": spec["schedule"]["tz"], "staggerMs": 0}
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
    expected_names = {spec["name"] for spec in cfg["jobs"]}
    jobs_doc["jobs"] = [job for job in jobs_doc.get("jobs", []) if not (str(job.get("name", "")).startswith("news-digest-jst-") and job.get("name") not in expected_names)]
    for spec in cfg["jobs"]:
        apply_job(cfg, jobs_doc, spec)
    save_json(JOBS_PATH, jobs_doc)
    print("APPLY_OK")
    for spec in cfg["jobs"]:
        print(spec["name"])

if __name__ == "__main__":
    main()
