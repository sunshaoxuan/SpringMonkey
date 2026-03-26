# News Task Domain

News broadcasting is now intended to be changed through a task-domain workflow instead of ad hoc edits to `jobs.json`.

## Control Surface

- Machine-readable config:
  - `config/news/broadcast.json`
- Apply tool:
  - `scripts/news/apply_news_config.py`
- Verify tool:
  - `scripts/news/verify_news_config.py`

## Intended Workflow For 汤猴

1. Update `config/news/broadcast.json`
2. Run `scripts/news/apply_news_config.py`
3. Run `scripts/news/verify_news_config.py`
4. Report only after verification passes
5. Commit the config or docs change to `bot/openclaw`

## Scope

This task domain is intended to let `汤猴` adjust:

- schedule expressions
- time windows
- news outline rules
- numbering rules
- delivery target already assigned to the news workflow

It is not intended to grant authority over unrelated host security boundaries.
