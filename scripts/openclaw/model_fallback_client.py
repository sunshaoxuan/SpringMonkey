#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUNTIME_ENV_FILES = (
    Path("/etc/openclaw/openclaw.env"),
    Path("/var/lib/openclaw/.openclaw/openclaw.env"),
)
DEFAULT_PRIMARY_MODEL = "gpt-5.6"
DEFAULT_FALLBACK_BASE_URL = "http://ccnode.briconbric.com:22545"
DEFAULT_FALLBACK_MODEL = "qwen3:14b"


@dataclass(frozen=True)
class ChatEndpoint:
    provider: str
    base_url: str
    model: str
    api_key: str = ""


def load_runtime_env_files(paths: tuple[Path, ...] = RUNTIME_ENV_FILES) -> None:
    for path in paths:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            key, value = line.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")


def read_secret_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
        file_value = os.environ.get(f"{name}_FILE", "").strip()
        if file_value:
            try:
                secret = Path(file_value).read_text(encoding="utf-8").strip()
            except OSError:
                secret = ""
            if secret:
                return secret
    return ""


def _strip_provider(model: str) -> str:
    value = (model or "").strip()
    for prefix in ("openai-codex/", "openai/", "ollama/"):
        if value.lower().startswith(prefix):
            return value.split("/", 1)[1].strip() or value
    return value


def _http_post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc
    return json.loads(raw)


def resolve_primary_chat_endpoint() -> ChatEndpoint:
    load_runtime_env_files()
    base_url = (
        os.environ.get("OPENCLAW_INTENT_MODEL_BASE_URL", "").strip()
        or os.environ.get("OPENCLAW_PUBLIC_MODEL_BASE_URL", "").strip()
        or os.environ.get("NEWS_CODEX_BASE_URL", "").strip()
    ).rstrip("/")
    model = (
        os.environ.get("OPENCLAW_INTENT_MODEL", "").strip()
        or os.environ.get("OPENCLAW_PUBLIC_MODEL", "").strip()
        or os.environ.get("NEWS_CODEX_MODEL", "").strip()
        or DEFAULT_PRIMARY_MODEL
    )
    api_key = read_secret_env(
        "OPENCLAW_INTENT_MODEL_API_KEY",
        "OPENCLAW_PUBLIC_MODEL_API_KEY",
        "NEWS_CODEX_API_KEY",
        "OPENCLAW_CODEX_API_KEY",
        "CODEX_API_KEY",
    )
    if not base_url:
        raise RuntimeError("missing OPENCLAW_INTENT_MODEL_BASE_URL/OPENCLAW_PUBLIC_MODEL_BASE_URL")
    return ChatEndpoint("openai_compatible", base_url, _strip_provider(model), api_key)


def resolve_fallback_chat_endpoint() -> ChatEndpoint:
    load_runtime_env_files()
    base_url = (
        os.environ.get("OPENCLAW_MODEL_FALLBACK_BASE_URL", "").strip()
        or os.environ.get("OPENCLAW_QWEN_FALLBACK_BASE_URL", "").strip()
        or os.environ.get("OLLAMA_BASE_URL", "").strip()
        or DEFAULT_FALLBACK_BASE_URL
    ).rstrip("/")
    model = (
        os.environ.get("OPENCLAW_MODEL_FALLBACK", "").strip()
        or os.environ.get("OPENCLAW_QWEN_FALLBACK_MODEL", "").strip()
        or os.environ.get("NEWS_FALLBACK_MODEL", "").strip()
        or DEFAULT_FALLBACK_MODEL
    )
    return ChatEndpoint("ollama", base_url, _strip_provider(model))


def _openai_compatible_chat(endpoint: ChatEndpoint, messages: list[dict[str, str]], timeout: int, temperature: float) -> str:
    payload = {"model": endpoint.model, "messages": messages, "temperature": temperature}
    headers = {"Content-Type": "application/json"}
    if endpoint.api_key:
        headers["Authorization"] = f"Bearer {endpoint.api_key}"
    data = _http_post_json(endpoint.base_url.rstrip("/") + "/chat/completions", payload, headers, timeout)
    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"unexpected OpenAI-compatible response: {data!r}") from exc


def _ollama_chat(endpoint: ChatEndpoint, messages: list[dict[str, str]], timeout: int) -> str:
    data = _http_post_json(
        endpoint.base_url.rstrip("/") + "/api/chat",
        {"model": endpoint.model, "messages": messages, "stream": False},
        {"Content-Type": "application/json"},
        timeout,
    )
    try:
        return str(data["message"]["content"]).strip()
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"unexpected Ollama response: {data!r}") from exc


def chat_with_fallback(
    messages: list[dict[str, str]],
    *,
    timeout: int = 30,
    temperature: float = 0,
    primary: ChatEndpoint | None = None,
    fallback: ChatEndpoint | None = None,
    allow_fallback: bool = True,
) -> tuple[str, dict[str, Any]]:
    primary = primary or resolve_primary_chat_endpoint()
    fallback = fallback or resolve_fallback_chat_endpoint()
    errors: list[str] = []
    started = time.monotonic()
    try:
        content = _openai_compatible_chat(primary, messages, timeout, temperature)
        return content, {
            "model": primary.model,
            "provider": primary.provider,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "fallback_used": False,
        }
    except Exception as exc:
        errors.append(f"primary {primary.model}@{primary.base_url}: {type(exc).__name__}: {exc}")
        if not allow_fallback:
            raise
    fallback_started = time.monotonic()
    content = _ollama_chat(fallback, messages, timeout)
    return content, {
        "model": fallback.model,
        "provider": fallback.provider,
        "latency_ms": int((time.monotonic() - fallback_started) * 1000),
        "fallback_used": True,
        "primary_error": errors[-1] if errors else "",
    }
