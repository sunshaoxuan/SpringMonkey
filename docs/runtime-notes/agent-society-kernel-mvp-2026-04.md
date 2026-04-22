# Agent Society Kernel MVP

Date: 2026-04-22 (Asia/Tokyo)

## Goal

Move `汤猴` one layer deeper than runtime prompt injection by introducing a durable state kernel for:

- `goal`
- `intent`
- `task`
- `step`
- `observation`

This is the first native slice toward a real task runtime.

## What It Adds

Repository file:

- `scripts/openclaw/agent_society_kernel.py`

Remote installer:

- `scripts/remote_install_agent_society_kernel.py`

Host workspace artifacts:

- `/var/lib/openclaw/.openclaw/workspace/AGENT_SOCIETY_KERNEL.md`
- `/var/lib/openclaw/.openclaw/workspace/agent_society_kernel/sessions/*.json`

## Current Capabilities

The kernel can:

1. bootstrap a session from a direct request
2. derive one primary goal
3. derive multiple initial intents from request clauses
4. derive one task per initial intent
5. derive one initial step per task
6. attach tool candidates and one current chosen tool
7. persist the resulting state as JSON
8. accept later observations and update task / intent status
9. compute the next active step

## Why This Matters

Previous agent-society work only injected protocol into the OpenClaw runtime bundle.

That improved behavior, but it still lacked:

- durable intent graph state
- durable task graph state
- durable step execution state
- observation history outside prompt text

This MVP starts solving that gap.

## What It Does Not Yet Do

This is not yet:

- a native OpenClaw scheduler
- a full multi-agent governor / worker runtime
- an automatic toolsmith loop
- a host-side orchestrator that intercepts every direct message

It is a durable kernel and minimal execution-loop foundation.

## Intended Next Step

After this MVP exists, the next serious step is:

1. make direct task entry create kernel sessions automatically
2. have runtime status updates write observations back into the kernel
3. let execution choose the next step from durable state instead of prompt-only decomposition
4. only then graduate to true role-separated scheduling
