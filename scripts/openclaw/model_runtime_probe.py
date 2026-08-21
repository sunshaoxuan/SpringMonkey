#!/usr/bin/env python3
from __future__ import annotations

import json
from typing import Any, Callable

from model_fallback_client import chat_with_fallback


ModelCaller = Callable[..., tuple[str, dict[str, Any]]]


def probe_text_runtime(model_caller: ModelCaller = chat_with_fallback) -> dict[str, Any]:
    try:
        content, meta = model_caller(
            [{"role": "user", "content": "Runtime health probe. Reply with OK only."}],
            timeout=25,
            temperature=0,
        )
    except Exception as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "status": "ok" if bool((content or "").strip()) else "failed",
        "provider": str(meta.get("provider") or ""),
        "model": str(meta.get("model") or ""),
        "fallback_used": bool(meta.get("fallback_used")),
        "latency_ms": int(meta.get("latency_ms") or 0),
        "primary_error": str(meta.get("primary_error") or "")[-1000:],
    }


def main() -> int:
    report = probe_text_runtime()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
