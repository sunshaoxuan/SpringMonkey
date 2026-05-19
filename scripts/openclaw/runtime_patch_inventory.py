#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_DIST = Path("/usr/lib/node_modules/openclaw/dist")
DEFAULT_REPO = Path("/var/lib/openclaw/repos/SpringMonkey")
DEFAULT_WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
DEFAULT_QUEUE = Path("/var/lib/openclaw/.openclaw/delivery-queue")
DEFAULT_OWNER_USER_ID = "999666719356354610"


@dataclass(frozen=True)
class PatchSpec:
    patch_id: str
    description: str
    selectors: tuple[str, ...]
    required_markers: tuple[str, ...]
    installer: str
    required: bool = True


PATCH_SPECS = (
    PatchSpec(
        patch_id="agent_society_runtime",
        description="Agent society task loop, kernel bridge, and self-improvement runtime protocol",
        selectors=("agent-runner.runtime-*.js",),
        required_markers=(
            "[runtime-goal-intent-task-agent-society-protocol]",
            "shouldApplyAgentSocietyProtocol",
            "extract all relevant intents",
            "create or refine a helper tool",
            "[runtime-self-improvement-toolsmith-protocol]",
            "classify the failure into a capability gap",
            "[runtime-kernel-session]",
            "ensure-session",
        ),
        installer="scripts/remote_install_agent_society_startup_guard.py",
    ),
    PatchSpec(
        patch_id="preemptive_compaction",
        description="Proactive compaction guard for long context before hard overflow",
        selectors=("preemptive-compaction-*.js", "selection-*.js"),
        required_markers=(
            "const proactiveThresholdTokens = Math.max(1, Math.floor(promptBudgetBeforeReserve * .9));",
            "const proactiveMessageThreshold = 48;",
        ),
        installer="scripts/remote_install_preemptive_compaction_guard.py",
    ),
    PatchSpec(
        patch_id="memory_lancedb_raw_embeddings",
        description="LanceDB memory raw embedding, autocapture, and text fallback compatibility",
        selectors=(
            "extensions/memory-lancedb/index.js",
            "../.openclaw/npm/node_modules/@openclaw/memory-lancedb/dist/index.js",
        ),
        required_markers=(
            "const response = await fetch(`${baseUrl}/embeddings`, {",
            "Embeddings dimension mismatch: expected ${expectedDims}, got ${vector.length}",
            "function stripConversationMetadata(text) {",
            "async textSearch(queryText, limit = 5)",
            "vector search failed, using text fallback",
        ),
        installer="scripts/remote_install_memory_lancedb_guard.py",
    ),
)


def run_text(command: list[str], timeout: int = 8) -> str:
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return (proc.stdout or proc.stderr or "").strip()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def candidate_paths(spec: PatchSpec, *, dist: Path, repo: Path) -> list[Path]:
    paths: list[Path] = []
    for selector in spec.selectors:
        if "*" in selector:
            paths.extend(path for path in dist.glob(selector) if path.is_file())
            continue
        path = (dist / selector).resolve()
        if path.is_file():
            paths.append(path)
            continue
        repo_relative = (repo / selector).resolve()
        if repo_relative.is_file():
            paths.append(repo_relative)
    return sorted(set(paths), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)


def score_candidate(path: Path, markers: tuple[str, ...]) -> tuple[int, int]:
    text = read_text(path)
    marker_hits = sum(1 for marker in markers if marker in text)
    size = path.stat().st_size if path.exists() else 0
    return marker_hits, size


def inspect_patch(spec: PatchSpec, *, dist: Path, repo: Path) -> dict[str, Any]:
    candidates = candidate_paths(spec, dist=dist, repo=repo)
    if not candidates:
        return {
            "patch_id": spec.patch_id,
            "description": spec.description,
            "status": "missing_artifact",
            "required": spec.required,
            "installer": spec.installer,
            "selected": "",
            "missing_markers": list(spec.required_markers),
            "candidates": [],
        }
    selected = sorted(candidates, key=lambda item: score_candidate(item, spec.required_markers), reverse=True)[0]
    text = read_text(selected)
    missing = [marker for marker in spec.required_markers if marker not in text]
    return {
        "patch_id": spec.patch_id,
        "description": spec.description,
        "status": "ok" if not missing else "missing_markers",
        "required": spec.required,
        "installer": spec.installer,
        "selected": str(selected),
        "missing_markers": missing,
        "candidates": [str(path) for path in candidates[:8]],
    }


