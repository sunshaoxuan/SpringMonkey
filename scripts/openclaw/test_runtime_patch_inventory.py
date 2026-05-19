from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.openclaw import runtime_patch_inventory as inventory


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        dist=str(tmp_path / "dist"),
        repo_root=str(tmp_path / "repo"),
        workspace=str(tmp_path / "workspace"),
        delivery_queue=str(tmp_path / "queue"),
        owner_user_id="owner",
        json=False,
        fail_on_missing=False,
    )


def seed_required_repo(repo: Path) -> None:
    for rel in (
        "scripts/openclaw/capability_repair_runner.py",
        "scripts/openclaw/toolsmith_repair_runner.py",
        "scripts/openclaw/regression_repair_runner.py",
        "scripts/openclaw/long_task_supervisor.py",
        "scripts/openclaw/discord_media_delivery.py",
        "config/openclaw/capability_baseline_cases.json",
        "config/openclaw/intent_tools.json",
    ):
        write(repo / rel, "{}" if rel.endswith(".json") else "# ok\n")


def test_inventory_passes_when_runtime_markers_and_repo_capabilities_exist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(inventory, "run_text", lambda command, timeout=8: "test-version")
    dist = tmp_path / "dist"
    repo = tmp_path / "repo"
    seed_required_repo(repo)
    write(
        dist / "agent-runner.runtime-test.js",
        "\n".join(
            [
                "[runtime-goal-intent-task-agent-society-protocol]",
                "shouldApplyAgentSocietyProtocol",
                "extract all relevant intents",
                "create or refine a helper tool",
                "[runtime-self-improvement-toolsmith-protocol]",
                "classify the failure into a capability gap",
                "[runtime-kernel-session]",
                "ensure-session",
            ]
        ),
    )
    write(
        dist / "preemptive-compaction-test.js",
        'const proactiveThresholdTokens = Math.max(1, Math.floor(promptBudgetBeforeReserve * .9));\nconst proactiveMessageThreshold = 48;\n',
    )
    write(
        dist / "extensions" / "memory-lancedb" / "index.js",
        "\n".join(
            [
                "const response = await fetch(`${baseUrl}/embeddings`, {",
                "Embeddings dimension mismatch: expected ${expectedDims}, got ${vector.length}",
                "function stripConversationMetadata(text) {",
                "async textSearch(queryText, limit = 5)",
                "vector search failed, using text fallback",
            ]
        ),
    )

    result = inventory.build_inventory(args(tmp_path))

    assert result["status"] == "ok"
    assert result["failures"] == []


def test_inventory_fails_on_legacy_owner_channel_queue_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(inventory, "run_text", lambda command, timeout=8: "test-version")
    dist = tmp_path / "dist"
    repo = tmp_path / "repo"
    seed_required_repo(repo)
    write(
        dist / "agent-runner.runtime-test.js",
        "[runtime-goal-intent-task-agent-society-protocol]\nshouldApplyAgentSocietyProtocol\nextract all relevant intents\ncreate or refine a helper tool\n[runtime-self-improvement-toolsmith-protocol]\nclassify the failure into a capability gap\n[runtime-kernel-session]\nensure-session\n",
    )
    write(
        dist / "selection-test.js",
        'const proactiveThresholdTokens = Math.max(1, Math.floor(promptBudgetBeforeReserve * .9));\nconst proactiveMessageThreshold = 48;\n',
    )
    write(
        dist / "extensions" / "memory-lancedb" / "index.js",
        "const response = await fetch(`${baseUrl}/embeddings`, {\nEmbeddings dimension mismatch: expected ${expectedDims}, got ${vector.length}\nfunction stripConversationMetadata(text) {\nasync textSearch(queryText, limit = 5)\nvector search failed, using text fallback\n",
    )
    queue = tmp_path / "queue"
    queue.mkdir()
    (queue / "bad.json").write_text(json.dumps({"to": "channel:owner"}), encoding="utf-8")

    result = inventory.build_inventory(args(tmp_path))

    assert result["status"] == "failed"
    assert "delivery_queue_owner_target" in result["failures"]


def test_memory_lancedb_external_plugin_counts_as_ok_when_dist_artifact_is_absent(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command: list[str], timeout: int = 8) -> str:
        if command[:3] == ["openclaw", "plugins", "inspect"]:
            return "Status: loaded"
        return "test-version"

    monkeypatch.setattr(inventory, "run_text", fake_run)
    dist = tmp_path / "dist"
    repo = tmp_path / "repo"
    seed_required_repo(repo)
    write(
        dist / "agent-runner.runtime-test.js",
        "[runtime-goal-intent-task-agent-society-protocol]\nshouldApplyAgentSocietyProtocol\nextract all relevant intents\ncreate or refine a helper tool\n[runtime-self-improvement-toolsmith-protocol]\nclassify the failure into a capability gap\n[runtime-kernel-session]\nensure-session\n",
    )
    write(
        dist / "selection-test.js",
        'const proactiveThresholdTokens = Math.max(1, Math.floor(promptBudgetBeforeReserve * .9));\nconst proactiveMessageThreshold = 48;\n',
    )

    result = inventory.build_inventory(args(tmp_path))

    assert result["status"] == "ok"
    memory = next(item for item in result["patches"] if item["patch_id"] == "memory_lancedb_raw_embeddings")
    assert memory["status"] == "ok_external_plugin"
