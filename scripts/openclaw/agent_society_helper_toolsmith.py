#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "helper_tool"


def infer_helper_category(helper_name: str, purpose: str, category: str | None) -> str:
    if category:
        return category
    lowered = f"{helper_name} {purpose}".lower()
    if "timeout" in lowered or "stall" in lowered or "hang" in lowered:
        return "runtime_timeout"
    if "missing" in lowered or "no tool" in lowered or "unsupported" in lowered:
        return "tool_missing"
    if "blocked" in lowered or "no response" in lowered:
        return "execution_blocked"
    if "drift" in lowered or "bundle" in lowered or "patch" in lowered:
        return "runtime_drift"
    if (
        "browser" in lowered
        or "chrome" in lowered
        or "cdp" in lowered
        or "targetid" in lowered
        or "tab" in lowered
        or "selector" in lowered
    ):
        return "browser_control"
    return "generic"


def purpose_hash(purpose: str) -> str:
    return hashlib.sha1(purpose.strip().encode("utf-8")).hexdigest()[:12]


def render_helper(helper_name: str, purpose: str, category: str) -> str:
    contract = {
        "helper_name": helper_name,
        "purpose": purpose,
        "purpose_hash": purpose_hash(purpose),
        "category": category,
    }
    return f"""#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


HELPER_CONTRACT = {json.dumps(contract, ensure_ascii=False, indent=2)}


def collect_checks(repo_root: Path, observation: str) -> tuple[list[dict[str, object]], list[str]]:
    checks: list[dict[str, object]] = []
    suggestions: list[str] = []
    expected = [
        "scripts/openclaw/agent_society_runtime_record_gap.py",
        "scripts/openclaw/agent_society_helper_toolsmith.py",
        "scripts/openclaw/agent_society_kernel.py",
    ]
    for rel in expected:
        path = repo_root.joinpath(*rel.split("/"))
        checks.append({{
            "kind": "path_exists",
            "path": rel,
            "ok": path.exists(),
        }})
    lowered = observation.lower()
    category = HELPER_CONTRACT["category"]
    if category == "runtime_timeout":
        suggestions.append("inspect direct-task timeout and first-response watchdog thresholds before retrying")
        if "line" in lowered or "response" in lowered:
            suggestions.append("verify LINE direct visibility watchdog and no-response fallback are both patched in the active runtime")
    elif category == "execution_blocked":
        suggestions.append("classify whether the block is channel delivery, runtime execution, or missing target discovery")
        if "no response" in lowered:
            suggestions.append("check whether no-response fallback is present before escalating to model/runtime diagnosis")
    elif category == "tool_missing":
        suggestions.append("identify the smallest missing helper or runtime probe and add it as a bounded repo script")
    elif category == "runtime_drift":
        suggestions.append("probe the active bundle by content markers instead of relying on filenames")
    elif category == "browser_control":
        suggestions.append("verify persistent host Chrome CDP status before retrying browser automation")
        suggestions.append("use a live CDP target instead of stale OpenClaw browser targetId/ref values")
    else:
        suggestions.append("reduce the failure into a bounded observable probe before proposing a larger repair")
    return checks, suggestions


def build_repair_workflow(observation: str) -> list[dict[str, str]]:
    category = HELPER_CONTRACT["category"]
    if category == "runtime_timeout":
        return [
            {{"step": "classify timeout surface", "action": "separate model wait, tool wait, and delivery wait using current observation"}},
            {{"step": "verify timeout guard", "action": "inspect active watchdog / timeout thresholds and compare them against the observed hang stage"}},
            {{"step": "apply bounded repair path", "action": "prefer timeout-specific helper or retry policy before changing unrelated runtime paths"}},
            {{"step": "verify visible recovery", "action": "confirm a later run emits visible progress or a concrete blocker instead of silent hanging"}},
        ]
    if category == "runtime_drift":
        return [
            {{"step": "identify active artifact", "action": "probe the currently active bundle or runtime file by content markers, not filenames"}},
            {{"step": "check expected anchor contract", "action": "verify the intended marker, anchor, or injected protocol still exists in the active artifact"}},
            {{"step": "repair active target only", "action": "patch the current active artifact and avoid editing stale filenames"}},
            {{"step": "re-verify markers", "action": "confirm required runtime markers exist after repair before trusting the fix"}},
        ]
    if category == "browser_control":
        return [
            {{"step": "prove browser substrate", "action": "run the CDP helper status check and verify the host Chrome is reachable and not headless-like"}},
            {{"step": "reselect live target", "action": "list current CDP page targets and pick a live non-blank tab before every action"}},
            {{"step": "act through CDP fallback", "action": "use the CDP helper open/inspect/click/type/wait-text commands when browser tool refs or target ids drift"}},
            {{"step": "report real blocker", "action": "if the site blocks progress, report the page text and URL as blocker evidence instead of asking the user to open a local browser"}},
        ]
    if category == "tool_missing":
        return [
            {{"step": "identify missing capability", "action": "narrow the exact missing tool, helper, or probe instead of broad retrying"}},
            {{"step": "generate bounded helper", "action": "add the smallest repo helper that closes the missing capability gap"}},
            {{"step": "validate helper output", "action": "run the helper and check that it produces structured ready output"}},
            {{"step": "promote if reusable", "action": "register the helper only if validation proves it is reusable"}},
        ]
    if category == "execution_blocked":
        return [
            {{"step": "classify block layer", "action": "separate channel delivery, runtime execution, access blocker, and target-discovery blocker"}},
            {{"step": "pick narrow repair path", "action": "use the smallest repair path that directly addresses the blocking layer"}},
            {{"step": "verify unblock", "action": "confirm the task now yields visible progress, concrete output, or an explicit blocker"}},
        ]
    return [
        {{"step": "reduce to bounded probe", "action": "turn the failure into a smaller observable repair loop before wider changes"}},
    ]


def assess_drift(checks: list[dict[str, object]], repair_workflow: list[dict[str, str]], observation: str) -> dict[str, object]:
    reasons: list[str] = []
    if not repair_workflow:
        reasons.append("repair workflow is empty")
    missing = [check["path"] for check in checks if not check.get("ok")]
    if missing:
        reasons.append("missing expected repo paths: " + ", ".join(missing))
    lowered = observation.lower()
    category = HELPER_CONTRACT["category"]
    if category == "runtime_timeout" and not any(token in lowered for token in ("timeout", "timed out", "stalled", "hang", "hung", "卡住", "response")):
        reasons.append("observation no longer looks like a timeout-shaped failure")
    if category == "runtime_drift" and not any(token in lowered for token in ("drift", "bundle", "anchor", "selector", "patch", "upgrade")):
        reasons.append("observation no longer looks like runtime drift")
    if category == "browser_control" and not any(
        token in lowered
        for token in ("browser", "chrome", "cdp", "targetid", "tab", "selector", "headless", "profile", "google", "signup")
    ):
        reasons.append("observation no longer looks like browser-control drift")
    if category == "tool_missing" and not any(token in lowered for token in ("missing", "not found", "unsupported", "helper", "tool")):
        reasons.append("observation no longer looks like tool-missing")
    if category == "execution_blocked" and not any(token in lowered for token in ("blocked", "no response", "stuck", "silent", "empty result")):
        reasons.append("observation no longer looks like execution-blocked")
    return {{
        "ok": not reasons,
        "reasons": reasons,
        "purpose_hash": HELPER_CONTRACT["purpose_hash"],
    }}


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded business repairer generated by the agent society toolsmith.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--observation", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root)
    checks, suggestions = collect_checks(repo_root, args.observation)
    repair_workflow = build_repair_workflow(args.observation)
    drift = assess_drift(checks, repair_workflow, args.observation)
    payload = {{
        "helper_name": HELPER_CONTRACT["helper_name"],
        "purpose": HELPER_CONTRACT["purpose"],
        "category": HELPER_CONTRACT["category"],
        "status": "ready" if drift["ok"] else "drifted",
        "repo_root": str(repo_root),
        "contract": HELPER_CONTRACT,
        "checks": checks,
        "suggested_actions": suggestions,
        "repair_workflow": repair_workflow,
        "drift": drift,
    }}
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def create_helper_tool(repo_root: Path, helper_name: str, purpose: str, category: str | None = None) -> dict[str, object]:
    target_dir = repo_root / "scripts" / "openclaw" / "helpers"
    target_dir.mkdir(parents=True, exist_ok=True)

    inferred_category = infer_helper_category(helper_name, purpose, category)
    slug = normalize_slug(helper_name)
    target = target_dir / f"{slug}.py"
    target.write_text(render_helper(helper_name, purpose, inferred_category), encoding="utf-8")
    target.chmod(0o755)
    return {
        "helper_name": helper_name,
        "entrypoint": str(target.relative_to(repo_root)).replace("\\", "/"),
        "created": True,
        "category": inferred_category,
        "purpose_hash": purpose_hash(purpose),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a bounded executable helper tool in the repo.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--helper-name", required=True)
    parser.add_argument("--purpose", required=True)
    parser.add_argument("--category")
    args = parser.parse_args()

    payload = create_helper_tool(
        repo_root=Path(args.repo_root),
        helper_name=args.helper_name,
        purpose=args.purpose,
        category=args.category,
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
