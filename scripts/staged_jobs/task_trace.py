#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import time
import uuid
from pathlib import Path
from typing import Any


TRACE_ROOT = Path("/var/lib/openclaw/.openclaw/workspace/state/task_traces")


def now_ms() -> int:
    return int(time.time() * 1000)


class StagedTaskTrace:
    def __init__(self, task_name: str, category: str) -> None:
        self.task_name = task_name
        self.category = category
        self.run_id = f"{task_name}-{uuid.uuid4().hex[:10]}"
        self.path = TRACE_ROOT / category / f"{task_name}.latest.json"
        self.payload: dict[str, Any] = {
            "version": 1,
            "task": task_name,
            "category": category,
            "runId": self.run_id,
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "status": "created",
            "startedAtMs": now_ms(),
            "updatedAtMs": now_ms(),
            "currentPhase": "created",
            "steps": [],
            "artifacts": {},
            "finalMessage": "",
        }

    def start(self, phase: str) -> None:
        self.payload["status"] = "running"
        self.payload["currentPhase"] = phase
        self.payload["updatedAtMs"] = now_ms()
        self._write()

    def step(self, phase: str, status: str, detail: str = "", tool: str = "", observation: str = "") -> None:
        self.payload["currentPhase"] = phase
        self.payload["updatedAtMs"] = now_ms()
        self.payload["steps"].append(
            {
                "phase": phase,
                "status": status,
                "detail": detail,
                "tool": tool,
                "observation": observation,
                "atMs": now_ms(),
            }
        )
        self._write()

    def artifact(self, name: str, value: Any) -> None:
        self.payload.setdefault("artifacts", {})[name] = value
        self.payload["updatedAtMs"] = now_ms()
        self._write()

    def finish(self, status: str, phase: str, final_message: str = "") -> None:
        self.payload["status"] = status
        self.payload["currentPhase"] = phase
        self.payload["updatedAtMs"] = now_ms()
        self.payload["finishedAtMs"] = now_ms()
        self.payload["finalMessage"] = final_message
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
