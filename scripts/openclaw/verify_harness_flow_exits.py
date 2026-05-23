#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]

SEMANTIC_FILES = [
    REPO / "scripts" / "openclaw" / "intent_tool_router.py",
    REPO / "scripts" / "openclaw" / "harness_intent_agent.py",
    REPO / "scripts" / "openclaw" / "harness_tool_binder.py",
    REPO / "scripts" / "openclaw" / "harness_dispatcher.py",
    REPO / "scripts" / "openclaw" / "capability_repair_runner.py",
    REPO / "scripts" / "openclaw" / "regression_repair_runner.py",
]

MID_EXIT_FILES = [
    REPO / "scripts" / "openclaw" / "capability_repair_runner.py",
    REPO / "scripts" / "openclaw" / "domain_implementation_runner.py",
    REPO / "scripts" / "openclaw" / "long_task_supervisor.py",
]

FORBIDDEN_TERMINAL_STATUSES = {"blocked", "repair_started", "awaiting_authorization", "internal_repair_required"}
ALLOWED_FINAL_STATUSES = {"final_succeeded", "final_failed", "failed", "delivered", "timed_out"}
SEMANTIC_REGEX_FUNCS = {"search", "match", "fullmatch", "findall", "finditer"}
LOW_LEVEL_PARSER_FUNCTIONS = {
    "classify",
    "parse_local_window_ts",
    "extract_cron_job_from_text",
    "extract_args",
}


@dataclass
class Finding:
    path: Path
    line: int
    message: str


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def string_value(node: ast.AST) -> str:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""


def called_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            return func.attr
        if isinstance(func, ast.Name):
            return func.id
    return ""


def scan_semantic_file(path: Path) -> list[Finding]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[Finding] = []
    function_stack: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            function_stack.append(node.name)
            self.generic_visit(node)
            function_stack.pop()

        def visit_Call(self, node: ast.Call) -> None:
            if function_stack and function_stack[-1] in LOW_LEVEL_PARSER_FUNCTIONS:
                return
            name = called_name(node)
            if name in SEMANTIC_REGEX_FUNCS:
                findings.append(Finding(path, getattr(node, "lineno", 0), f"semantic layer uses regex call {name}"))
            if name == "get" and node.args:
                key = string_value(node.args[0])
                if key in {"patterns", "required_any"}:
                    findings.append(Finding(path, getattr(node, "lineno", 0), f"semantic layer reads legacy routing field {key}"))
            self.generic_visit(node)

        def visit_Subscript(self, node: ast.Subscript) -> None:
            if function_stack and function_stack[-1] in LOW_LEVEL_PARSER_FUNCTIONS:
                return
            key = ""
            if isinstance(node.slice, ast.Constant):
                key = string_value(node.slice)
            if key in {"patterns", "required_any"}:
                findings.append(Finding(path, getattr(node, "lineno", 0), f"semantic layer indexes legacy routing field {key}"))
            self.generic_visit(node)

    Visitor().visit(tree)
    return findings


def scan_mid_exits(path: Path) -> list[Finding]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Return):
            values: set[str] = set()
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                values.add(node.value.value)
            if isinstance(node.value, (ast.Set, ast.List, ast.Tuple)):
                for item in node.value.elts:
                    if isinstance(item, ast.Constant) and isinstance(item.value, str):
                        values.add(item.value)
            if values & FORBIDDEN_TERMINAL_STATUSES and not values & ALLOWED_FINAL_STATUSES:
                findings.append(Finding(path, getattr(node, "lineno", 0), f"returns non-final status as terminal: {sorted(values & FORBIDDEN_TERMINAL_STATUSES)}"))
        if isinstance(node, ast.Set):
            values = {item.value for item in node.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)}
            if values & FORBIDDEN_TERMINAL_STATUSES and "final_succeeded" not in values and "final_failed" not in values:
                findings.append(Finding(path, getattr(node, "lineno", 0), f"status set contains non-final exit without final pair: {sorted(values & FORBIDDEN_TERMINAL_STATUSES)}"))
    return findings


def main() -> int:
    findings: list[Finding] = []
    for path in SEMANTIC_FILES:
        if path.is_file():
            findings.extend(scan_semantic_file(path))
    for path in MID_EXIT_FILES:
        if path.is_file():
            findings.extend(scan_mid_exits(path))
    if findings:
        for item in findings:
            print(f"HARNESS_FLOW_EXIT_FAIL: {rel(item.path)}:{item.line}: {item.message}", file=sys.stderr)
        return 1
    print("harness_flow_exits_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
