#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil


def resolve_selection_bundle(dist: Path) -> Path:
    candidates = sorted(
        [p for p in dist.glob("selection-*.js") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SystemExit("selection runtime bundle not found")
    return candidates[0]


def main() -> int:
    dist = Path("/usr/lib/node_modules/openclaw/dist")
    target = resolve_selection_bundle(dist)
    text = target.read_text(encoding="utf-8")

    old_block = '''\tlet route = "fits";\n\tif (overflowTokens > 0) if (toolResultReducibleChars <= 0) route = "compact_only";\n\telse if (toolResultReducibleChars >= truncateOnlyThresholdChars) route = "truncate_tool_results_only";\n\telse route = "compact_then_truncate";\n\treturn {\n\t\troute,\n\t\tshouldCompact: route === "compact_only" || route === "compact_then_truncate",\n\t\testimatedPromptTokens,\n\t\tpromptBudgetBeforeReserve,\n\t\toverflowTokens,\n\t\ttoolResultReducibleChars,\n\t\teffectiveReserveTokens\n\t};\n}\n'''
    new_block = '''\tconst proactiveThresholdTokens = Math.max(1, Math.floor(promptBudgetBeforeReserve * .9));\n\tconst proactiveMessageThreshold = 48;\n\tlet route = "fits";\n\tif (overflowTokens > 0) if (toolResultReducibleChars <= 0) route = "compact_only";\n\telse if (toolResultReducibleChars >= truncateOnlyThresholdChars) route = "truncate_tool_results_only";\n\telse route = "compact_then_truncate";\n\telse if (params.messages.length >= proactiveMessageThreshold && estimatedPromptTokens >= proactiveThresholdTokens) route = "compact_only";\n\treturn {\n\t\troute,\n\t\tshouldCompact: route === "compact_only" || route === "compact_then_truncate",\n\t\testimatedPromptTokens,\n\t\tpromptBudgetBeforeReserve,\n\t\toverflowTokens,\n\t\ttoolResultReducibleChars,\n\t\teffectiveReserveTokens\n\t};\n}\n'''

    old_proactive_block = '''\tconst proactiveThresholdTokens = Math.max(1, Math.floor(promptBudgetBeforeReserve * .82));\n\tconst proactiveMessageThreshold = 48;\n\tlet route = "fits";\n\tif (overflowTokens > 0) if (toolResultReducibleChars <= 0) route = "compact_only";\n\telse if (toolResultReducibleChars >= truncateOnlyThresholdChars) route = "truncate_tool_results_only";\n\telse route = "compact_then_truncate";\n\telse if (params.messages.length >= proactiveMessageThreshold && estimatedPromptTokens >= proactiveThresholdTokens) route = "compact_only";\n\treturn {\n\t\troute,\n\t\tshouldCompact: route === "compact_only" || route === "compact_then_truncate",\n\t\testimatedPromptTokens,\n\t\tpromptBudgetBeforeReserve,\n\t\toverflowTokens,\n\t\ttoolResultReducibleChars,\n\t\teffectiveReserveTokens\n\t};\n}\n'''
    if "const proactiveThresholdTokens = Math.max(1, Math.floor(promptBudgetBeforeReserve * .9));" not in text:
        if old_proactive_block in text:
            text = text.replace(old_proactive_block, new_block, 1)
        elif old_block in text:
            text = text.replace(old_block, new_block, 1)
        else:
            raise SystemExit("preemptive compaction route anchor not found")

    backup = target.with_name(f"{target.name}.bak-preemptive-compaction-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(target, backup)
    target.write_text(text, encoding="utf-8")
    print(f"PATCHED_BUNDLE {target}")
    print(f"BACKUP_BUNDLE {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
