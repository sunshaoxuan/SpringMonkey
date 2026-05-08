# Toolsmith Semantic Stage 4

Date: 2026-05-08 (Asia/Tokyo)

## Current Acceptance Target

Stage 4 moves the toolsmith path from generic read-only helper drafts to semantic read-only repair packages.

The accepted behavior is:

- safe read-only gaps can generate helper code, pytest, registry patch, verify command, and replay policy
- generated semantic helpers inherit contracts and safety metadata from similar registered tools
- generated semantic helpers return structured business output and must not emit a generic `draft` payload
- promotion still requires tests and registry validation
- production writes, credentials, deletes, booking changes, service configuration, and permission expansion remain blocked until explicit authorization

## Verification Entry Points

- Local: `python -m pytest -q scripts/openclaw/test_toolsmith_repair_runner.py scripts/openclaw/test_capability_repair_runner.py`
- Full local: `python -m pytest -q scripts/openclaw`
- Remote smoke: `python scripts/openclaw_remote_cli.py toolsmith-verify`
- Production deploy loop: `python scripts/remote_deploy_toolsmith_semantic.py`

## Boundary

This stage is not an unrestricted autonomous code writer.

It deliberately limits automatic landing and deployment to read-only, no-side-effect helpers that can be validated through the repository registry and test gates.
