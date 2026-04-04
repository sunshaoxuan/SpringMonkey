# News Numbering Check Policy

## Purpose

Fix repeated numbering regressions in the Discord news digest by turning the formatting rule into a delivery checklist and config-backed prompt contract.

## Canonical Numbering Rule

The digest only allows four top-level numbered headings:

- `1. 日本`
- `2. 中国`
- `3. 国际`
- `4. 市场或风险提示`

Everything else must remain unnumbered.

## Numbering Is Forbidden In

- title line
- time-window line
- body bullet items
- source-link lines

## Explicitly Forbidden Numbering Patterns

These patterns count as formatting failures even if the content is otherwise correct:

- `1.1`
- `1)`
- `（1）`
- `一、`
- `（一）`

## Delivery Checklist

Before a digest is sent, the operator prompt must force a self-check for all of the following:

- 标题不得编号
- 时间窗口不得编号
- 全文只允许出现 4 个一级数字标题
- 一级数字标题必须连续为 1 到 4
- 正文条目只能使用短横线，不能使用数字编号
- 链接行不得带任何编号

## Landing Requirements

Any durable change to numbering behavior must update all three layers together:

1. `config/news/broadcast.json`
2. `scripts/news/apply_news_config.py`
3. `scripts/news/verify_news_config.py`

A change is not considered landed until:

1. config is updated
2. apply script regenerates cron payloads
3. verify script passes
4. the result is committed to `bot/openclaw`

## Why This Exists

Chat-only reminders were too weak. Numbering failures kept recurring because the rule was not encoded as a strict pre-send checklist. This policy makes the rule durable, inspectable, and testable.
