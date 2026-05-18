#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import os
import uuid
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_PATH = Path("/var/lib/openclaw/.openclaw/openclaw.json")


@dataclass(frozen=True)
class MediaReply:
    media_path: Path
    caption: str


def discord_token(config_path: Path = DEFAULT_CONFIG_PATH) -> str:
    token = os.environ.get("OPENCLAW_DISCORD_TOKEN", "").strip()
    if token:
        return token
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    discord = (data.get("channels") or {}).get("discord") if isinstance(data.get("channels"), dict) else {}
    return str((discord or {}).get("token") or "")


def parse_media_reply(content: str) -> MediaReply | None:
    lines = (content or "").splitlines()
    if not lines:
        return None
    first = lines[0].strip()
    if not first.startswith("MEDIA:"):
        return None
    path = Path(first.split(":", 1)[1].strip())
    if not path.is_file():
        return None
    caption = "\n".join(line for line in lines[1:] if line.strip()).strip()
    return MediaReply(path, caption)


def _multipart_body(*, payload: dict, file_path: Path, boundary: str) -> bytes:
    mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    filename = file_path.name
    parts: list[bytes] = []
    parts.append(
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="payload_json"\r\n'
            "Content-Type: application/json\r\n\r\n"
            f"{json.dumps(payload, ensure_ascii=False)}\r\n"
        ).encode("utf-8")
    )
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(file_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts)


def send_discord_text(token: str, channel_id: str, content: str) -> int:
    chunks: list[str] = []
    text = content or ""
    while text:
        chunks.append(text[:1900])
        text = text[1900:]
    if not chunks:
        chunks = [""]
    for index, chunk in enumerate(chunks, 1):
        if len(chunks) > 1:
            chunk = f"[{index}/{len(chunks)}]\n{chunk}"
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            data=json.dumps({"content": chunk, "allowed_mentions": {"parse": []}}).encode("utf-8"),
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
                "User-Agent": "DiscordBot (openclaw-media-delivery, 1.0)",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    return len(chunks)


def send_discord_media(token: str, channel_id: str, media: MediaReply) -> int:
    boundary = f"----openclaw{uuid.uuid4().hex}"
    payload = {
        "content": media.caption[:1900],
        "allowed_mentions": {"parse": []},
        "attachments": [{"id": 0, "filename": media.media_path.name}],
    }
    body = _multipart_body(payload=payload, file_path=media.media_path, boundary=boundary)
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        data=body,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "DiscordBot (openclaw-media-delivery, 1.0)",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()
    return 1


def send_discord_message(channel_id: str, content: str, *, config_path: Path = DEFAULT_CONFIG_PATH) -> tuple[int, str]:
    token = discord_token(config_path)
    if not token:
        raise RuntimeError("missing channels.discord.token")
    media = parse_media_reply(content)
    if media:
        return send_discord_media(token, channel_id, media), f"media:{media.media_path}"
    return send_discord_text(token, channel_id, content), "text"
