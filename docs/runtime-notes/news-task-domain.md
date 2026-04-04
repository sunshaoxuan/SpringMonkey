# News Task Domain

News broadcasting is now intended to be changed through a task-domain workflow instead of ad hoc edits to `jobs.json`.

## Control Surface

- Machine-readable config:
  - `config/news/broadcast.json`
- Apply tool:
  - `scripts/news/apply_news_config.py`
- Verify tool:
  - `scripts/news/verify_news_config.py`
- Workspace mirror for editing from OpenClaw:
  - `~/.openclaw/workspace/SpringMonkey/`

## Intended Workflow For 汤猴

1. Update `~/.openclaw/workspace/SpringMonkey/config/news/broadcast.json`
2. Mirror or save the same change into the repo working copy under `/var/lib/openclaw/repos/SpringMonkey/`
3. Run `scripts/news/apply_news_config.py`
4. Run `scripts/news/verify_news_config.py`
5. Report only after verification passes
6. Commit the config or docs change to `bot/openclaw`

## Path Rule

- Do not use `apply_patch` against absolute repo paths outside `~/.openclaw/workspace`.
- If editing from Discord/embedded agent mode, prefer the workspace mirror path first.
- The repo working copy under `/var/lib/openclaw/repos/SpringMonkey` remains the source for Git commits.

## Scope

This task domain is intended to let `汤猴` adjust:

- schedule expressions
- time windows
- news outline rules
- numbering rules
- per-item candidate-processing workflow
- intermediate file layout and merge scripts
- delivery target already assigned to the news workflow

It is not intended to grant authority over unrelated host security boundaries.

## Default Generation Contract

Unless the user explicitly overrides it, news generation now defaults to a two-stage workflow:

1. process candidate items one by one, preferably with a local model
2. append each structured decision to a task-local temp file
3. run a script for dedupe / grouping / time sort / source-link checks
4. use Codex only once at the very end for final formatting and numbering cleanup
