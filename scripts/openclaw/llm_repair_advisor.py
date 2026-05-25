#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from model_fallback_client import chat_with_fallback


@dataclass(frozen=True)
class RepairAdvice:
    status: str
    provider: str
    model: str
    fallback_used: bool
    failure_class: str
    root_cause: str
    next_actions: list[str]
    verification_plan: list[str]
    replay_policy: str
    raw_response: str
    error: str = ""


def tail(text: str, limit: int = 5000) -> str:
    return (text or "")[-limit:]


def load_json_file(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("repair advice response is not a JSON object")
    return data


def normalize_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def build_messages(
    *,
    task_text: str,
    failure_stage: str,
    failure_reason: str,
    stdout: str = "",
    stderr: str = "",
    package_state: dict[str, Any] | None = None,
    repo_status: str = "",
) -> list[dict[str, str]]:
    package_view = package_state or {}
    system = (
        "You are a repair planning model for an autonomous coding harness. "
        "Return strict JSON only. Do not suggest external side effects. "
        "Prefer root cause, code change target, test target, and replay gate."
    )
    user = "\n".join(
        [
            "Task:",
            task_text.strip() or "(empty)",
            "",
            "Failure stage:",
            failure_stage.strip() or "(unknown)",
            "",
            "Failure reason:",
            failure_reason.strip() or "(unknown)",
            "",
            "Package state:",
            json.dumps(package_view, ensure_ascii=False, indent=2, sort_keys=True)[:4000],
            "",
            "Repo status:",
            tail(repo_status, 2000) or "(not supplied)",
            "",
            "Stdout tail:",
            tail(stdout),
            "",
            "Stderr tail:",
            tail(stderr),
            "",
            "Return JSON with keys: failure_class, root_cause, next_actions, verification_plan, replay_policy.",
            "Allowed replay_policy values: do_not_replay, replay_after_verified_commit, awaiting_external_authorization.",
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def get_repair_advice(
    *,
    task_text: str,
    failure_stage: str,
    failure_reason: str,
    stdout: str = "",
    stderr: str = "",
    package_state: dict[str, Any] | None = None,
    repo_status: str = "",
    model_caller: Callable[..., tuple[str, dict[str, Any]]] | None = None,
) -> RepairAdvice:
    caller = model_caller or chat_with_fallback
    try:
        content, meta = caller(
            build_messages(
                task_text=task_text,
                failure_stage=failure_stage,
                failure_reason=failure_reason,
                stdout=stdout,
                stderr=stderr,
                package_state=package_state,
                repo_status=repo_status,
            ),
            timeout=45,
            temperature=0,
        )
        payload = parse_json_object(content)
        return RepairAdvice(
            status="ok",
            provider=str(meta.get("provider") or ""),
            model=str(meta.get("model") or ""),
            fallback_used=bool(meta.get("fallback_used")),
            failure_class=str(payload.get("failure_class") or "unclassified_failure"),
            root_cause=str(payload.get("root_cause") or "").strip(),
            next_actions=normalize_str_list(payload.get("next_actions")),
            verification_plan=normalize_str_list(payload.get("verification_plan")),
            replay_policy=str(payload.get("replay_policy") or "do_not_replay"),
            raw_response=content,
        )
    except Exception as exc:
        return RepairAdvice(
            status="failed",
            provider="",
            model="",
            fallback_used=False,
            failure_class="advisor_failed",
            root_cause="",
            next_actions=[],
            verification_plan=[],
            replay_policy="do_not_replay",
            raw_response="",
            error=f"{type(exc).__name__}: {exc}",
        )


def format_advice_for_report(advice: RepairAdvice) -> str:
    if advice.status != "ok":
        return f"模型修复建议生成失败：{advice.error}"
    actions = "\n".join(f"- {item}" for item in advice.next_actions[:5]) or "- 未给出下一步"
    verifies = "\n".join(f"- {item}" for item in advice.verification_plan[:5]) or "- 未给出验证计划"
    return "\n".join(
        [
            "模型修复建议",
            f"模型：{advice.provider}/{advice.model}" if advice.provider or advice.model else "模型：unknown",
            f"失败分类：{advice.failure_class}",
            f"根因：{advice.root_cause or '未给出'}",
            "下一步：",
            actions,
            "验证：",
            verifies,
            f"重试策略：{advice.replay_policy}",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask the configured LLM for a bounded repair route after an internal failure.")
    parser.add_argument("--task-text", default="")
    parser.add_argument("--failure-stage", required=True)
    parser.add_argument("--failure-reason", required=True)
    parser.add_argument("--stdout-file", type=Path)
    parser.add_argument("--stderr-file", type=Path)
    parser.add_argument("--package-state", type=Path)
    parser.add_argument("--repo-status", default="")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stdout = args.stdout_file.read_text(encoding="utf-8", errors="replace") if args.stdout_file and args.stdout_file.is_file() else ""
    stderr = args.stderr_file.read_text(encoding="utf-8", errors="replace") if args.stderr_file and args.stderr_file.is_file() else ""
    advice = get_repair_advice(
        task_text=args.task_text,
        failure_stage=args.failure_stage,
        failure_reason=args.failure_reason,
        stdout=stdout,
        stderr=stderr,
        package_state=load_json_file(args.package_state),
        repo_status=args.repo_status,
    )
    if args.json:
        print(json.dumps(asdict(advice), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_advice_for_report(advice))
    return 0 if advice.status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
