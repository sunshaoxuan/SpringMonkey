#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = REPO / "config" / "openclaw" / "intent_tools.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ToolContract:
    tool_id: str
    capability_id: str
    domain: str
    actions: list[str]
    goal: str
    use_when: str
    do_not_use_when: str
    input_contract: dict[str, Any]
    output_contract: dict[str, Any]
    permission_scope: str
    safety: str
    write_operation: bool
    examples: list[str] = field(default_factory=list)
    counterexamples: list[str] = field(default_factory=list)


@dataclass
class IntentContract:
    domain: str
    action: str
    capability_family: str
    safety: str
    candidate_tools: list[str]
    use_when: str
    do_not_use_when: str


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _contract_text(tool: dict[str, Any], key: str, fallback: str) -> str:
    value = tool.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def tool_contract(tool: dict[str, Any]) -> ToolContract:
    description = str(tool.get("description") or "").strip()
    domain = str(tool.get("domain") or "unknown")
    actions = _list(tool.get("actions"))
    safety = str(tool.get("safety") or ("write" if bool(tool.get("write_operation")) else "readonly"))
    tool_id = str(tool.get("tool_id") or "")
    capability_id = str(tool.get("capability_id") or tool.get("intent_id") or tool_id)
    return ToolContract(
        tool_id=tool_id,
        capability_id=capability_id,
        domain=domain,
        actions=actions,
        goal=_contract_text(tool, "goal", description or f"{domain}/{','.join(actions) or 'query'} capability"),
        use_when=_contract_text(tool, "use_when", description or "Use when the user request semantically matches this capability."),
        do_not_use_when=_contract_text(
            tool,
            "do_not_use_when",
            "Do not use when the requested goal belongs to another capability, needs missing authorization, or requires external side effects beyond this tool contract.",
        ),
        input_contract=tool.get("input_contract") if isinstance(tool.get("input_contract"), dict) else {},
        output_contract=tool.get("output_contract") if isinstance(tool.get("output_contract"), dict) else {},
        permission_scope=str(tool.get("permission_scope") or tool.get("permission") or ""),
        safety=safety,
        write_operation=bool(tool.get("write_operation")),
        examples=_list(tool.get("examples")) or _list(tool.get("prompt_hints"))[:3],
        counterexamples=_list(tool.get("counterexamples")),
    )


def registry_tool_contracts(registry: dict[str, Any], *, limit: int | None = None) -> list[ToolContract]:
    tools = registry.get("tools") if isinstance(registry.get("tools"), list) else []
    selected = tools if limit is None else tools[:limit]
    return [tool_contract(tool) for tool in selected if isinstance(tool, dict)]


def contract_prompt(registry: dict[str, Any], *, limit: int | None = None) -> str:
    contracts = registry_tool_contracts(registry, limit=limit)
    return json.dumps([asdict(item) for item in contracts], ensure_ascii=False, sort_keys=True)


def intent_contracts(registry: dict[str, Any]) -> list[IntentContract]:
    grouped: dict[tuple[str, str, str], set[str]] = {}
    notes: dict[tuple[str, str, str], list[str]] = {}
    for contract in registry_tool_contracts(registry):
        actions = contract.actions or ["query"]
        for action in actions:
            key = (contract.domain, action, contract.safety)
            grouped.setdefault(key, set()).add(contract.tool_id)
            notes.setdefault(key, []).append(contract.use_when)
    results: list[IntentContract] = []
    for (domain, action, safety), tool_ids in sorted(grouped.items()):
        family = f"{domain}.{action}.{safety}"
        use_when = " / ".join(item for item in notes.get((domain, action, safety), [])[:2] if item)
        results.append(
            IntentContract(
                domain=domain,
                action=action,
                capability_family=family,
                safety=safety,
                candidate_tools=sorted(tool_ids),
                use_when=use_when or f"Use for {domain}/{action} requests.",
                do_not_use_when="Do not use for requests whose goal, safety boundary, or output contract differs from this family.",
            )
        )
    return results


def intent_contract_prompt(registry: dict[str, Any]) -> str:
    return json.dumps([asdict(item) for item in intent_contracts(registry)], ensure_ascii=False, sort_keys=True)
