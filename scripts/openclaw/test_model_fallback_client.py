from __future__ import annotations

from unittest.mock import patch

import model_fallback_client as client


def test_default_primary_model_is_gpt_5_6_sol() -> None:
    assert client.DEFAULT_PRIMARY_MODEL == "gpt-5.6-sol"


def test_chat_with_fallback_uses_primary_when_available() -> None:
    primary = client.ChatEndpoint("openai_compatible", "http://primary/v1", "gpt-5.5", "key")
    fallback = client.ChatEndpoint("ollama", "http://ccnode.briconbric.com:22545", "qwen3:14b")
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


def test_chat_with_fallback_uses_qwen_14b_when_primary_fails() -> None:
    primary = client.ChatEndpoint("openai_compatible", "http://primary/v1", "gpt-5.5", "key")
    fallback = client.ChatEndpoint("ollama", "http://ccnode.briconbric.com:22545", "qwen3:14b")
    with patch.object(client, "_openai_compatible_chat", side_effect=RuntimeError("primary down")), patch.object(
        client, "_ollama_chat", return_value="fallback ok"
    ) as fallback_chat:
        content, meta = client.chat_with_fallback(
            [{"role": "user", "content": "hi"}],
            primary=primary,
            fallback=fallback,
        )
    assert content == "fallback ok"
    assert meta["provider"] == "ollama"
    assert meta["model"] == "qwen3:14b"
    assert meta["fallback_used"] is True
    assert "primary down" in meta["primary_error"]
    fallback_chat.assert_called_once()


def test_default_fallback_endpoint_is_ccnode_qwen_14b(monkeypatch) -> None:
    for key in (
        "OPENCLAW_MODEL_FALLBACK_BASE_URL",
        "OPENCLAW_QWEN_FALLBACK_BASE_URL",
        "OLLAMA_BASE_URL",
        "OPENCLAW_MODEL_FALLBACK",
        "OPENCLAW_QWEN_FALLBACK_MODEL",
        "NEWS_FALLBACK_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    endpoint = client.resolve_fallback_chat_endpoint()
    assert endpoint.provider == "ollama"
    assert endpoint.base_url == "http://ccnode.briconbric.com:22545"
    assert endpoint.model == "qwen3:14b"
