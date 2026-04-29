#!/usr/bin/env python3
"""Control the persistent host Chrome through raw CDP with no extra deps.

This helper is intentionally generic: it does not know about any business
site. It gives the agent a stable fallback when the OpenClaw browser tool loses
track of tab ids or element refs.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import socket
import struct
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_CDP = os.environ.get("OPENCLAW_BROWSER_CDP", "http://127.0.0.1:18800")


def http_json(url: str, *, method: str = "GET") -> Any:
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


def cdp_url(path: str, base: str = DEFAULT_CDP) -> str:
    return base.rstrip("/") + path


def list_tabs(base: str = DEFAULT_CDP) -> list[dict[str, Any]]:
    return [tab for tab in http_json(cdp_url("/json/list", base)) if tab.get("type") == "page"]


def version(base: str = DEFAULT_CDP) -> dict[str, Any]:
    return http_json(cdp_url("/json/version", base))


def chrome_process_flags() -> list[str]:
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid,user,args"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    flags: list[str] = []
    for line in out.splitlines():
        if "google-chrome" not in line and "/opt/google/chrome/chrome" not in line:
            continue
        if "--remote-debugging-port=18800" not in line:
            continue
        parts = line.split()
        flags.extend(part for part in parts if part.startswith("--"))
    return sorted(set(flags))


def is_headless_like(user_agent: str, flags: list[str]) -> bool:
    lowered = " ".join([user_agent, *flags]).lower()
    return "headlesschrome" in lowered or "--headless" in lowered


def choose_tab(tabs: list[dict[str, Any]], target: str) -> dict[str, Any]:
    if not tabs:
        raise RuntimeError("no Chrome page targets are available")
    if target == "latest":
        non_blank = [tab for tab in tabs if (tab.get("url") or "") != "about:blank"]
        return (non_blank or tabs)[-1]
    for tab in tabs:
        values = [
            str(tab.get("id", "")),
            str(tab.get("tabId", "")),
            str(tab.get("title", "")),
            str(tab.get("url", "")),
        ]
        if any(target == value or target in value for value in values):
            return tab
    raise RuntimeError(f"target not found: {target}")


def new_tab(url: str, base: str = DEFAULT_CDP) -> dict[str, Any]:
    quoted = urllib.parse.quote(url, safe=":/?&=%#")
    return http_json(cdp_url(f"/json/new?{quoted}", base), method="PUT")


@dataclass
class WebSocket:
    sock: socket.socket
    next_id: int = 1

    @classmethod
    def connect(cls, ws_url: str) -> "WebSocket":
        parsed = urllib.parse.urlparse(ws_url)
        if parsed.scheme != "ws":
            raise RuntimeError(f"unsupported websocket scheme: {parsed.scheme}")
        port = parsed.port or 80
        sock = socket.create_connection((parsed.hostname or "127.0.0.1", port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        headers = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(headers.encode("ascii"))
        response = sock.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError("websocket upgrade failed")
        return cls(sock=sock)

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass

    def send_text(self, payload: str) -> None:
        data = payload.encode("utf-8")
        header = bytearray([0x81])
        if len(data) < 126:
            header.append(0x80 | len(data))
        elif len(data) < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", len(data)))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", len(data)))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(data))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv_text(self) -> str:
        b1, b2 = self._recv_exact(2)
        opcode = b1 & 0x0F
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        masked = bool(b2 & 0x80)
        mask = self._recv_exact(4) if masked else b""
        data = self._recv_exact(length)
        if masked:
            data = bytes(byte ^ mask[i % 4] for i, byte in enumerate(data))
        if opcode == 0x8:
            raise RuntimeError("websocket closed")
        if opcode == 0x9:
            return self.recv_text()
        return data.decode("utf-8", errors="replace")

    def _recv_exact(self, length: int) -> bytes:
        chunks: list[bytes] = []
        remaining = length
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise RuntimeError("websocket connection closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        msg_id = self.next_id
        self.next_id += 1
        self.send_text(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        deadline = time.time() + 15
        while time.time() < deadline:
            event = json.loads(self.recv_text())
            if event.get("id") != msg_id:
                continue
            if "error" in event:
                raise RuntimeError(json.dumps(event["error"], ensure_ascii=False))
            return event.get("result", {})
        raise RuntimeError(f"CDP call timed out: {method}")


def with_page(target: str, fn, base: str = DEFAULT_CDP):
    tab = choose_tab(list_tabs(base), target)
    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError(f"target has no websocket url: {tab.get('id')}")
    ws = WebSocket.connect(ws_url)
    try:
        return fn(ws, tab)
    finally:
        ws.close()


def evaluate(ws: WebSocket, expression: str) -> Any:
    result = ws.call(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    remote = result.get("result", {})
    if "value" in remote:
        return remote["value"]
    return remote.get("description")


def inspect_page(ws: WebSocket, tab: dict[str, Any]) -> dict[str, Any]:
    expression = r"""
