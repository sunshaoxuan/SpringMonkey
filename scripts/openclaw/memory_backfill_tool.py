#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OPENCLAW_HOME = Path("/var/lib/openclaw/.openclaw")
DEFAULT_DB_PATH = DEFAULT_OPENCLAW_HOME / "memory" / "lancedb"
DEFAULT_SESSIONS_DIR = DEFAULT_OPENCLAW_HOME / "agents" / "main" / "sessions"
DEFAULT_BACKFILL_LOG = DEFAULT_OPENCLAW_HOME / "workspace" / "var" / "memory_backfill_records.jsonl"
DEFAULT_OLLAMA_BASE_URL = "http://ccnode.briconbric.com:22545"
DEFAULT_EMBED_MODEL = "bge-m3:latest"
DEFAULT_DIMENSIONS = 1024

TOPIC_PATTERNS = {
    "xhs": re.compile(r"(小红书|小紅書|XHS|xhs|Costco|Frutteto|投稿|话题|話題|笔记|筆記)", re.IGNORECASE),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MemoryCandidate:
    topic: str
    source: str
    text: str
    category: str = "fact"
    importance: float = 0.72


def parse_since(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    try:
        if len(raw) == 10:
            return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        raise SystemExit(f"invalid --since value: {value}")


def file_mtime_after(path: Path, since: datetime | None) -> bool:
    if since is None:
        return True
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) >= since


def extract_strings(value: Any, out: list[str]) -> None:
    if isinstance(value, str):
        if value.strip():
            out.append(value.strip())
    elif isinstance(value, dict):
        for item in value.values():
            extract_strings(item, out)
    elif isinstance(value, list):
        for item in value:
            extract_strings(item, out)


def read_textish_json(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    snippets: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        extract_strings(data, snippets)
    if snippets:
        return "\n".join(snippets)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    snippets = []
    extract_strings(data, snippets)
    return "\n".join(snippets)


def concise_topic_summary(topic: str, source: str, text: str) -> str | None:
    pattern = TOPIC_PATTERNS.get(topic)
    if not pattern or not pattern.search(text):
        return None
    lines = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or len(line) < 8:
            continue
        if not pattern.search(line):
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line[:260])
        if len(lines) >= 6:
            break
    if not lines:
        return None
    body = "；".join(lines)
    return f"{topic.upper()} 长记忆回填：来源 {source}。要点：{body}"


def collect_candidates(topic: str, sessions_dir: Path, since: datetime | None) -> list[MemoryCandidate]:
    candidates: list[MemoryCandidate] = []
    if not sessions_dir.is_dir():
        return candidates
    files = sorted(
        [path for path in sessions_dir.rglob("*") if path.is_file() and file_mtime_after(path, since)],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in files[:400]:
        text = read_textish_json(path)
        summary = concise_topic_summary(topic, path.name, text)
        if summary:
            candidates.append(MemoryCandidate(topic=topic, source=str(path), text=summary))
        if len(candidates) >= 25:
            break
    return dedupe_candidates(candidates)


def dedupe_candidates(candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
    out: list[MemoryCandidate] = []
    seen: set[str] = set()
    for item in candidates:
        key = re.sub(r"\W+", "", item.text.lower())[:220]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def embed_text(text: str, base_url: str, model: str, dimensions: int) -> list[float]:
    payload = json.dumps({"model": model, "input": text}).encode("utf-8")
    req = urllib.request.Request(base_url.rstrip("/") + "/api/embed", data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    embeddings = data.get("embeddings")
    if not embeddings:
        vector = data.get("embedding")
    else:
        vector = embeddings[0]
    if not isinstance(vector, list) or len(vector) != dimensions:
        raise RuntimeError(f"unexpected embedding dimensions: {0 if not isinstance(vector, list) else len(vector)}")
    return [float(item) for item in vector]


def node_insert_lancedb(db_path: Path, rows: list[dict[str, Any]]) -> None:
    script = r"""
const fs = require("node:fs");
const lancedb = require("@lancedb/lancedb");
async function main() {
  const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  const db = await lancedb.connect(payload.dbPath);
  let table;
  const names = await db.tableNames();
  if (names.includes("memories")) {
    table = await db.openTable("memories");
  } else {
    table = await db.createTable("memories", [{
      id: "__schema__",
      text: "",
      vector: Array.from({ length: payload.dimensions }).fill(0),
      importance: 0,
      category: "other",
      createdAt: 0
    }]);
    await table.delete('id = "__schema__"');
  }
  await table.add(payload.rows);
}
main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
"""
    with tempfile.TemporaryDirectory(prefix="memory_backfill_") as tmp:
        tmp_path = Path(tmp)
        script_path = tmp_path / "insert.js"
        payload_path = tmp_path / "rows.json"
        script_path.write_text(script, encoding="utf-8")
        payload_path.write_text(
            json.dumps({"dbPath": str(db_path), "dimensions": DEFAULT_DIMENSIONS, "rows": rows}, ensure_ascii=False),
            encoding="utf-8",
        )
        env = dict(os.environ)
        node_path = env.get("NODE_PATH", "")
        plugin_node_modules = "/var/lib/openclaw/.openclaw/npm/node_modules"
        env["NODE_PATH"] = plugin_node_modules if not node_path else plugin_node_modules + os.pathsep + node_path
        subprocess.run(["node", str(script_path), str(payload_path)], check=True, text=True, env=env)


def write_candidates(
    candidates: list[MemoryCandidate],
    *,
    db_path: Path,
    base_url: str,
    model: str,
    dimensions: int,
    backfill_log: Path,
) -> list[dict[str, Any]]:
    import uuid
    rows: list[dict[str, Any]] = []
    created_at = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    for item in candidates:
        rows.append(
            {
                "id": str(uuid.uuid4()),
                "text": item.text,
                "vector": embed_text(item.text, base_url, model, dimensions),
                "importance": float(item.importance),
                "category": item.category,
                "createdAt": created_at,
            }
        )
    if rows:
        node_insert_lancedb(db_path, rows)
    backfill_log.parent.mkdir(parents=True, exist_ok=True)
    with backfill_log.open("a", encoding="utf-8") as fh:
        for row, item in zip(rows, candidates):
            fh.write(json.dumps({"created_at": utc_now(), "id": row["id"], "topic": item.topic, "source": item.source, "text": item.text}, ensure_ascii=False) + "\n")
    return rows


def format_output(topic: str, candidates: list[MemoryCandidate], rows: list[dict[str, Any]], write: bool) -> str:
    lines = [
        "长记忆回填结果",
        f"主题：{topic}",
        f"模式：{'写入' if write else 'dry-run'}",
        f"候选条数：{len(candidates)}",
    ]
    if write:
        lines.append(f"写入条数：{len(rows)}")
    for index, item in enumerate(candidates[:8], start=1):
        lines.append(f"{index}. {item.text[:260]}")
    if not candidates:
        lines.append("未找到可回填内容。")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill selected OpenClaw session history into long-term memory.")
    parser.add_argument("--topic", default="xhs", choices=sorted(TOPIC_PATTERNS))
    parser.add_argument("--since", default="")
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--ollama-base-url", default=os.environ.get("OPENCLAW_MEMORY_OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL))
    parser.add_argument("--embed-model", default=os.environ.get("OPENCLAW_MEMORY_EMBED_MODEL", DEFAULT_EMBED_MODEL))
    parser.add_argument("--dimensions", type=int, default=DEFAULT_DIMENSIONS)
    parser.add_argument("--backfill-log", type=Path, default=DEFAULT_BACKFILL_LOG)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.dry_run and args.write:
        raise SystemExit("--dry-run and --write are mutually exclusive")
    write = bool(args.write)
    since = parse_since(args.since)
    candidates = collect_candidates(args.topic, args.sessions_dir, since)
    rows: list[dict[str, Any]] = []
    if write and candidates:
        rows = write_candidates(
            candidates,
            db_path=args.db_path,
            base_url=args.ollama_base_url,
            model=args.embed_model,
            dimensions=args.dimensions,
            backfill_log=args.backfill_log,
        )
    payload = {
        "status": "ok",
        "topic": args.topic,
        "mode": "write" if write else "dry-run",
        "candidate_count": len(candidates),
        "written_count": len(rows),
        "candidates": [asdict(item) for item in candidates],
        "db_path": str(args.db_path),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_output(args.topic, candidates, rows, write))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
