# Agent Self-Improvement And Toolsmith Architecture

## Goal

`汤猴` should eventually behave like an agent that can:

- detect when a failure is actually a capability gap
- decide whether that gap is temporary or reusable
- create or refine bounded helper tools
- validate those tools
- return to the parent task
- preserve the new capability as durable runtime knowledge

This document defines the target architecture for that behavior.

It is the formal design document for `汤猴`'s self-improvement path.

## Why This Exists

The current failure mode is not just "model quality is insufficient".

The deeper problem is:

- the runtime can execute many tasks
- but when it hits a missing capability, it often stalls inside the current task loop
- the same class of failure later reappears as if the system learned nothing

The purpose of this architecture is to make repeated failures accumulate into capability, not just frustration.

## External Reference Models

This architecture intentionally borrows from existing agent research and engineering patterns instead of inventing everything from scratch.

### 1. Reflexion

Borrowed idea:

- convert failure into explicit self-critique or repair signal
- use that signal to improve the next attempt instead of repeating the same behavior blindly

Adopted here as:

- durable `capability_gap` classification
- step-level failure reflection
- repair proposal before retry

### 2. Voyager

Borrowed idea:

- accumulate reusable skills instead of treating each task as a fresh blank slate

Adopted here as:

- `helper_tools`
- durable tool registry direction
- preference for reusable helper generation when the same gap repeats

### 3. State-Graph / Reflection Agent Patterns

Borrowed idea:

- agent execution should be a graph or loop with explicit state transitions, not a single long reply

Adopted here as:

- goal / intent / task / step / observation state
- capability-gap transitions
- repair loop transitions

## Non-Goals

This architecture is not asking for:

- unconstrained self-modification
- infinite tool creation
- a system that rewrites its own production environment without verification
- a giant monolithic planner that "thinks harder" once

The target is controlled self-improvement, not unlimited autonomous mutation.

## Core Principles

### 1. Failure Must Be Classified

A failed task step is not enough information.

The runtime must first decide whether the failure is:

- information missing
- target discovery missing
- access blocked
- runtime drift
- tool missing
- tool broken
- timeout or resource bound
- orchestration error

Without this classification, no reliable self-improvement is possible.

### 2. Reusable Gaps Should Produce Reusable Repairs

If the same gap appears repeatedly, the runtime should prefer:

- a helper script
- a parser
- a verifier
- a bundle probe
- a host state inspector
- a domain-specific workflow helper

over repeated blind attempts.

### 3. Repair Must Stay Bounded

Every repair action must answer:

1. does it serve the primary goal
2. is it required now
3. is it reusable enough to justify creation
4. does it stay within approved write scope

If not, it should remain a one-off recovery step, not a new tool.

### 4. Every New Tool Needs Verification

A helper tool is not accepted just because it was written.

It must be:

- executed
- checked against expected observation
- linked to the gap it repaired
- marked with an explicit status

## Runtime Layers

### Layer A: Goal And Convergence

The runtime keeps:

- one primary goal
- bounded secondary goals
- completion criteria
- boundaries

This layer prevents toolsmith expansion from drifting away from the user request.

### Layer B: Intent / Task / Step

The runtime decomposes work into:

- intents
- tasks
- executable steps

This layer provides the execution surface where failure is first observed.

### Layer C: Capability Gap Detection

When a step fails or stalls, the runtime should produce a `capability_gap`.

The gap must include:

- category
- severity
- summary
- proposed repair
- optional proposed helper tool name
- current lifecycle state

### Layer D: Toolsmith

The toolsmith function decides whether to:

- retry with better context
- switch tools
- create a temporary helper
- register a reusable helper
- escalate a blocker to the user

Current implemented step:

- the toolsmith can now generate a bounded business repairer, not just a thin scaffold
- generated repairers include a helper contract, a multi-step repair workflow, and a drift guard
- promotion now requires not only executable output, but also a non-empty repair workflow and a passing drift check

### Layer E: Verification

Every repair step must generate:

- actual observation
- success or failure
- whether the gap is now closed
- whether the new helper should remain in durable state

### Layer F: Accumulation

Successful reusable helpers become durable capability artifacts.

They should eventually map to:

- repo script
- indexed tool note
- runtime registration
- future preference in tool selection

Current implemented step:

- promoted helpers now enter a formal durable registry under the kernel state root
- that registry is used as a cross-session capability source for future tool selection
- helper reuse no longer depends only on the original session that produced the helper

### Layer G: Failure Pattern Learning

Error classification itself should also improve over time.

The durable kernel should not rely only on a fixed list of gap categories.
It should also accumulate repeated similar failures into `failure_pattern` state.

Each pattern should carry:

- a stable signature
- the current base category
- an occurrence count
- example gap ids
- a proposed response
- an optional proposed helper name
- a lifecycle such as `candidate -> emerging -> learned`

This layer is the first self-growth mechanism for error handling:

- one-off failures stay local
- repeated failures become durable patterns
- learned patterns can later influence helper generation, promotion, and routing

Current implemented step:

- a `learned` pattern can already affect later helper naming and promotion decisions in the durable repair loop
- a `learned` pattern can now also affect later step routing, including helper-first `tool_candidates`, `chosen_tool`, and repair-oriented `next_decision`
- cron failure is no longer limited to human-visible timeout notifications; a host watcher can now record cron failure into the same durable self-improvement loop

