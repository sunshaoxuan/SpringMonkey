#!/usr/bin/env python3
"""Expose local Codex Local Access to ccnode through an SSH reverse tunnel."""
from __future__ import annotations

import os
import select
import socket
import sys
import threading
import time
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint


SSH_HOST = os.environ.get("OPENCLAW_SSH_HOST", "ccnode.briconbric.com")
SSH_PORT = int(os.environ.get("OPENCLAW_SSH_PORT", "8822"))
SSH_USER = os.environ.get("OPENCLAW_SSH_USER", "root")
REMOTE_BIND = os.environ.get("CODEX_TUNNEL_REMOTE_BIND", "0.0.0.0")
REMOTE_PORT = int(os.environ.get("CODEX_TUNNEL_REMOTE_PORT", "49530"))
LOCAL_HOST = os.environ.get("CODEX_TUNNEL_LOCAL_HOST", "127.0.0.1")
LOCAL_PORT = int(os.environ.get("CODEX_TUNNEL_LOCAL_PORT", "59451"))


def pipe_sockets(left, right) -> None:
    try:
        sockets = [left, right]
        while True:
            readable, _, _ = select.select(sockets, [], [], 30)
            if not readable:
                continue
            for src in readable:
                data = src.recv(65536)
                if not data:
                    return
                dst = right if src is left else left
                dst.sendall(data)
    finally:
        try:
            left.close()
        except Exception:
            pass
        try:
            right.close()
        except Exception:
            pass


def serve_forever() -> int:
    try:
        import paramiko
    except ImportError:
        print("paramiko is required. Install scripts/requirements-ssh.txt.", file=sys.stderr)
        return 1
    password = load_openclaw_ssh_password()
    if not password:
        print(missing_password_hint(), file=sys.stderr)
        return 1

    while True:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                SSH_HOST,
                port=SSH_PORT,
                username=SSH_USER,
                password=password,
                timeout=60,
                allow_agent=False,
                look_for_keys=False,
            )
            transport = client.get_transport()
            if transport is None:
                raise RuntimeError("missing SSH transport")
            transport.request_port_forward(REMOTE_BIND, REMOTE_PORT)
            print(
                f"CODEX_REVERSE_TUNNEL_READY remote={REMOTE_BIND}:{REMOTE_PORT} local={LOCAL_HOST}:{LOCAL_PORT}",
                flush=True,
            )
            while transport.is_active():
                channel = transport.accept(30)
                if channel is None:
                    continue
                try:
                    local = socket.create_connection((LOCAL_HOST, LOCAL_PORT), timeout=10)
                except Exception as exc:
                    print(f"LOCAL_CONNECT_FAIL {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                    channel.close()
                    continue
                thread = threading.Thread(target=pipe_sockets, args=(channel, local), daemon=True)
                thread.start()
        except Exception as exc:
            print(f"TUNNEL_RECONNECT {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            time.sleep(5)
        finally:
            try:
                client.close()
            except Exception:
                pass


def main() -> int:
    return serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
