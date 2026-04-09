"""
从环境变量或本机文件读取 OpenClaw 宿主机 SSH 密码（不入 Git）。

优先级：
1. OPENCLAW_SSH_PASSWORD 或 SSH_ROOT_PASSWORD
2. OPENCLAW_SSH_PASSWORD_FILE 指向的文件（单行密码）
3. 若存在则读取（均在 SpringMonkey 下，且被 .gitignore 忽略）：
   - secrets/openclaw_ssh_password.txt
   - private/openclaw_ssh_password.txt

说明：被 gitignore 的路径在 IDE 里可能不可索引，AI 未必能「自动发现」；
      但脚本运行时只要文件在磁盘上即可读取。
"""
from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_first_line(p: Path) -> str | None:
    if not p.is_file():
        return None
    raw = p.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return None
    line = raw.splitlines()[0].strip()
    return line or None


def load_openclaw_ssh_password() -> str | None:
    pw = (os.environ.get("OPENCLAW_SSH_PASSWORD") or os.environ.get("SSH_ROOT_PASSWORD") or "").strip()
    if pw:
        return pw

    path = (os.environ.get("OPENCLAW_SSH_PASSWORD_FILE") or "").strip()
    if path:
        p = Path(path).expanduser()
        got = _read_first_line(p)
        if got:
            return got

    root = _repo_root()
    for rel in ("secrets/openclaw_ssh_password.txt", "private/openclaw_ssh_password.txt"):
        got = _read_first_line(root / rel)
        if got:
            return got

    return None


def missing_password_hint() -> str:
    return (
        "未找到 SSH 密码：请设置 OPENCLAW_SSH_PASSWORD / SSH_ROOT_PASSWORD，"
        "或设置 OPENCLAW_SSH_PASSWORD_FILE，"
        "或在 SpringMonkey/secrets/openclaw_ssh_password.txt（或 private/ 下同文件名）"
        "写入单行密码（该目录已在 .gitignore，勿提交）。"
    )