Current boundary:

- pattern learning is durable and tested
- semantic clustering is now broader for common timeout / drift / tool-missing / execution-blocked variants
- truly distant adjacent sub-shapes are still not merged unless the current signature logic can justify it

## Durable State Model

The current kernel already persists:

- `goal`
- `intent`
- `task`
- `step`
- `observation`
- `capability_gap`
- `helper_tool`

The current kernel CLI also supports an explicit minimum repair lifecycle:

- `analyze-gap`
- `propose-helper`
- `validate-tool`
- `close-gap`

This means the durable state can now represent not only that a gap was noticed, but also:

- which helper was proposed from that gap
- whether the helper path was validated
- whether the gap is still open, being addressed, or closed

The current MVP implementation direction also includes:

- `ensure-session` so direct tasks can reuse or create a durable kernel session
- `scripts/openclaw/agent_society_helper_toolsmith.py` so a reusable helper proposal can land as a bounded executable repo helper
- reuse of validated helper entrypoints as future preferred step tool candidates
- `scripts/openclaw/agent_society_runtime_record_gap.py` so a real runtime failure can be persisted as a gap and optionally materialized into a helper
- LINE direct runtime failure hooks currently cover both `no response generated` and `auto-reply failed` paths
- LINE direct runtime failure hooks now also cover the watchdog timeout path
- the current reusable-helper path is aligned for the already hooked `execution_blocked`, `runtime_timeout`, and `tool_missing` categories
- generated helpers can now self-validate immediately and re-enter the durable state as `validated`
- the same three aligned categories can now auto-promote a ready helper into durable reusable capability

The durable state is meant to answer:

- what failed
- why it failed
- what repair was proposed
- what helper was created
- whether that helper worked

This is the minimum state needed for self-improvement to survive process restarts and host recovery.

## Helper Tool Lifecycle

### 1. Proposed

Created when a reusable gap is detected.

### 2. Registered

Stored in durable state with:

- name
- scope
- kind
- entrypoint
- notes
- source gap

### 3. Validated

A real execution path proves the tool did what it was supposed to do.

### 4. Promoted

The helper becomes part of stable host or repo capability.

Promotion target may be:

- a repo script
- a runtime installer
- a host guard
- a workflow note

### 5. Deprecated

If the helper becomes obsolete due to runtime drift or upstream changes, it must be marked obsolete instead of being silently trusted forever.

## Decision Rules For Tool Creation

The runtime should prefer creating or refining a helper tool when all are true:

- the same failure class is likely to recur
- an existing tool does not cleanly solve it
- the repair can be bounded
- verification is available

The runtime should avoid tool creation when:

- the issue is clearly one-off
- the blocker is missing credentials or human approval
- the helper would simply encode unstable UI selectors without fallback logic
- the tool would exceed the current write authority

## Verification Rules

Every helper tool must have:

- intended scope
- intended success observation
- known failure mode
- one real execution proof before promotion

No helper tool should be considered "real capability" without at least one successful verification chain.

## Relationship To Current Components

### Current Policy Layer

- `GOAL_INTENT_TASK_AGENT_SOCIETY.md`

Defines the control model and role boundaries.

### Current Runtime Bridge Layer

- `agent-society-runtime-guard-2026-04.md`

Provides behavior shaping inside current OpenClaw runtime.

### Current Durable Kernel Layer

- `scripts/openclaw/agent_society_kernel.py`
- `agent-society-kernel-mvp-2026-04.md`
- `agent-society-self-repair-loop-2026-04.md`

Provides the first durable state needed for self-improvement.

## Current Gap Between Design And Reality

The current system still lacks:

- automatic interception of every direct task into kernel state
- automatic generation of helper code from open capability gaps
- automatic promotion of validated helpers into stable host capability
- automatic retirement of obsolete helpers
- first-class scheduler support for toolsmith sub-roles
- broader semantic clustering so adjacent failure sub-shapes can be learned without manual category edits

So the architecture is now defined more completely than the implementation.

That is acceptable at this stage, as long as the implementation moves toward this model instead of away from it.

## Acceptance Standard

This architecture should be considered meaningfully implemented only when all are true:

1. direct tasks can create durable sessions automatically
2. failed steps create durable `capability_gap` records
3. repeated gaps can produce `helper_tool` records
4. at least one helper path can be generated, validated, and reused
5. successful helpers survive host restart or recovery via repo or recovery bundle
6. repeated similar failures can accumulate into durable `failure_pattern` state instead of being forgotten after one repair

## Disaster Recovery Requirement

Self-improvement state is part of runtime value and must be recoverable.

Recovery must preserve:

- capability gap history
- helper tool records
- kernel session state
- any promoted helper scripts that live outside pure upstream OpenClaw

Otherwise a rebuilt host reverts to repeating the same old failures.

## Immediate Next Steps

Near-term implementation should focus on:

1. direct task to kernel-session wiring
2. runtime failure to `capability_gap` wiring
3. helper-tool registration path
4. one validated end-to-end helper example
5. recovery-bundle preservation of kernel state

This is the shortest path from "smart prompts" to genuine self-improving runtime behavior.
