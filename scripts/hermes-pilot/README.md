# Hermes pinned CLI pilot

Authorized and deployed on SpringMonkey on 2026-11-17. See the
[deployment and acceptance report](../../docs/reports/HERMES_DEPLOYMENT_2026-11-17.md).
No Discord connection or fee reservation service is configured.
See [current research/dashboard status](../../docs/reports/HERMES_RESEARCH_AND_DASHBOARD_2026-11-17.md).
The current deployment has 70 enabled skills and eight native workflow bundles;
see the [expansion receipt](../../docs/reports/HERMES_CAPABILITY_EXPANSION_2026-11-17.md)
and [capability guide](CAPABILITIES.md). The original six-skill image is the r1 base.
`Dockerfile.capabilities` extends that exact local base with Office/OCR/rendering
tools and a separate hash-locked Python environment. Check the r1 image ID before
building it. Runtime skill sources are the reviewed readonly host mount, with
the pinned source archive and licenses retained in the expansion evidence.

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
Exa search/extract and local headless Chromium are enabled.
Two shared session slots accommodate the CLI frontend/backend pair; the host lock
limits top-level tasks to one. `WORKSPACE_AGENTS.md` defines scope. This trusted
single-user container exposes its model client credentials to its own processes.

On the host run `sudo hermes-pilot chat`. Work under `/workspace`, mapped to
`/srv/hermes-pilot/workspace`. The official dashboard sidecar runs as UID10001 on host loopback9119 with Nous OAuth.
Public HTTPS, Nous owner login and native config Save have passed acceptance.
The official UI has a known 9px control overflow at a 390px mobile viewport; desktop
1024px and wider was checked. No messaging gateway, OCR,
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


The canonical config is /srv/hermes-pilot/policy/config.yaml, UID10001/GID10000,
mode0640, in an administrator-owned0750 policy directory. The CLI home is
/srv/hermes-pilot/cli-home (UID10000/0700); dashboard home is
/srv/hermes-pilot/data (UID10001/0700). Each home config.yaml symlinks to
../policy/config.yaml. Native atomic saving preserves the symlink. The CLI mounts
policy readonly and uses HERMES_MANAGED_DIR=/opt/policy to pin administrator values.
Prepare these homes, links and the policy directory before start_container.py.
Both containers mount /srv/hermes-pilot/data/skill-bundles readonly. Old state
remains in the dashboard home; new CLI sessions have separate state.
The former /etc/hermes-pilot/config.json is not read at runtime. start_dashboard.py
starts the official UI using the registered client in the protected env file.
acceptance_research.py checks real search, browser and arXiv tools.
publish_dashboard.py prepare installs only the dedicated domain's HTTP/ACME
site and loopback-only FRP firewall unit. activate issues the dedicated
certificate and enables HTTPS after DNS/redirect changes are confirmed and the
domain resolves. The approved DNS-only record and OAuth callback are now saved.
`install_dashboard_renewal.py` installs the dedicated twice-daily certificate
timer and conditional Nginx deploy hook from `/srv/hermes-dashboard-public`.
It renews only sm.briconbric.com, using the existing free Let's Encrypt certificate.
The UID10000 config-write boundary was verified for the CLI; GUI chat is outside
this acceptance and the trusted administrator UI runs as UID10001.
Never include credentials in this tree.

`acceptance_capabilities.py` exercises bounded synthetic CSV/analysis, Office
conversion, formula recalculation, PDF rendering, OCR, code statistics, RSS and
Playwright with the deployed tools. It is an acceptance fixture, not a benchmark
or a guarantee for arbitrary documents. Reuse its PASS for the pinned image when
its inputs and execution environment remain valid.

For rollback, stop and replace only the two owned containers, restore the original
reviewed skills mount and r1 image ID, and use the current private-home startup
scripts. Keep the private-home/policy arrangement: the older root-sticky home
fails native control-socket discovery. Archived stopped containers retain older
mounts and must not be started blindly. Preserve all user state and recovery data.