(() => ({
  title: document.title,
  url: location.href,
  readyState: document.readyState,
  inputs: [...document.querySelectorAll('input, textarea, select')].slice(0, 40).map((el, i) => ({
    i,
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type') || '',
    name: el.getAttribute('name') || '',
    id: el.id || '',
    autocomplete: el.getAttribute('autocomplete') || '',
    placeholder: el.getAttribute('placeholder') || '',
    aria: el.getAttribute('aria-label') || '',
    visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
  })),
  buttons: [...document.querySelectorAll('button, [role=button], input[type=submit]')].slice(0, 40).map((el, i) => ({
    i,
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type') || '',
    text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 80),
    id: el.id || '',
    name: el.getAttribute('name') || '',
    visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
  })),
  bodyText: document.body ? document.body.innerText.slice(0, 1200) : ''
}))()
"""
    payload = evaluate(ws, expression)
    payload["targetId"] = tab.get("id")
    return payload


def element_center(ws: WebSocket, selector: str) -> dict[str, Any]:
    expression = f"""
(() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return {{ok:false, error:'selector_not_found', selector:{json.dumps(selector)}}};
  el.scrollIntoView({{block:'center', inline:'center'}});
  const r = el.getBoundingClientRect();
  return {{
    ok: true,
    selector: {json.dumps(selector)},
    x: r.left + r.width / 2,
    y: r.top + r.height / 2,
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type') || '',
    name: el.getAttribute('name') || '',
    id: el.id || '',
    text: (el.innerText || el.value || '').slice(0, 80)
  }};
}})()
"""
    info = evaluate(ws, expression)
    if not info.get("ok"):
        raise RuntimeError(json.dumps(info, ensure_ascii=False))
    return info


def click_selector(ws: WebSocket, selector: str) -> dict[str, Any]:
    info = element_center(ws, selector)
    x = float(info["x"])
    y = float(info["y"])
    ws.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    time.sleep(random.uniform(0.05, 0.15))
    ws.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    time.sleep(random.uniform(0.05, 0.18))
    ws.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    return info


def type_selector(ws: WebSocket, selector: str, text: str, clear: bool) -> dict[str, Any]:
    info = click_selector(ws, selector)
    if clear:
        ws.call("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
        ws.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
        ws.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8})
        ws.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8})
    for chunk in split_text(text):
        ws.call("Input.insertText", {"text": chunk})
        time.sleep(random.uniform(0.03, 0.12))
    return info


def split_text(text: str) -> list[str]:
    chunks: list[str] = []
    current = ""
    for char in text:
        current += char
        if len(current) >= random.randint(2, 5):
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


def wait_text(ws: WebSocket, text: str, timeout: float) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = evaluate(ws, f"document.body && document.body.innerText.includes({json.dumps(text)})")
        if found:
            return {"ok": True, "text": text}
        time.sleep(0.5)
    return {"ok": False, "text": text, "timeout": timeout}


def status_payload(base: str = DEFAULT_CDP) -> dict[str, Any]:
    data = version(base)
    flags = chrome_process_flags()
    user_agent = str(data.get("User-Agent") or data.get("userAgent") or "")
    return {
        "ok": True,
        "cdp": base,
        "browser": data.get("Browser"),
        "userAgent": user_agent,
        "webSocketDebuggerUrl": data.get("webSocketDebuggerUrl"),
        "flags": flags,
        "headlessLike": is_headless_like(user_agent, flags),
        "usesXvfb": bool(os.environ.get("DISPLAY")) or any("Xvfb" in line for line in subprocess.getoutput("ps -eo args").splitlines()),
        "tabs": [
            {"id": tab.get("id"), "title": tab.get("title"), "url": tab.get("url")}
            for tab in list_tabs(base)
        ],
    }


def print_json(payload: Any) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Human-style CDP control for the persistent host Chrome.")
    parser.add_argument("--cdp", default=DEFAULT_CDP)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    p_open = sub.add_parser("open")
    p_open.add_argument("url")

    p_inspect = sub.add_parser("inspect")
    p_inspect.add_argument("--target", default="latest")

    p_click = sub.add_parser("click")
    p_click.add_argument("--target", default="latest")
    p_click.add_argument("--selector", required=True)

    p_type = sub.add_parser("type")
    p_type.add_argument("--target", default="latest")
    p_type.add_argument("--selector", required=True)
    p_type.add_argument("--text")
    p_type.add_argument("--text-env")
    p_type.add_argument("--clear", action="store_true")

    p_wait = sub.add_parser("wait-text")
    p_wait.add_argument("--target", default="latest")
    p_wait.add_argument("--text", required=True)
    p_wait.add_argument("--timeout", type=float, default=10.0)

    args = parser.parse_args()
    if args.command == "status":
        return print_json(status_payload(args.cdp))
    if args.command == "open":
        tab = new_tab(args.url, args.cdp)
        return print_json({"ok": True, "tab": tab})
    if args.command == "inspect":
        return print_json(with_page(args.target, inspect_page, args.cdp))
    if args.command == "click":
        return print_json(with_page(args.target, lambda ws, tab: {"ok": True, "clicked": click_selector(ws, args.selector), "targetId": tab.get("id")}, args.cdp))
    if args.command == "type":
        text = args.text if args.text is not None else os.environ.get(args.text_env or "", "")
        return print_json(with_page(args.target, lambda ws, tab: {"ok": True, "typed": type_selector(ws, args.selector, text, args.clear), "targetId": tab.get("id")}, args.cdp))
    if args.command == "wait-text":
        return print_json(with_page(args.target, lambda ws, tab: {"targetId": tab.get("id"), **wait_text(ws, args.text, args.timeout)}, args.cdp))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
