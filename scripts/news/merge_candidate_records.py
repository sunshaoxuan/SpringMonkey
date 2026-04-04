#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

REQUIRED_FIELDS = [
    "keep",
    "section",
    "factSummary",
    "sourceUrl",
    "sourceName",
    "publishedAt",
    "reason",
]
VALID_SECTIONS = {"日本", "中国", "国际"}


def load_ndjson(path: Path):
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"invalid json on line {line_no}: {exc}") from exc
    return rows


def normalize_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    normalized_path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{normalized_path}"


def validate_record(record: dict, index: int):
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        raise SystemExit(f"record {index} missing fields: {', '.join(missing)}")
    section = record.get("section")
    if record.get("keep") and section not in VALID_SECTIONS:
        raise SystemExit(f"record {index} has invalid section: {section}")
    normalized = normalize_url(record.get("sourceUrl", ""))
    if record.get("keep") and not normalized:
        raise SystemExit(f"record {index} has invalid sourceUrl")
    record["normalizedSourceUrl"] = normalized


def dedupe_records(records):
    seen = set()
    deduped = []
    for record in records:
        key = (
            record.get("normalizedSourceUrl") or record.get("sourceUrl", "").strip(),
            record.get("factSummary", "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def build_output(records: list[dict]):
    kept = [record for record in records if record.get("keep")]
    deduped = dedupe_records(kept)
    grouped = defaultdict(list)
    for record in deduped:
        grouped[record["section"]].append(record)
    for section in grouped:
        grouped[section].sort(key=lambda row: row.get("publishedAt", ""), reverse=True)

    return {
        "counts": {
            "input": len(records),
            "kept": len(kept),
            "deduped": len(deduped),
        },
        "sections": {
            section: grouped.get(section, [])
            for section in ["日本", "中国", "国际"]
        },
        "linkCheck": {
            "allKeptRecordsHaveValidSourceUrl": all(record.get("normalizedSourceUrl") for record in deduped),
            "checkedField": "sourceUrl",
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="candidate ndjson file")
    parser.add_argument("output", help="merged json file")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records = load_ndjson(input_path)
    for index, record in enumerate(records, start=1):
        validate_record(record, index)

    doc = build_output(records)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("MERGE_OK")
    print(output_path)


if __name__ == "__main__":
    main()
