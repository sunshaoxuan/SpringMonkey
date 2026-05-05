#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


OWNER_USER_ID = "999666719356354610"


@dataclass
class GovernanceDecision:
    allowed: bool
    reason: str
    required_permissions: list[str]
    policy_hits: list[str]
    report_visibility: str = "owner_dm"


def evaluate_tool_invocation(tool: dict[str, Any], *, channel: str, user_id: str) -> GovernanceDecision:
    required: list[str] = []
    hits: list[str] = []
    permission = str(tool.get("permission") or "")
    if permission:
        required.append(permission)
    if tool.get("write_operation"):
        required.append("write_operation")
        hits.append("write_operation_requires_owner_dm")
        if channel != "discord_dm" or user_id != OWNER_USER_ID:
            return GovernanceDecision(False, "write operation requires owner Discord DM", required, hits, "owner_dm")
        if not tool.get("confirm_policy") or not tool.get("idempotency"):
            return GovernanceDecision(False, "write operation lacks confirm_policy or idempotency", required, hits, "owner_dm")
    if permission == "owner_dm" and channel != "discord_dm":
        return GovernanceDecision(False, "owner DM permission requires direct message channel", required, hits, "owner_dm")
    if permission == "owner_dm_write" and (channel != "discord_dm" or user_id != OWNER_USER_ID):
        return GovernanceDecision(False, "owner DM write permission denied", required, hits, "owner_dm")
    visibility = "owner_dm"
    if channel != "discord_dm" and not tool.get("write_operation"):
        visibility = "public_success_owner_failure"
    return GovernanceDecision(True, "allowed", required, hits, visibility)
