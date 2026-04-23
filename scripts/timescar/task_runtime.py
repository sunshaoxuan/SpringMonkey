#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any


WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
TRACE_DIR = WORKSPACE / "state" / "timescar_traces"
GUARD_SCRIPT = WORKSPACE / "scripts" / "timescar_task_guard.py"


def now_ms() -> int:
    return int(time.time() * 1000)


def _safe_text(value: Any) -> str:
    return str(value).strip()


class TimesCarTaskRuntime:
    def __init__(self, job_name: str, mode: str, ttl_seconds: int = 1800) -> None:
        self.job_name = job_name
        self.mode = mode
        self.ttl_seconds = ttl_seconds
        self.run_id = f"{job_name}-{uuid.uuid4().hex[:10]}"
        self.trace_path = TRACE_DIR / f"{job_name}.latest.json"
        self.state: dict[str, Any] = {
            "version": 1,
            "job": job_name,
            "mode": mode,
            "runId": self.run_id,
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "status": "created",
            "startedAtMs": now_ms(),
            "updatedAtMs": now_ms(),
            "currentPhase": "created",
            "steps": [],
            "finalMessage": "",
        }

    def start(self, phase: str) -> None:
        self.state["status"] = "running"
        self.state["currentPhase"] = phase
        self.state["updatedAtMs"] = now_ms()
        self._guard("start", phase)
        self._write_trace()

    def heartbeat(self, phase: str, note: str = "") -> None:
        self.state["currentPhase"] = phase
        self.state["updatedAtMs"] = now_ms()
        if note:
            self.state["lastNote"] = _safe_text(note)
        self._guard("heartbeat", phase)
        self._write_trace()

    def record_step(
        self,
        *,
        step: str,
        status: str,
        tool: str = "",
        detail: str = "",
        observation: str = "",
    ) -> None:
        self.state["updatedAtMs"] = now_ms()
        self.state["currentPhase"] = step
        self.state["steps"].append(
            {
                "step": _safe_text(step),
                "status": _safe_text(status),
                "tool": _safe_text(tool),
                "detail": _safe_text(detail),
                "observation": _safe_text(observation),
                "atMs": now_ms(),
            }
        )
        self._write_trace()

    def finish(self, status: str, phase: str, final_message: str = "") -> None:
        self.state["status"] = status
        self.state["currentPhase"] = phase
        self.state["updatedAtMs"] = now_ms()
        self.state["finishedAtMs"] = now_ms()
        self.state["finalMessage"] = final_message
        self._guard("finish", phase, status=status)
        self._write_trace()

    def _guard(self, action: str, phase: str, status: str = "") -> None:
        if not GUARD_SCRIPT.is_file():
            return
        cmd = ["python3", str(GUARD_SCRIPT), action]
        if action == "start":
            cmd += ["--job", self.job_name, "--mode", self.mode, "--ttl-seconds", str(self.ttl_seconds), "--phase", phase]
        elif action == "heartbeat":
            cmd += ["--phase", phase]
        elif action == "finish":
            cmd += ["--status", status, "--phase", phase]
        try:
            subprocess.check_output(cmd, text=True)
        except Exception as exc:
            self.state.setdefault("guardErrors", []).append(_safe_text(exc))

    def _write_trace(self) -> None:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = self.trace_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.trace_path)

