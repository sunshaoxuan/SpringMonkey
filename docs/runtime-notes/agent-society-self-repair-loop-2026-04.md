# Agent Society Self-Repair Loop

Date: 2026-04-22 (Asia/Tokyo)

## Goal

`汤猴` should not stop at:

- one failed step
- one missing tool
- one runtime blocker

The runtime should move toward a self-repair loop:

1. observe failure
2. classify the capability gap
3. propose a bounded repair
4. register or refine a helper tool when the gap is reusable
5. return to the parent task instead of drifting forever

## Current MVP Landing

Repository file:

- `scripts/openclaw/agent_society_kernel.py`

The durable kernel now tracks more than `goal -> intent -> task -> step`.

It can also persist:

- `capability_gaps`
- `helper_tools`

## Why This Matters

Previous behavior often stalled like this:

- task step fails
- model keeps spinning or retries blindly
- no durable record of what capability was missing
- same problem comes back later as if it were new

The self-repair loop exists to break that pattern.

## Kernel Additions

### Capability Gap

Each gap records:

- `gap_id`
- `parent_step_id`
- `category`
- `summary`
- `severity`
- `proposed_repair`
- `proposed_tool_name`
- `status`

### Helper Tool

Each helper tool record stores:

- `tool_id`
- `name`
- `scope`
- `kind`
- `entrypoint`
- `status`
- `derived_from_gap_id`
- `notes`

## Current Gap Categories

The kernel currently classifies repeated failures into categories such as:

- `runtime_timeout`
- `tool_missing`
- `runtime_drift`
- `access_blocked`
- `target_discovery_missing`
- `execution_blocked`

This is still a minimal classifier, but it is durable and explicit.

## Current Commands

The kernel CLI now supports:

- `new-session`
- `show`
- `record`
- `analyze-gap`
- `register-tool`
- `propose-helper`
- `validate-tool`
- `close-gap`

This means a runtime or wrapper can:

1. create a session
2. record a failed observation
3. classify the gap
4. register a helper tool proposal
5. continue work with that new tool context

The current minimum self-repair closure is now:

1. `record` a failed or blocked observation
2. `analyze-gap` to classify the failure
3. `propose-helper` to bind a reusable helper proposal to the gap
4. `validate-tool` after the helper path is exercised
5. `close-gap` once the repair path is proven or otherwise resolved

The current bridge direction is now explicit too:

6. `ensure-session` can create or reuse a durable direct-task session
7. `scripts/openclaw/agent_society_helper_toolsmith.py` can land a helper proposal as a bounded executable repo helper
8. validated or promoted helper entrypoints are fed back into later step `tool_candidates`

The current direct-task failure bridge now also supports:

9. `scripts/openclaw/agent_society_runtime_record_gap.py` can record a real direct-task failure into durable kernel state
10. LINE direct no-response fallback can classify that failure as a durable `capability_gap`
11. when the gap is reusable, a bounded executable helper can be created under `scripts/openclaw/helpers/`
12. LINE direct auto-reply exceptions can also be recorded as durable runtime failures instead of disappearing into logs only
13. LINE direct watchdog timeout can also be recorded as a durable `runtime_timeout` style gap
14. the current reusable-helper path covers the already hooked `execution_blocked`, `runtime_timeout`, and `tool_missing` categories, so those failures do not stop at gap recording only
15. generated helpers are now self-validated immediately after creation and can return `validated` instead of remaining at `registered` or `scaffold`
16. for the currently aligned `execution_blocked`, `runtime_timeout`, and `tool_missing` paths, a ready helper can now auto-promote into durable reusable capability
17. repeated failures can now accumulate into durable `failure_patterns` with a lifecycle such as `candidate -> emerging -> learned`, so error handling no longer depends only on hard-coded categories
18. a `learned` failure pattern can now feed back into later gap handling, including helper naming and promotion decisions, instead of remaining passive history
19. `learned` failure patterns can now also influence later step routing, including `tool_candidates`, `chosen_tool`, and `next_decision`
20. cron failure can now be scanned from host journal and recorded into the same durable `capability_gap -> helper -> pattern` loop instead of stopping at a plain failure notification
21. promoted helpers now enter a formal durable helper registry and can be reused by future sessions, instead of living only in the session that first created them
22. generated helpers are now bounded business repairers with a helper contract, repair workflow, and drift guard, so promotion no longer accepts a helper that has already drifted away from its original purpose

In other words, error classification is no longer only a static table.

The current direction is:

- first classify a concrete runtime failure into a `capability_gap`
- then accumulate repeated similar failures into durable `failure_pattern` state
- let those patterns become the next layer of reusable repair knowledge
- and once a pattern is `learned`, let it influence later helper generation and promotion

This is the current minimum self-growth path for error handling.

## Current Limitation

This is not yet a full autonomous toolsmith runtime.

It still lacks:

- automatic interception of every direct task
- automatic code generation for helper tools
- automatic promotion for categories beyond the currently aligned `execution_blocked`, `runtime_timeout`, and `tool_missing` paths
- broader semantic clustering so related failure sub-shapes can merge without being manually enumerated first
  current progress: common timeout / drift / tool-missing / execution-blocked phrasing variants now cluster more aggressively into the same durable pattern

But it provides the durable state model needed for those later steps.

## Recovery Importance

This matters for disaster recovery too.

If the host is rebuilt, a durable kernel plus recovery bundle should preserve:

- previously observed capability gaps
- previously registered helper tools
- the direction of self-improvement work

Without that, the rebuilt agent has to rediscover every missing capability from scratch.
