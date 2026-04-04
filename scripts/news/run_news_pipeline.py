#!/usr/bin/env python3
"""
新闻多阶段流水线（管理者工具）：编排 → 工人落盘 → 合并 → 终稿 + 机械校验。

阶段概览
--------
1. plan          从 broadcast.json + job 名生成 plan.json（按地区拆批，与 1–4 大纲对齐）。
2. orchestrate   调用 OpenAI 兼容 API（默认 Codex/配置中的 newsOrchestrator）生成本批检索计划 orchestration.json。
3. worker        每批调用 Ollama（newsWorker）整理/筛选，写入 worker_<id>.md。
4. merge         拼接为 draft_merged.md。
5. finalize      再次调用 OpenAI 兼容 API，合并润色为 final_broadcast.md 并强调编号规则。
6. verify        调用 verify_broadcast_draft 规则做机械检查。

环境变量（常用）
--------------
OPENAI_API_KEY           编排与终稿（缺省则 orchestrate/finalize 用模板或跳过终稿）
NEWS_OPENAI_BASE_URL     默认 https://api.openai.com/v1
NEWS_ORCHESTRATOR_MODEL  覆盖 broadcast.json model.newsOrchestrator
OLLAMA_HOST              默认 http://127.0.0.1:11434
NEWS_WORKER_MODEL        覆盖 broadcast.json model.newsWorker

不落盘 OpenAI Key；运行目录仅含中间稿与 JSON。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "news" / "broadcast.json"

# 与 formatRules.outline 顺序一致
BATCH_SPECS: list[dict[str, Any]] = [
    {"id": "japan", "pool_key": "japan"},
    {"id": "china", "pool_key": "china"},
    {"id": "world", "pool_key": "world"},
    {"id": "markets", "pool_key": None},
]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def http_post_json(url: str, payload: dict, headers: dict[str, str], timeout: int) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {url}: {err_body}") from e
    return json.loads(raw)


def openai_chat(
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    timeout: int,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = http_post_json(url, payload, headers, timeout)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"unexpected OpenAI response: {data!r}") from e


def ollama_chat(host: str, model: str, system: str, user: str, timeout: int) -> str:
    url = host.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
    }
    data = http_post_json(url, payload, {"Content-Type": "application/json"}, timeout)
    try:
        return data["message"]["content"].strip()
    except KeyError as e:
        raise RuntimeError(f"unexpected Ollama response: {data!r}") from e


def job_spec(cfg: dict, name: str) -> dict:
    for j in cfg.get("jobs", []):
        if j.get("name") == name:
            return j
    raise SystemExit(f"unknown job name: {name}")


def build_plan(cfg: dict, job: dict) -> dict:
    fr = cfg["formatRules"]
    outline = fr["outline"]
    if len(outline) != len(BATCH_SPECS):
        raise SystemExit("BATCH_SPECS/outline length mismatch; update BATCH_SPECS")
    batches = []
    for spec, line in zip(BATCH_SPECS, outline, strict=True):
        pk = spec["pool_key"]
        pool = (cfg.get("sourcePolicy", {}).get("sourcePools") or {}).get(pk) if pk else []
        batches.append(
            {
                "id": spec["id"],
                "outline_line": line,
                "source_pool": pool or [],
            }
        )
    return {
        "version": 1,
        "job_name": job["name"],
        "window_label": job["windowLabel"],
        "window_hours": job["windowHours"],
        "title_line": fr.get("titleLine", "新闻简报"),
        "fallback_no_news": fr.get("fallbackNoMajorUpdateLine", "本节无合格新增新闻条目。"),
        "batches": batches,
    }


def template_orchestration(plan: dict) -> dict:
    out = []
    for b in plan["batches"]:
        pool = b.get("source_pool") or []
        hints = "、".join(pool[:6]) if pool else "权威通讯社与主流媒体"
        q = [
            f"{b['outline_line']} 重要新闻 {plan['window_label']}",
            f"{hints} 最新",
        ]
        out.append(
            {
                "id": b["id"],
                "queries": q,
                "outlet_hints": pool[:12],
            }
        )
    return {"version": 1, "batches": out, "source": "template"}


def orchestrate_with_openai(plan: dict, cfg: dict, api_key: str, base_url: str, model: str, timeout: int) -> dict:
    system = (
        "你是新闻采集编排员。只输出 JSON，不要 markdown 围栏。"
        "根据各批地区与信源池，为每批生成 3–8 条可执行的搜索查询（中英均可），"
        "以及 outlet_hints 字符串数组（媒体名）。"
    )
    user = json.dumps(
        {
            "window": plan["window_label"],
            "batches": plan["batches"],
            "instruction": '输出格式：{"batches":[{"id":"japan","queries":[],"outlet_hints":[]}]}，id 必须与输入一致。',
        },
        ensure_ascii=False,
    )
    raw = openai_chat(base_url, api_key, model, system, user, timeout)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    data = json.loads(raw)
    if "batches" not in data:
        raise RuntimeError("orchestration JSON missing batches")
    return {"version": 1, "batches": data["batches"], "source": "openai"}


def worker_system_prompt() -> str:
    return (
        "你是新闻整理与质检助手（工人模型）。只输出 Markdown 正文片段，不要解释流程。"
        "严禁使用一级数字标题（不要用 1. 2. 3. 作为章节号，主编会统一加）。"
        "每条新闻一条项目符号，以「- 」开头；若某条无可靠独立信源链接则不要写该条。"
        "若本批没有任何可写条目，只输出一行：- 本节无合格新增新闻条目。"
    )


def worker_user_prompt(plan: dict, batch_plan: dict, orch_batch: dict, dry_run: bool) -> str:
    lines = [
        f"本批地区大纲行：{batch_plan['outline_line']}",
        f"时间窗：{plan['window_label']}",
        f"检索查询建议：{json.dumps(orch_batch.get('queries', []), ensure_ascii=False)}",
        f"优先媒体提示：{json.dumps(orch_batch.get('outlet_hints', []), ensure_ascii=False)}",
        "",
        "请基于上述方向整理候选条目（若无法联网检索，可列出你认为该时间窗应核查的主题清单，用项目符号，但不要伪造具体新闻事实）。",
    ]
    if dry_run:
        lines.append("（干跑模式：输出两条占位示例条目，标注【干跑占位】，并附假链接 example.com）")
    return "\n".join(lines)


def finalize_system_prompt(cfg: dict, plan: dict) -> str:
    fr = cfg["formatRules"]
    outline = "\n".join(fr["outline"])
    return (
        "你是主编，负责合并工人草稿并输出最终 Discord 新闻简报。"
        "只输出最终成稿 Markdown，不要前言后语。\n"
        f"第一行标题必须是：{plan['title_line']}\n"
        f"第二行起写时间窗（纯文字，不要编号）：{plan['window_label']}\n"
        "然后必须按顺序出现且仅出现以下四个编号小节（整篇仅此四处数字编号行）：\n"
        f"{outline}\n"
        "每个小节内条目一律用「- 」项目符号；禁止嵌套数字编号；禁止在小节内再写 1.2.3.。\n"
        "若某节工人未提供合格条目，写一条「- " + plan["fallback_no_news"] + "」。\n"
        "链接规则：每条新闻下另起一行「链接：https://...」；无链则不写该条。\n"
        "不要使用 markdown 代码围栏（不要用 ```）包裹全文。"
    )


def merge_workers(run_dir: Path, plan: dict) -> str:
    parts = []
    for b in plan["batches"]:
        bid = b["id"]
        p = run_dir / f"worker_{bid}.md"
        if not p.is_file():
            raise SystemExit(f"missing worker file: {p}")
        parts.append(f"<!-- batch:{bid} -->\n{p.read_text(encoding='utf-8').strip()}\n")
    return "\n".join(parts).strip() + "\n"


def load_verify_text():
    path = Path(__file__).resolve().parent / "verify_broadcast_draft.py"
    spec = importlib.util.spec_from_file_location("verify_broadcast_draft", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load verify_broadcast_draft")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.verify_text


def main() -> int:
    parser = argparse.ArgumentParser(description="新闻多阶段流水线（Codex 编排/终稿 + Qwen 工人落盘）")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--job", required=True, help="jobs.json 中的 name，如 news-digest-jst-1700")
    parser.add_argument("--run-dir", type=Path, help="运行目录；默认 repo 下 var/news-runs/<ts>_<job>")
    parser.add_argument("--dry-run", action="store_true", help="工人输出占位；编排/终稿仍尽量走 API（若无 Key 用模板）")
    parser.add_argument("--template-orchestrate", action="store_true", help="跳过 Codex 编排，只用模板检索计划")
    parser.add_argument("--skip-finalize", action="store_true", help="不调用主编模型，draft 即结束")
    parser.add_argument("--skip-worker", action="store_true", help="不调用 Ollama，写入占位 worker_*.md（测合并/终稿）")
    parser.add_argument("--skip-verify", action="store_true", help="跳过机械校验")
    parser.add_argument("--openai-timeout", type=int, default=120)
    parser.add_argument("--ollama-timeout", type=int, default=300)
    args = parser.parse_args()

    cfg = load_json(args.config)
    job = job_spec(cfg, args.job)
    model_cfg = cfg.get("model", {})
    orch_model = os.environ.get(
        "NEWS_ORCHESTRATOR_MODEL",
        model_cfg.get("newsOrchestrator", "gpt-4o"),
    )
    worker_model = os.environ.get(
        "NEWS_WORKER_MODEL",
        model_cfg.get("newsWorker", "qwen2.5:14b-instruct"),
    )
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("NEWS_OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    ollama_host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").strip()

    ts = int(time.time())
    run_dir = args.run_dir
    if not run_dir:
        run_dir = REPO_ROOT / "var" / "news-runs" / f"{ts}_{args.job}"
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    plan = build_plan(cfg, job)
    save_json(run_dir / "plan.json", plan)
    save_json(
        run_dir / "meta.json",
        {
            "created_at_ts": ts,
            "job": args.job,
            "dry_run": args.dry_run,
            "orchestrator_model": orch_model,
            "worker_model": worker_model,
        },
    )

    # --- orchestrate ---
    if args.template_orchestrate or not api_key:
        orch = template_orchestration(plan)
    else:
        try:
            orch = orchestrate_with_openai(
                plan, cfg, api_key, base_url, orch_model, args.openai_timeout
            )
        except Exception as e:
            print(f"[pipeline] orchestrate fallback template: {e}", file=sys.stderr)
            orch = template_orchestration(plan)
    tpl = template_orchestration(plan)
    tpl_by_id = {b["id"]: b for b in tpl["batches"]}
    orch_by_id = {b["id"]: b for b in orch.get("batches", [])}
    for b in plan["batches"]:
        if b["id"] not in orch_by_id:
            print(
                f"[pipeline] orchestration missing batch {b['id']}, using template slice",
                file=sys.stderr,
            )
            orch_by_id[b["id"]] = tpl_by_id[b["id"]]
    orch["batches"] = [orch_by_id[b["id"]] for b in plan["batches"]]
    save_json(run_dir / "orchestration.json", orch)

    # --- workers ---
    sys_prompt = worker_system_prompt()
    for b in plan["batches"]:
        bid = b["id"]
        out_path = run_dir / f"worker_{bid}.md"
        if args.skip_worker:
            out_path.write_text(
                f"- 【skip-worker】{b['outline_line']} 占位草稿（须由主编终稿整理编号）。\n",
                encoding="utf-8",
            )
            continue
        ob = orch_by_id.get(bid) or {"id": bid, "queries": [], "outlet_hints": []}
        user_p = worker_user_prompt(plan, b, ob, args.dry_run)
        try:
            text = ollama_chat(
                ollama_host, worker_model, sys_prompt, user_p, args.ollama_timeout
            )
        except Exception as e:
            if args.dry_run:
                text = f"- 【干跑】工人失败回退：{bid}\n- {plan['fallback_no_news']}\n"
                print(f"[pipeline] ollama worker {bid} failed, dry-run stub: {e}", file=sys.stderr)
            else:
                raise
        out_path.write_text(text + "\n", encoding="utf-8")

    # --- merge ---
    draft = merge_workers(run_dir, plan)
    (run_dir / "draft_merged.md").write_text(draft, encoding="utf-8")

    # --- finalize ---
    final_path = run_dir / "final_broadcast.md"
    if args.skip_finalize:
        final_path.write_text(draft, encoding="utf-8")
        print(f"PIPELINE_OK skip_finalize -> {final_path}")
    elif not api_key:
        print("[pipeline] no OPENAI_API_KEY: copy draft to final (may fail verify)", file=sys.stderr)
        final_path.write_text(draft, encoding="utf-8")
    else:
        fin_sys = finalize_system_prompt(cfg, plan)
        fin_user = "工人合并草稿如下，请输出最终成稿：\n\n" + draft
        final_text = openai_chat(
            base_url, api_key, orch_model, fin_sys, fin_user, args.openai_timeout * 2
        )
        final_path.write_text(final_text.strip() + "\n", encoding="utf-8")

    if not args.skip_verify:
        verify_text = load_verify_text()
        ok, errors = verify_text(final_path.read_text(encoding="utf-8"), cfg)
        if not ok:
            print("VERIFY_DRAFT_FAIL", file=sys.stderr)
            for err in errors:
                print(err, file=sys.stderr)
            save_json(run_dir / "verify_errors.json", {"errors": errors})
            return 3

    print("PIPELINE_OK", run_dir)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
