#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable


REPO = Path(os.environ.get("SPRINGMONKEY_REPO", Path(__file__).resolve().parents[2]))
DEFAULT_TIMEOUT_SECONDS = 120


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class ModelCandidate:
    provider: str
    model: str
    model_ref: str
    configured: bool
    selected: bool
    available: bool


@dataclass(frozen=True)
class ProbeResult:
    model_ref: str
    ok: bool
    detail: str


def run_openclaw(args: list[str], *, command_runner: CommandRunner = subprocess.run, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("HOME", "/var/lib/openclaw")
    return command_runner(
        ["openclaw", *args],
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=env,
    )


def json_lines(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line.startswith("{") or not line.endswith("}"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def discover_image_models(*, command_runner: CommandRunner = subprocess.run) -> tuple[list[ModelCandidate], str]:
    proc = run_openclaw(["infer", "image", "providers"], command_runner=command_runner)
    detail = (proc.stderr or proc.stdout or "").strip()
    providers = json_lines((proc.stdout or "") + "\n" + (proc.stderr or ""))
    candidates: list[ModelCandidate] = []
    for provider in providers:
        provider_id = str(provider.get("id") or "").strip()
        models = provider.get("models")
        if not provider_id or not isinstance(models, list):
            continue
        for model in models:
            model_id = str(model).strip()
            if not model_id:
                continue
            candidates.append(
                ModelCandidate(
                    provider=provider_id,
                    model=model_id,
                    model_ref=f"{provider_id}/{model_id}",
                    configured=bool(provider.get("configured")),
                    selected=bool(provider.get("selected")),
                    available=bool(provider.get("available")),
                )
            )
    return candidates, detail[-1200:]


def discover_text_models(*, command_runner: CommandRunner = subprocess.run) -> tuple[list[dict[str, Any]], str]:
    proc = run_openclaw(["models", "list"], command_runner=command_runner)
    rows: list[dict[str, Any]] = []
    for raw in (proc.stdout or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("Model ") or line.startswith("OpenClaw "):
            continue
        parts = line.split()
        if len(parts) < 2 or "/" not in parts[0]:
            continue
        rows.append({"model_ref": parts[0], "input": parts[1], "raw": line})
    return rows, (proc.stderr or proc.stdout or "").strip()[-1200:]


def probe_image_model(model_ref: str, *, command_runner: CommandRunner = subprocess.run, timeout_ms: int = 30_000) -> ProbeResult:
    output = Path(os.environ.get("OPENCLAW_MODEL_DISCOVERY_PROBE_OUTPUT", "/tmp/openclaw-model-discovery-probe.png"))
    proc = run_openclaw(
        [
            "infer",
            "image",
            "generate",
            "--model",
            model_ref,
            "--prompt",
            "single simple weather icon probe image, no text",
            "--size",
            "1024x1024",
            "--output-format",
            "png",
            "--output",
            str(output),
            "--timeout-ms",
            str(timeout_ms),
            "--json",
        ],
        command_runner=command_runner,
        timeout=max(60, timeout_ms // 1000 + 60),
    )
    detail = (proc.stderr or proc.stdout or "").strip()
    ok = proc.returncode == 0 and output.exists() and output.stat().st_size > 1000
    return ProbeResult(model_ref=model_ref, ok=ok, detail=detail[-1200:])


def build_report(kind: str, *, probe: bool = False, command_runner: CommandRunner = subprocess.run) -> dict[str, Any]:
    if kind == "image":
        candidates, detail = discover_image_models(command_runner=command_runner)
        configured = [item for item in candidates if item.configured and item.available]
        probe_results: list[ProbeResult] = []
        if probe:
            for item in configured:
                probe_results.append(probe_image_model(item.model_ref, command_runner=command_runner))
        usable = [result.model_ref for result in probe_results if result.ok] if probe else [item.model_ref for item in configured]
        return {
            "kind": "image",
            "status": "ok" if usable else "no_usable_model",
            "usable_candidates": usable,
            "configured_candidates": [asdict(item) for item in configured],
            "all_candidates": [asdict(item) for item in candidates],
            "probe_results": [asdict(item) for item in probe_results],
            "diagnostic": detail,
        }
    if kind == "text":
        models, detail = discover_text_models(command_runner=command_runner)
        return {"kind": "text", "status": "ok" if models else "no_models", "models": models, "diagnostic": detail}
    raise ValueError(f"unsupported kind: {kind}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover currently configured OpenClaw model candidates.")
    parser.add_argument("--kind", choices=["image", "text"], default="image")
    parser.add_argument("--probe", action="store_true", help="Run a small provider call to prove the candidate actually works.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.kind, probe=args.probe)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"模型类型：{report['kind']}")
        print(f"状态：{report['status']}")
        if report.get("usable_candidates"):
            print("可用候选：" + "、".join(report["usable_candidates"]))
        elif report.get("models"):
            print("模型：" + "、".join(item["model_ref"] for item in report["models"]))
        else:
            print("可用候选：无")
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