def inspect_repo_capabilities(repo: Path) -> list[dict[str, Any]]:
    required_files = {
        "capability_repair_runner": "scripts/openclaw/capability_repair_runner.py",
        "toolsmith_repair_runner": "scripts/openclaw/toolsmith_repair_runner.py",
        "regression_repair_runner": "scripts/openclaw/regression_repair_runner.py",
        "long_task_supervisor": "scripts/openclaw/long_task_supervisor.py",
        "discord_media_delivery": "scripts/openclaw/discord_media_delivery.py",
        "capability_baseline": "config/openclaw/capability_baseline_cases.json",
        "intent_tool_registry": "config/openclaw/intent_tools.json",
    }
    results: list[dict[str, Any]] = []
    for capability, rel in required_files.items():
        path = repo / rel
        results.append(
            {
                "capability": capability,
                "path": str(path),
                "status": "ok" if path.is_file() else "missing",
            }
        )
    return results


def inspect_delivery_queue(queue_dir: Path, owner_user_id: str) -> dict[str, Any]:
    if not queue_dir.is_dir():
        return {"status": "missing", "queue_dir": str(queue_dir), "bad_owner_channel_targets": []}
    bad: list[str] = []
    pending = 0
    for path in queue_dir.glob("*.json"):
        pending += 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("to") == f"channel:{owner_user_id}":
            bad.append(path.name)
    return {
        "status": "ok" if not bad else "bad_owner_channel_target",
        "queue_dir": str(queue_dir),
        "pending_files": pending,
        "bad_owner_channel_targets": bad,
    }


def build_inventory(args: argparse.Namespace) -> dict[str, Any]:
    dist = Path(args.dist)
    repo = Path(args.repo_root)
    queue_dir = Path(args.delivery_queue)
    patches = [inspect_patch(spec, dist=dist, repo=repo) for spec in PATCH_SPECS]
    repo_caps = inspect_repo_capabilities(repo)
    queue = inspect_delivery_queue(queue_dir, args.owner_user_id)
    failures = [
        item["patch_id"]
        for item in patches
        if item.get("required") and item.get("status") != "ok"
    ]
    failures.extend(item["capability"] for item in repo_caps if item["status"] != "ok")
    if queue["status"] == "bad_owner_channel_target":
        failures.append("delivery_queue_owner_target")
    return {
        "openclaw_version": run_text(["openclaw", "--version"]),
        "node_version": run_text(["node", "--version"]),
        "dist": str(dist),
        "repo_root": str(repo),
        "patches": patches,
        "repo_capabilities": repo_caps,
        "delivery_queue": queue,
        "status": "ok" if not failures else "failed",
        "failures": failures,
    }


def print_text(inventory: dict[str, Any]) -> None:
    print(f"OpenClaw: {inventory['openclaw_version']}")
    print(f"Node: {inventory['node_version']}")
    print(f"Repo: {inventory['repo_root']}")
    print(f"Dist: {inventory['dist']}")
    print("Runtime patches:")
    for item in inventory["patches"]:
        print(f"- {item['patch_id']}: {item['status']} selected={item['selected']}")
        if item["missing_markers"]:
            print(f"  missing={item['missing_markers']}")
        print(f"  installer={item['installer']}")
    print("Repo capabilities:")
    for item in inventory["repo_capabilities"]:
        print(f"- {item['capability']}: {item['status']} path={item['path']}")
    queue = inventory["delivery_queue"]
    print(f"Delivery queue: {queue['status']} pending={queue.get('pending_files', 0)}")
    if queue.get("bad_owner_channel_targets"):
        print(f"  bad_owner_channel_targets={queue['bad_owner_channel_targets']}")
    print(f"Overall: {inventory['status']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory SpringMonkey runtime patches that can be lost by OpenClaw upgrades.")
    parser.add_argument("--dist", default=str(DEFAULT_DIST))
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO))
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    parser.add_argument("--delivery-queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--owner-user-id", default=DEFAULT_OWNER_USER_ID)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-missing", action="store_true")
    args = parser.parse_args()
    inventory = build_inventory(args)
    if args.json:
        print(json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(inventory)
    if args.fail_on_missing and inventory["status"] != "ok":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
