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
            "标题直接写成：",
            "从日本开始才允许使用编号",
            "只有以上 4 个一级标题可以使用数字编号",
            "标题和时间窗口不能编号",
            "带数字编号的行只能是 1 到 4",
            "发出前逐条检查：标题未编号、时间窗口未编号、只有 4 个一级数字标题、一级标题连续为 1 到 4、正文条目不用数字、链接行不带编号"
        ]
        fr = cfg["formatRules"]
        numbering = fr.get("numberingCheck", {})
        for heading in numbering.get("allowedTopLevelHeadings", []):
            required.append(heading)
        for area in numbering.get("forbidNumberingIn", []):
            required.append(f"以下位置禁止任何编号：{'、'.join(numbering.get('forbidNumberingIn', []))}")
            break
        for pattern in numbering.get("forbidPatterns", []):
            required.append(f"以下模式一律视为编号错误并禁止出现：{'、'.join(numbering.get('forbidPatterns', []))}")
            break
        for item in numbering.get("deliveryChecklist", []):
            required.append(f"编号检查清单：{item}。")
        if fr.get("omitFinalSourceSummary"):
            required.append("文末不要再重复列一次所有来源概览")
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
        coverage_rule = cfg.get("sourcePolicy", {}).get("coverageRule")
        if coverage_rule:
            required.append(coverage_rule)
        min_soft = cfg.get("sourcePolicy", {}).get("minimumSoftNewsCategoriesPerRegion")
        if min_soft:
            required.append(f"每个地区至少要纳入 {min_soft} 个软新闻类别")
        tp = cfg.get("toolPolicy", {})
        if tp.get("preferWebSearchAndWebFetch"):
            required.append("优先使用 web_search 获取线索，并直接用 web_fetch 抓取原文页面")
        if tp.get("forbidBrowserSearchPages"):
            required.append("禁止把 Google、DuckDuckGo 等搜索结果页当成 browser 打开目标")
        if tp.get("browserFallbackPolicy"):
            required.append(tp["browserFallbackPolicy"])
        sq = tp.get("searchQuotaPolicy", {})
        if sq:
            required.append("搜索配额控制是硬约束，不得超过")
        if sq.get("primaryProvider"):
            required.append(f"搜索顺序：先 RSS / 原媒体直链，再 {sq['primaryProvider']}")
        if sq.get("limits", {}).get("brave", {}).get("maxCalls"):
            required.append(f"Brave 调用上限：每月 {sq['limits']['brave']['maxCalls']} 次")
        for rule in sq.get("enforcementRules", []):
            required.append(rule)
        workflow = cfg.get("workflow", {})
        if workflow.get("mode"):
            required.append(f"默认工作流模式：{workflow['mode']}")
        per_item = workflow.get("perItemProcessing", {})
        if per_item.get("preferLocalModel"):
            required.append("单条判断阶段优先使用本地模型，不要先用 Codex")
        if per_item.get("forbidCodexBeforeFinalDraft"):
            required.append("Codex 在最终成稿前禁止参与整批筛选或前置判断")
        if workflow.get("taskTempRoot"):
            required.append(f"本次任务必须建立自己的临时目录，建议根目录：{workflow['taskTempRoot']}")
        if workflow.get("itemRecordFile"):
            required.append(f"单条处理结果必须持续追加写入临时文件：{workflow['itemRecordFile']}")
        if per_item.get("requiredFields"):
            required.append(f"每条候选新闻必须输出结构化记录，至少包含：{'、'.join(per_item['requiredFields'])}")
        merge = workflow.get("mechanicalMerge", {})
        if workflow.get("mergedRecordFile"):
            required.append(f"机械合并产物写入：{workflow['mergedRecordFile']}")
        if merge.get("script"):
            required.append(f"机械合并必须先用脚本完成，脚本路径：{merge['script']}")
        for step in merge.get("steps", []):
            required.append(f"机械合并步骤：{step}。")
        final_codex = workflow.get("finalCodexPass", {})
        if final_codex.get("allowedResponsibilities"):
            required.append(f"Codex 只负责：{'、'.join(final_codex['allowedResponsibilities'])}。")
        if final_codex.get("forbidRescreeningAllCandidates"):
            required.append("Codex 不得重新做整批新闻筛选")
        if workflow.get("finalDraftFile"):
            required.append(f"最终成稿文件写入：{workflow['finalDraftFile']}")
        if workflow.get("summaryReportFile"):
            required.append(f"运行摘要写入：{workflow['summaryReportFile']}")
        reporting = workflow.get("reporting", {})
        if reporting.get("replyFields"):
            required.append(f"完成后只汇报这些字段：{'、'.join(reporting['replyFields'])}")
        channel_output = workflow.get("channelOutputPolicy", {})
        if channel_output.get("defaultMode"):
            required.append(f"频道输出默认模式：{channel_output['defaultMode']}")
        if channel_output.get("forbidIntermediateProgressMessages"):
            required.append("默认不要把中间过程连续发到频道")
        if channel_output.get("allowRealtimeOnlyIfExplicitlyRequested"):
            required.append("除非用户明确要求实时播报，否则只发最终结果")
        if channel_output.get("allowStartMessage"):
            required.append(f"最多允许发送 {channel_output['maxStartMessages']} 条开始执行消息")
        if channel_output.get("allowCompletionMessage"):
            required.append(f"最多允许发送 {channel_output['maxCompletionMessages']} 条完成结果消息")
        pools = cfg.get("sourcePolicy", {}).get("sourcePools", {})
        if pools.get("japan"):
            required.append("日本优先信源池")
        if pools.get("china"):
            required.append("中国优先信源池")
        if pools.get("world"):
            required.append("国际优先信源池")
        for token in required:
            if token not in msg:
                fail(f"missing required token in {spec['name']}: {token}")

    print("VERIFY_OK")
    for spec in cfg["jobs"]:
        print(spec["name"])


if __name__ == "__main__":
    main()

