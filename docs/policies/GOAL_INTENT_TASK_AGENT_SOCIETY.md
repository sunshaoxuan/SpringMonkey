# Goal, Intent, Task, And Agent Society

## Goal

`汤猴` should not behave like a single-pass chat model that occasionally tries tools.

The target runtime is a **goal-directed agent society**:

- one inbound command may contain multiple intents
- intents may produce multiple tasks
- tasks may produce multiple steps
- steps may require different tools or new helper tools
- new sub-intents may appear during execution
- all expansion must still converge toward the parent goal

This policy defines the control model for that behavior.

## Non-Goal

This policy is **not** asking for:

- a fixed workflow hardcoded for one domain
- a single planner prompt that writes a long plan once
- a chatbot that only adds more explanations
- a static tool list that is retried until it fails

## Core Runtime Model

The runtime should reason in layers.

### 1. Goal Layer

Every direct user request must produce:

- one primary goal
- zero or more bounded secondary goals
- explicit completion criteria
- explicit boundary conditions

The primary goal is the convergence anchor.

### 2. Intent Layer

An inbound message may contain multiple intents.

Examples:

- ask a factual question
- perform a website action
- record a durable rule
- verify a result
- report current status
- continue a previously interrupted job

The runtime must extract all relevant intents, not just the first obvious one.

Each intent should carry:

- `intent_id`
- `parent_goal_id`
- `source`
- `priority`
- `status`
- `reason_to_exist`

### 3. Task Layer

Intents become tasks.

Tasks are not assumed to be linear. They may be:

- sequential
- parallel
- conditional
- blocking
- verification-only

Each task should carry:

- `task_id`
- `parent_intent_id`
- `owner`
- `success_condition`
- `evidence_required`
- `status`

### 4. Step Layer

Tasks become steps only when execution is about to happen.

Each step should be concrete and observable:

- one immediate objective
- one best current tool path
- one success check
- one failure classification path

Each step should carry:

- `step_id`
- `parent_task_id`
- `tool_candidates`
- `chosen_tool`
- `expected_observation`
- `actual_observation`
- `next_decision`

### 5. Action / Tool Layer

Steps become actions only at execution time.

An action may be:

- a shell command
- a browser operation
- a parser or helper script
- a pipeline worker
- a message delivery step

`exec` is only an action/tool. It is not allowed to hide a staged or agentic
task as one black-box job.

Cron jobs must follow the same model. Even if the scheduler invokes one command,
the job must still be represented as intent, task, step, action/tool,
observation, repair, retry, and report.

## Expansion And Convergence

### Expansion Rule

The runtime may create new sub-intents, tasks, steps, or helper tools when:

- the previous observation proves a missing dependency
- the previous observation exposes a hidden subproblem
- the previous observation reveals a better path

### Convergence Rule

Every new child object must answer:

1. does this serve the primary goal
2. is this required now
3. is this worth the added cost and drift risk

If the answer is no, the child must be:

- merged
- deferred
- cancelled
- discarded

Unbounded branching is a failure mode.

## Tool Ecology

The runtime must treat tools as a growing ecosystem.

### Tool Categories

- existing tools
- composed tools
- newly created helper tools

### Tool Selection Rule

For each step:

1. prefer a proven existing tool
2. if no existing tool fits, compose a path from existing tools
3. if the gap is stable and reusable, create a helper tool

### Tool Accumulation Rule

The goal is not unlimited tool count.

The goal is:

- stronger reusable capability
- fewer repeated blind retries
- fewer domain-specific dead ends

If the runtime repeatedly encounters the same capability gap, it should prefer creating or improving a helper tool over repeating the same failed path.

## Agent Society

This system should not treat every task as a single-agent problem.

At minimum, the architecture should support differentiated roles:

- `governor`
  - preserves the primary goal, scope, and convergence
- `decomposer`
  - extracts intents and derives tasks
- `worker`
  - executes bounded steps
- `toolsmith`
  - creates or refines helper tools
- `verifier`
  - validates real end state and evidence
- `reporter`
  - renders user-visible progress and final status

One runtime may temporarily collapse multiple roles into one process, but the conceptual boundaries should remain explicit.

## User-Visible Delivery

For direct user work, the runtime should expose execution state.

Minimum visible phases:

1. `accepted`
2. `executing`
3. `progressing` or `blocked`
4. `completed` or `failed`

The user should not be forced to infer whether work started, whether tools were used, or whether the task silently died.

## Operational Task Rule

For website, account, dashboard, console, or settings tasks:

- prefer `browser` first when the task is page-driven
- identify the target system before claiming a path
- discover the real login or settings entry when unknown
- verify observed page state before saying a step is complete

Examples:

- login tests
- password changes
- account settings
- platform dashboards
- workflow consoles

## Evidence And Verification

The final answer must report:

- requested end state
- actual end state
- evidence
- remaining blocker or risk

No final completion claim without machine or direct observed proof.

## Minimal Runtime Implications

The runtime should eventually provide:

- multi-intent extraction
- task graph state
- step execution loop
- tool selection
- observation normalization
- bounded sub-agent delegation
- reusable helper tool creation
- convergence control
- visible execution reporting

## Current Direction

Until a full task graph runtime exists, every patch or prompt protocol should move the system toward:

- less single-pass improvisation
- more explicit decomposition
- more tool-grounded execution
- more bounded expansion
- more reliable convergence

Staged trace is a bridge, not the final control point. The orchestrator state is
the production entry for closing the loop between cron execution, failure
observation, helper growth, and retry.
