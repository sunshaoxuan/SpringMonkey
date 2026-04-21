# Agent Society Runtime Guard

Date: 2026-04-22 (Asia/Tokyo)

## Goal

Push `汤猴` away from "single-pass chat reply + occasional tool use" toward a runtime that is:

- visible to the user
- operationally stronger
- more structured in decomposition
- less likely to silently die after long internal thinking

## Scope

This runtime guard is still a **bridge layer**, not the final task-graph operating system.

It currently adds three kinds of behavior on the host:

1. direct-chat three-phase visibility
2. operational-task execution protocol
3. goal-intent-task-agent-society protocol injection

## Installed Host Patches

### 1. Three-Phase Reply Guard

Host installer:

- `python SpringMonkey/scripts/remote_install_three_phase_reply_guard.py`

Behavior:

- direct LINE main-session tasks get an early visible acknowledgement
- long-running work gets at least one progress update
- if the model produces silent or empty final output, the runtime emits a fallback visible closing message instead of dropping the turn

### 2. Operational Execution Guard

Host installer:

- `python SpringMonkey/scripts/remote_install_operational_execution_guard.py`

Behavior:

- detects direct operational work such as login, password, settings, browser tasks
- injects a runtime protocol that forces plan-execute-observe-replan behavior
- pushes website/account work toward browser-first execution

### 3. Agent Society Runtime Guard

Host installer:

- `python SpringMonkey/scripts/remote_install_agent_society_runtime_guard.py`
- startup self-heal: `python SpringMonkey/scripts/remote_install_agent_society_startup_guard.py`

Behavior:

- upgrades the operational protocol into a broader goal-intent-task-step-agent-society protocol
- tells the runtime to extract multiple intents
- requires task and step decomposition
- allows bounded sub-intent expansion
- requires convergence back to the parent goal
- encourages reusable helper-tool creation when stable capability gaps are detected
- writes a host workspace bridge file at `/var/lib/openclaw/.openclaw/workspace/AGENT_SOCIETY_RUNTIME.md`
- can now be re-applied from the repo patch source `scripts/openclaw/patch_agent_society_runtime_current.py`

## Why This Exists

The earlier failure mode was not just `NO_REPLY`.

Observed bad behaviors included:

- user message arrived
- runtime entered internal thinking
- no visible acknowledgement was sent
- no progress update was sent
- final user-visible report never arrived

This made operational work look dead even when the message had been received.

## What This Guard Does Not Yet Provide

This is **not yet** a full hierarchical task operating system.

Missing pieces still include:

- durable intent graph state
- durable task graph state
- first-class step objects
- structured observation storage
- real governor / decomposer / worker / verifier separation
- automatic reusable tool registration lifecycle

## Current Architectural Position

Think of the current host as:

- better than a single-pass agent
- not yet a complete task graph runtime
- published from Git, with host startup self-heal responsible for replaying the runtime patch after upgrades or bundle replacement

The new runtime behavior is best described as:

- prompt- and runtime-assisted decomposition
- delivery-state enforcement
- bounded execution guidance

## Validation

After installation, confirm all of the following:

1. `openclaw.service` restarts cleanly
2. `http://127.0.0.1:18789/healthz` responds
3. `agent-runner.runtime-CTlghBhJ.js` contains:
   - `shouldForceVisibleLifecycle`
   - `[runtime-operational-execution-protocol]`
   - `[runtime-goal-intent-task-agent-society-protocol]`
   - `shouldApplyAgentSocietyProtocol`
4. a direct LINE operational request now:
   - receives an acknowledgement
   - receives progress if it runs long enough
   - does not silently vanish on empty/silent final output
   - is pushed toward multi-intent extraction, task/step decomposition, bounded expansion, and reusable helper-tool creation

## Next Stage

The next serious step is no longer another prompt tweak.

It is a runtime-level shift toward:

- intent graph
- task graph
- step graph
- tool ecology
- bounded sub-agent orchestration

This guard is the transitional layer that makes that deeper rebuild possible.
