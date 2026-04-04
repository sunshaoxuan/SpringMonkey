# News Two-Stage Generation Policy

## Purpose

The news digest must no longer hand the full candidate batch to a single model for end-to-end selection and drafting.

Default mode is now **two-stage per-item processing**.

## Default Workflow

Unless the user explicitly overrides it, every news broadcast run must follow this order:

1. per-item candidate evaluation
2. persisted intermediate records
3. mechanical merge
4. final Codex formatting pass

## Stage 1: Per-item Candidate Evaluation

Each candidate news item must be processed separately.

Rules:

- evaluate one candidate at a time
- prefer the local model during this stage
- do not use Codex first
- emit one structured record per candidate

Required record fields:

- `keep`
- `section`
- `factSummary`
- `sourceUrl`
- `sourceName`
- `publishedAt`
- `reason`

## Stage 2: Intermediate Results Must Be Written To Disk

Per-item outputs must not live only in model context.

Each run should create its own temp directory under the configured task temp root and append records into:

- `candidate-records.ndjson`

## Stage 3: Mechanical Merge Before Final Draft

Before any final drafting pass, a script must do the non-AI merge work:

- dedupe
- group by section
- sort by time
- check source URL completeness

Default script:

- `scripts/news/merge_candidate_records.py`

Expected merged output:

- `merged-records.json`

## Stage 4: Final Codex Pass

Codex is allowed only after stages 1-3 are complete.

Codex may only handle:

- overall formatting
- numbering normalization
- tone tightening
- source overview

Codex must not re-screen the entire candidate batch.

## Run Outputs

Each run should produce at least:

- temp candidate file
- merged record file
- final draft file
- run summary file

Suggested names:

- `candidate-records.ndjson`
- `merged-records.json`
- `final-draft.md`
- `run-summary.json`

## Reporting Rule

Completion reports for this workflow should only include:

- stages used
- local model candidate count
- whether Codex was used
- temp result file location
- final draft file location
