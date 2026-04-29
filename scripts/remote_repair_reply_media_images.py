#!/usr/bin/env python3
"""Repair OpenClaw outbound image media processing on the host."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint

HOST = os.environ.get("OPENCLAW_SSH_HOST", "ccnode.briconbric.com")
PORT = int(os.environ.get("OPENCLAW_SSH_PORT", "8822"))
USER = "root"

REMOTE = r"""
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

CHECK_ONLY="__CHECK_ONLY__"
OPENCLAW_DIR="${OPENCLAW_NODE_DIR:-/usr/lib/node_modules/openclaw}"
DIST_DIR="$OPENCLAW_DIR/dist"
TEST_PNG="/tmp/openclaw-reply-media-test.png"

if [ ! -d "$OPENCLAW_DIR" ]; then
  echo "missing OpenClaw node dir: $OPENCLAW_DIR" >&2
  exit 1
fi
if [ ! -d "$DIST_DIR" ]; then
  echo "missing OpenClaw dist dir: $DIST_DIR" >&2
  exit 1
fi

python3 <<'PY'
import base64
from pathlib import Path

png = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAFgwJ/lQn5WQAAAABJRU5ErkJggg=="
)
Path("/tmp/openclaw-reply-media-test.png").write_bytes(base64.b64decode(png))
PY

validate_image_ops() {
  OPENCLAW_DIST="$DIST_DIR" OPENCLAW_TEST_PNG="$TEST_PNG" node --input-type=module <<'NODE'
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const dist = process.env.OPENCLAW_DIST;
const testPng = process.env.OPENCLAW_TEST_PNG;
const files = await fs.readdir(dist);
const imageOpsName = files.find((name) => /^image-ops-.*\.js$/.test(name));
if (!imageOpsName) throw new Error(`image-ops bundle not found in ${dist}`);

const imageOpsPath = path.join(dist, imageOpsName);
const source = await fs.readFile(imageOpsPath, "utf8");
const alias = source.match(/resizeToJpeg\s+as\s+([A-Za-z_$][\w$]*)/)?.[1] || "resizeToJpeg";
const imageOps = await import(pathToFileURL(imageOpsPath).href);
const resizeToJpeg = imageOps[alias];
if (typeof resizeToJpeg !== "function") {
  throw new Error(`resizeToJpeg export not found in ${imageOpsName}; alias=${alias}`);
}

const buffer = await fs.readFile(testPng);
const jpeg = await resizeToJpeg({
  buffer,
  maxSide: 800,
  quality: 80,
  withoutEnlargement: true,
});
if (!Buffer.isBuffer(jpeg) || jpeg.length < 10 || jpeg[0] !== 0xff || jpeg[1] !== 0xd8) {
  throw new Error("resizeToJpeg did not return a valid JPEG buffer");
}
console.log(JSON.stringify({ ok: true, imageOps: imageOpsName, alias, jpegBytes: jpeg.length }));
NODE
}

echo "=== validating OpenClaw image media processing ==="
if validate_image_ops; then
  echo "IMAGE_MEDIA_READY"
  echo DONE
  exit 0
fi

if [ "$CHECK_ONLY" = "1" ]; then
  echo "image media validation failed in check-only mode" >&2
  exit 1
fi

echo "=== installing sharp optional dependency ==="
npm install --prefix "$OPENCLAW_DIR" sharp

echo "=== validating after repair ==="
validate_image_ops

echo "=== restarting OpenClaw ==="
systemctl daemon-reload
systemctl restart openclaw.service
sleep 8
systemctl is-active openclaw.service

echo DONE
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair OpenClaw screenshot/reply image sending.")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only validate image media processing; do not install dependencies or restart OpenClaw.",
    )
    args = parser.parse_args()

    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print(
            "缺少 paramiko。请执行一次：\n"
            "  python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt",
            file=sys.stderr,
        )
        return 1

    remote = REMOTE.replace("__CHECK_ONLY__", "1" if args.check_only else "0")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=pw, timeout=60, allow_agent=False, look_for_keys=False)
    _, so, se = c.exec_command(remote.strip(), get_pty=True)
    out = so.read().decode("utf-8", errors="replace")
    err = se.read().decode("utf-8", errors="replace")
    c.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    if out and not out.endswith("\n"):
        sys.stdout.buffer.write(b"\n")
    if err.strip():
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
        if err and not err.endswith("\n"):
            sys.stderr.buffer.write(b"\n")
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
