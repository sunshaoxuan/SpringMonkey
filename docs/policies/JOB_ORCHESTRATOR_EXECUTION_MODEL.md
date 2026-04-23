# Job Orchestrator Execution Model

## Goal

`汤猴` does not need to become a native OpenClaw scheduler to satisfy the
production requirement.

The required execution standard is:

`intent -> task -> step -> action/tool -> observation -> repair -> retry -> report`

A job is acceptable only when it exposes this execution loop and lets failure
feed the self-improvement system.

## Core Rule

`exec` is only one action/tool inside a step.

It must not be treated as the whole task when the work is actually staged or
agentic.

This applies to:

- direct chat tasks
- cron jobs
- pipeline jobs
- browser workflows
- account and website operations

## Orchestrator Contract

The repo-managed job orchestrator is the production bridge for jobs that are
still externally scheduled as cron.

It must:

- create or reuse durable kernel state
- map job prompt and metadata into goal, intent, task, and step state
- run the underlying script command as the current step action/tool
- record stdout, stderr, return code, timeout, and blocker observations
- on failure, write a capability gap and let helper/pattern learning run
- allow only bounded automatic repair and retry
- preserve the user-facing output contract when the job succeeds

## Bounded Repair

Default production bounds:

- one generated or selected helper per failed job run
- one automatic retry after repair evidence is written
- no credential mutation
- no 2FA or approval bypass
- no completion claim without observed evidence

If the bounded repair fails, the job must return a concrete blocker report and
leave durable evidence for the next run.

## Relationship To Staged Trace

Staged trace is useful but not sufficient.

Trace shows what happened inside a script. Orchestrator state decides how the
platform reacts to that observation.

The long-term direction is:

- scripts continue to expose domain stages
- orchestrator records those runs as kernel steps
- self-improvement uses the observations to grow helpers
- helper drift and retirement are enforced before reuse

## Acceptance Standard

A scheduled job is considered aligned only when:

1. it enters durable kernel state before execution
2. its script or command is represented as an action/tool step
3. success writes a completed observation while preserving stdout delivery
4. failure writes a capability gap
5. reusable failures can generate, validate, and promote helpers
6. one bounded retry can return to the original step
7. stale helpers can be deprecated instead of reused forever
