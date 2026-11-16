# Hermes pinned CLI pilot

Authorized and deployed on SpringMonkey on 2026-11-17. See the
[deployment and acceptance report](../../docs/reports/HERMES_DEPLOYMENT_2026-11-17.md).
No Discord connection or fee reservation service is configured.

`Dockerfile` extends the immutable v0.23.1 base using its own locked build,
applies two preverified refusal source files, verifies source/package hashes and
versions, and narrows the catalog to six reviewed Skills. Its complete build
context includes the retained reviewed `skills/`, `patched/agent/`, and
`manifest.json` from formal evidence, beyond this script directory.

`install_docker.py` checks official signing-key identity, records network baselines,
and installs Docker on Ubuntu26.10. `start_container.py` uses the reviewed local
image ID, UID10000, resource limits, readonly policy/Skills and no published ports.
It rejects an existing container and expects root-only credentials staged under
`/etc/hermes-pilot`. The host wrapper serializes tasks and enforces a 900s timeout.

`pilot-config.json` defines GPT, independent DeepSeek and same-gateway Qwen routes.
Two shared session slots accommodate the CLI frontend/backend pair; the host lock
limits top-level tasks to one. `WORKSPACE_AGENTS.md` defines scope. This trusted
single-user container exposes its model client credentials to its own processes.

On the host run `sudo hermes-pilot chat`. Work under `/workspace`, mapped to
`/srv/hermes-pilot/workspace`. No dashboard, messaging gateway, browser, OCR,
runtime dependency installation, delegation or scheduling is enabled.

`acceptance_runtime.py` checks real alternate model responses and document
readback. `acceptance_routing.py` exercises the installed AIAgent with synthetic
loopback providers, including SSE refusal and three-hop availability fallback.
The report also binds real GPT file tasks, restart persistence and SSH checks.

`upstream-pins.json` binds two files to commit
`3b421578588243f920886e6fe79a6faa87ea026e`. `refusal_patch.py` rejects changed
originals and prepares a fresh candidate. Apply the reviewed patch using
`git apply --unidiff-zero` only after matching original digests. Content/provider
policy refusals remain terminal and availability fallback remains enabled.
The unchanged 12 source/patch regressions reuse their previous valid evidence.

Local regression command when those implementation inputs change:

```sh
python -m pytest scripts/hermes-pilot/tests -q -p no:cacheprovider --hermes-source=<verified-source-cache> --basetemp=<task-temporary-directory>
```
