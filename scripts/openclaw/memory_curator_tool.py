#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path("/var/lib/openclaw/.openclaw/memory/lancedb-qwen3-embedding-8b-4096")
DEFAULT_AUDIT_LOG = Path("/var/lib/openclaw/.openclaw/workspace/var/memory_curator_audit.jsonl")
NOISE_RE = re.compile(
    r"(encrypted_content|iVBORw0KGgo|base64|gAAAAA|\.png\s|root root \d+|url\.parse\(\)|DEP0169|System \(untrusted\))",
    re.IGNORECASE,
)
XHS_RE = re.compile(r"(XHS|小红书|小紅書|Costco|Frutteto|コストコ|フルッテート|投稿)", re.IGNORECASE)
HIGH_VALUE_XHS_RE = re.compile(r"(Costco|Frutteto|无水印|無水印|投稿流程|话题|話題|规则|規則|发布|發布|小红书文档|小紅書文檔)", re.IGNORECASE)


@dataclass
class MemoryEntry:
    id: str
    text: str
    category: str
    importance: float
    createdAt: int


@dataclass
class CuratedMemory:
    id: str
    reason: str
    text_preview: str
    score: int


def node_lancedb(payload: dict[str, Any]) -> dict[str, Any]:
    script = r"""
const fs = require("node:fs");
const lancedb = require("@lancedb/lancedb");
async function main() {
  const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  const db = await lancedb.connect(payload.dbPath);
  const names = await db.tableNames();
  if (!names.includes("memories")) {
    console.log(JSON.stringify({ entries: [], deleted: [] }));
    return;
  }
  const table = await db.openTable("memories");
  if (payload.action === "list") {
    const rows = await table.query().select(["id", "text", "category", "importance", "createdAt"]).toArray();
    console.log(JSON.stringify({ entries: rows }));
    return;
  }
  if (payload.action === "delete") {
    const deleted = [];
    for (const id of payload.ids || []) {
      if (!/^[0-9a-f-]{36}$/i.test(id)) continue;
      await table.delete(`id = '${id}'`);
      deleted.push(id);
    }
    console.log(JSON.stringify({ deleted }));
    return;
  }
  throw new Error("unsupported action");
}
main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
"""
    with tempfile.TemporaryDirectory(prefix="memory_curator_") as tmp:
        tmp_path = Path(tmp)
        script_path = tmp_path / "curator.js"
        payload_path = tmp_path / "payload.json"
        script_path.write_text(script, encoding="utf-8")
        payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        env = dict(os.environ)
        node_path = env.get("NODE_PATH", "")
        plugin_node_modules = "/var/lib/openclaw/.openclaw/npm/node_modules"
        env["NODE_PATH"] = plugin_node_modules if not node_path else plugin_node_modules + os.pathsep + node_path
        proc = subprocess.run(
            ["node", str(script_path), str(payload_path)],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            env=env,
        )
    return json.loads(proc.stdout or "{}")


def list_memories(db_path: Path) -> list[MemoryEntry]:
    data = node_lancedb({"action": "list", "dbPath": str(db_path)})
    entries: list[MemoryEntry] = []
    for row in data.get("entries", []):
        entries.append(
            MemoryEntry(
                id=str(row.get("id") or ""),
                text=str(row.get("text") or ""),
                category=str(row.get("category") or "other"),
                importance=float(row.get("importance") or 0),
                createdAt=int(row.get("createdAt") or 0),
            )
        )
    return entries


def noise_score(text: str) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0
    if NOISE_RE.search(text):
        score += 3
        reasons.append("contains encrypted/base64/path-log noise")
    if len(text) > 1200:
        score += 1
        reasons.append("too long for durable fact memory")
    if text.count("/") > 10:
        score += 1
        reasons.append("path-heavy log line")
    if text.count("{") > 3 and text.count("}") > 3:
        score += 1
        reasons.append("raw json/log fragment")
    if HIGH_VALUE_XHS_RE.search(text) and not re.search(r"(encrypted_content|iVBORw0KGgo|base64|gAAAAA)", text, re.IGNORECASE):
        score = max(0, score - 2)
        reasons.append("contains high-value XHS content; downgraded")
    return score, reasons


def curate(entries: list[MemoryEntry], topic: str) -> list[CuratedMemory]:
    marked: list[CuratedMemory] = []
    for entry in entries:
        if topic == "xhs" and not XHS_RE.search(entry.text):
            continue
        score, reasons = noise_score(entry.text)
        if score >= 3:
            marked.append(
                CuratedMemory(
                    id=entry.id,
                    reason="; ".join(reasons),
                    text_preview=entry.text[:260],
                    score=score,
                )
            )
    marked.sort(key=lambda item: item.score, reverse=True)
    return marked


def delete_marked(db_path: Path, ids: list[str]) -> list[str]:
    data = node_lancedb({"action": "delete", "dbPath": str(db_path), "ids": ids})
    return [str(item) for item in data.get("deleted", [])]


def write_audit(topic: str, marked: list[CuratedMemory], deleted: list[str], path: Path = DEFAULT_AUDIT_LOG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "candidate_count": len(marked),
        "deleted_count": len(deleted),
        "deleted": deleted,
        "candidates": [asdict(item) for item in marked],
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def format_report(topic: str, marked: list[CuratedMemory], deleted: list[str]) -> str:
    lines = [
        "长记忆质量检查",
        f"主题：{topic}",
        f"噪声候选：{len(marked)}",
        f"已删除：{len(deleted)}",
    ]
    for index, item in enumerate(marked[:10], start=1):
        lines.append(f"{index}. score={item.score} id={item.id} reason={item.reason} text={item.text_preview}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect and optionally delete noisy long-term memory rows.")
    parser.add_argument("--topic", default="xhs", choices=["xhs"])
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--forget-marked", action="store_true")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--audit-log", type=Path, default=DEFAULT_AUDIT_LOG)
    args = parser.parse_args()
    entries = list_memories(args.db_path)
    marked = curate(entries, args.topic)[: max(0, args.limit)]
    deleted: list[str] = []
    if args.forget_marked:
        deleted = delete_marked(args.db_path, [item.id for item in marked])
        write_audit(args.topic, marked, deleted, args.audit_log)
    payload = {
        "status": "ok",
        "topic": args.topic,
        "candidate_count": len(marked),
        "deleted_count": len(deleted),
        "deleted": deleted,
        "audit_log": str(args.audit_log) if args.forget_marked else "",
        "candidates": [asdict(item) for item in marked],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_report(args.topic, marked, deleted))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
