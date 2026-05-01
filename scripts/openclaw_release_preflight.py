#!/usr/bin/env python3
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


def run(command: list[str], *, input_text: str | None = None) -> None:
    proc = subprocess.run(
        command,
        cwd=REPO,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        detail = "\n".join(x for x in (proc.stdout.strip(), proc.stderr.strip()) if x)
        raise SystemExit(f"PRECHECK_FAIL command={' '.join(command)}\n{detail}")


def python_files() -> list[Path]:
    ignored_parts = {"__pycache__", ".pytest_cache"}
    return sorted(
        path
        for path in SCRIPTS.rglob("*.py")
        if not any(part in ignored_parts for part in path.parts)
    )


def py_compile_all() -> None:
    files = [str(path.relative_to(REPO)) for path in python_files()]
    run([sys.executable, "-m", "py_compile", *files])


def run_targeted_tests() -> None:
    tests = [
        "scripts/test_repository_guardrails.py",
        "scripts/test_remote_install_direct_discord_cron.py",
        "scripts/weather/test_discord_weather_report.py",
    ]
    for test in tests:
        if (REPO / test).is_file():
            run([sys.executable, test])


def module_string_assignments(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                values[target.id] = node.value.value
    return values


def bash_syntax_check(name: str, script: str) -> None:
    script = script.replace("\r\n", "\n").replace("\r", "\n")
    proc = subprocess.run(
        ["bash", "-n", "-s"],
        cwd=REPO,
        input=script.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        stdout = proc.stdout.decode("utf-8", errors="replace").strip()
        raise SystemExit(f"PRECHECK_FAIL bash_syntax name={name}\n{stderr or stdout}")


def find_unquoted_heredoc_expansion(script: str) -> list[str]:
    script = script.replace("\r\n", "\n").replace("\r", "\n")
    lines = script.splitlines()
    findings: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        marker = None
        if "<<" in line:
            tail = line.split("<<", 1)[1].strip()
            if tail and not tail.startswith(("'", '"', "\\")):
                marker = tail.split()[0].strip()
        if not marker:
            index += 1
            continue
        body_start = index + 1
        index += 1
        body: list[str] = []
        while index < len(lines) and lines[index].strip() != marker:
            body.append(lines[index])
            index += 1
        body_text = "\n".join(body)
        if "$(" in body_text or "`" in body_text:
            findings.append(f"line {body_start}: unquoted heredoc <<{marker} contains command substitution")
        index += 1
    return findings


def validate_embedded_shell() -> None:
    failures: list[str] = []
    for path in sorted(SCRIPTS.glob("remote_*.py")):
        strings = module_string_assignments(path)
        for name, value in strings.items():
            if name != "REMOTE":
                continue
            bash_syntax_check(f"{path.relative_to(REPO)}:{name}", value)
            heredoc_findings = find_unquoted_heredoc_expansion(value)
            if heredoc_findings:
                joined = "\n  ".join(heredoc_findings)
                failures.append(f"{path.relative_to(REPO)}:\n  {joined}")
    if failures:
        raise SystemExit("PRECHECK_FAIL unsafe embedded shell heredoc\n" + "\n".join(failures))


def main() -> int:
    py_compile_all()
    validate_embedded_shell()
    run_targeted_tests()
    print("openclaw_release_preflight_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
