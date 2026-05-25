from __future__ import annotations

import json
import subprocess
from pathlib import Path

import model_discovery_tool as tool


def test_discover_image_models_reads_provider_json_lines() -> None:
    provider = {
        "id": "openai",
        "available": True,
        "configured": True,
        "selected": False,
        "models": ["gpt-image-2", "chatgpt-image-latest"],
    }

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="warning\n" + json.dumps(provider) + "\n", stderr="")

    candidates, _detail = tool.discover_image_models(command_runner=fake_run)

    assert [item.model_ref for item in candidates] == ["openai/gpt-image-2", "openai/chatgpt-image-latest"]
    assert candidates[0].configured is True


def test_build_image_report_without_probe_returns_configured_candidates() -> None:
    provider = {
        "id": "openai",
        "available": True,
        "configured": True,
        "selected": False,
        "models": ["gpt-image-2"],
    }

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(provider) + "\n", stderr="")

    report = tool.build_report("image", command_runner=fake_run)

    assert report["status"] == "ok"
    assert report["usable_candidates"] == ["openai/gpt-image-2"]


def test_build_image_report_with_probe_rejects_endpoint_failure(monkeypatch, tmp_path: Path) -> None:
    provider = {
        "id": "openai",
        "available": True,
        "configured": True,
        "selected": False,
        "models": ["gpt-image-2"],
    }
    monkeypatch.setenv("OPENCLAW_MODEL_DISCOVERY_PROBE_OUTPUT", str(tmp_path / "probe.png"))

    def fake_run(cmd, **kwargs):
        if cmd[:4] == ["openclaw", "infer", "image", "providers"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(provider) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="endpoint not supported")

    report = tool.build_report("image", probe=True, command_runner=fake_run)

    assert report["status"] == "no_usable_model"
    assert report["usable_candidates"] == []
    assert report["probe_results"][0]["model_ref"] == "openai/gpt-image-2"
    assert report["probe_results"][0]["ok"] is False
    assert report["probe_results"][0]["failure_kind"] == "generation_endpoint_unsupported"


def test_discover_text_models_parses_model_list_table() -> None:
    stdout = """Model                                      Input      Ctx
openai/gpt-5.5                             text       191k
ollama/qwen3:14b                           text       32k
"""

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    models, _detail = tool.discover_text_models(command_runner=fake_run)

    assert [item["model_ref"] for item in models] == ["openai/gpt-5.5", "ollama/qwen3:14b"]


def test_classify_image_probe_failure_distinguishes_catalog_from_endpoint() -> None:
    assert tool.classify_image_probe_failure("HTTP 404 endpoint not supported") == "generation_endpoint_unsupported"
    assert tool.classify_image_probe_failure("code=model_not_available") == "model_not_available_for_key"
    assert tool.classify_image_probe_failure("model is not supported when using Codex with a ChatGPT account") == "account_does_not_support_image_model"
