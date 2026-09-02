from __future__ import annotations

from unittest.mock import patch

import model_fallback_client as client


def test_default_primary_model_is_gpt_5_6_sol() -> None:
    assert client.DEFAULT_PRIMARY_MODEL == "gpt-5.6-sol"


def test_chat_with_fallback_uses_primary_when_available() -> None:
    primary = client.ChatEndpoint("openai_compatible", "http://primary/v1", "gpt-5.5", "key")
    fallback = client.ChatEndpoint("openai_compatible", "http://fallback.example/v1", "fallback-model", "fallback-key")
    with patch.object(client, "_openai_compatible_chat", return_value="primary ok") as primary_chat, patch.object(
        client, "_ollama_chat", return_value="fallback ok"
    ) as fallback_chat:
        content, meta = client.chat_with_fallback(
            [{"role": "user", "content": "hi"}],
            primary=primary,
            fallback=fallback,
        )
    assert content == "primary ok"
    assert meta["model"] == "gpt-5.5"
    assert meta["fallback_used"] is False
    primary_chat.assert_called_once()
    fallback_chat.assert_not_called()


def test_chat_with_fallback_uses_explicit_fallback_when_primary_fails() -> None:
    primary = client.ChatEndpoint("openai_compatible", "http://primary/v1", "gpt-5.5", "key")
    fallback = client.ChatEndpoint("openai_compatible", "http://fallback.example/v1", "safe-fallback", "fallback-key")
    with patch.object(client, "_openai_compatible_chat", side_effect=[RuntimeError("primary down"), "fallback ok"]), patch.object(
        client, "_ollama_chat"
    ) as fallback_chat:
        content, meta = client.chat_with_fallback(
            [{"role": "user", "content": "hi"}],
            primary=primary,
            fallback=fallback,
        )
    assert content == "fallback ok"
    assert meta["provider"] == "openai_compatible"
    assert meta["model"] == "safe-fallback"
    assert meta["fallback_used"] is True
    assert "primary down" in meta["primary_error"]
    fallback_chat.assert_not_called()


def test_default_fallback_endpoint_is_not_configured(monkeypatch) -> None:
    for key in (
        "OPENCLAW_MODEL_FALLBACK_BASE_URL",
        "OPENCLAW_MODEL_FALLBACK",
    ):
        monkeypatch.delenv(key, raising=False)
    endpoint = client.resolve_fallback_chat_endpoint()
    assert endpoint is None


def test_primary_failure_raises_when_no_fallback_is_configured(monkeypatch) -> None:
    primary = client.ChatEndpoint("openai_compatible", "http://primary/v1", "gpt-5.5", "key")
    for key in ("OPENCLAW_MODEL_FALLBACK_BASE_URL", "OPENCLAW_MODEL_FALLBACK"):
        monkeypatch.delenv(key, raising=False)
    with patch.object(client, "_openai_compatible_chat", side_effect=RuntimeError("primary down")):
        try:
            client.chat_with_fallback([{"role": "user", "content": "hi"}], primary=primary)
        except RuntimeError as exc:
            assert "primary down" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")


def test_explicit_fallback_endpoint_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_MODEL_FALLBACK_PROVIDER", "openai_compatible")
    monkeypatch.setenv("OPENCLAW_MODEL_FALLBACK_BASE_URL", "http://fallback.example")
    monkeypatch.setenv("OPENCLAW_MODEL_FALLBACK", "fallback-model")
    endpoint = client.resolve_fallback_chat_endpoint()
    assert endpoint is not None
    assert endpoint.provider == "openai_compatible"
    assert endpoint.base_url == "http://fallback.example"
    assert endpoint.model == "fallback-model"


def test_primary_secret_uses_systemd_credential(monkeypatch, tmp_path) -> None:
    payload = tmp_path / "openclaw-secrets.json"
    payload.write_text('{"providers":{"openaiCodex":{"apiKey":"test-key"}}}', encoding="utf-8")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    for key in ("NEWS_CODEX_API_KEY", "NEWS_CODEX_API_KEY_FILE"):
        monkeypatch.delenv(key, raising=False)
    assert client.read_secret_env("NEWS_CODEX_API_KEY") == "test-key"
