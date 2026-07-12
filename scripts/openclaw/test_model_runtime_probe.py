from model_runtime_probe import probe_text_runtime


def test_primary_model_probe_success() -> None:
    report = probe_text_runtime(
        lambda *_args, **_kwargs: ("OK", {"provider": "openai", "model": "gpt", "fallback_used": False, "latency_ms": 12})
    )
    assert report == {
        "status": "ok",
        "provider": "openai",
        "model": "gpt",
        "fallback_used": False,
        "latency_ms": 12,
        "primary_error": "",
    }


def test_fallback_model_probe_success() -> None:
    report = probe_text_runtime(
        lambda *_args, **_kwargs: (
            "OK",
            {"provider": "ollama", "model": "qwen", "fallback_used": True, "latency_ms": 8, "primary_error": "primary unavailable"},
        )
    )
    assert report["status"] == "ok"
    assert report["fallback_used"] is True
    assert report["primary_error"] == "primary unavailable"


def test_model_probe_failure_is_structured() -> None:
    def fail(*_args, **_kwargs):
        raise RuntimeError("all providers unavailable")

    report = probe_text_runtime(fail)
    assert report["status"] == "failed"
    assert "all providers unavailable" in report["error"]
