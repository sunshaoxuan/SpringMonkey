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

This means a runtime or wrapper can:

1. create a session
2. record a failed observation
3. classify the gap
4. register a helper tool proposal
5. continue work with that new tool context

## Current Limitation

This is not yet a full autonomous toolsmith runtime.

It still lacks:

- automatic interception of every direct task
- automatic code generation for helper tools
- automatic validation and promotion of helper tools into standard host capability

But it provides the durable state model needed for those later steps.

## Recovery Importance

This matters for disaster recovery too.

If the host is rebuilt, a durable kernel plus recovery bundle should preserve:

- previously observed capability gaps
- previously registered helper tools
- the direction of self-improvement work

Without that, the rebuilt agent has to rediscover every missing capability from scratch.
