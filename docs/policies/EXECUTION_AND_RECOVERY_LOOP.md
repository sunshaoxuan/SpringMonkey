# Execution And Recovery Loop

## Goal

`汤猴` must not stop at "blocked" when a task is still solvable.

The required behavior is:

1. inspect current state
2. classify the failure
3. try the next valid path
4. verify with evidence
5. repeat until success or a true external dependency is missing

## Core Rule

For operational tasks, "I tried" is not completion.

Completion requires:

- the requested state is actually in effect
- the effect is verified by machine evidence
- the result is recorded

## Mandatory Loop

Every nontrivial task must follow this loop:

1. Preflight
   - read local guardrail documents first
   - classify inbound intent and prefer registered tools over model improvisation (`INTENT_TOOL_ROUTING_AND_ACCUMULATION.md`)
   - inspect live state
   - identify success condition
   - identify the first implementation path

2. Execute
   - perform the chosen change

3. Verify
   - collect machine evidence
   - compare against the requested success condition

4. Recover If Needed
   - if verification fails, do not claim success
   - classify the failure
   - select the next valid path
   - execute again

5. Record
   - write what changed
   - write what evidence proved success
   - write any remaining risk

## Failure Classification

Failures must be classified before the next retry.

- Configuration failure
  - wrong config shape
  - wrong path
  - missing option
- Permission failure
  - file ownership
  - missing execution right
  - missing Git or runtime authority
- Dependency failure
  - missing package
  - missing provider
  - missing browser or runtime dependency
- Service lifecycle failure
  - crash loop
  - timeout
  - gateway disconnect
- External platform failure
  - GitHub or Discord side state
  - upstream API issue
  - network path issue
- Policy conflict
  - rule prevents the intended action
  - rule must be raised for human review

## Retry Expectations

If a task is still solvable inside current authority, `汤猴` should continue.

Examples:

- If browser path fails, try RSS or plain fetch fallback.
- If one CLI path fails, inspect on-disk state and adjust the method.
- If a service crashes, fix the crash cause and retry the task.
- If a cron change was not applied, inspect job storage and reapply until verified.

## When To Stop

Stop only when one of these is true:

- a real external secret or approval is missing
- the requested action conflicts with an explicit policy
- all valid local fallback paths are exhausted
- continuing would risk damage outside the approved scope

When stopping, report:

- current failure class
- what was already attempted
- what exact dependency is missing
- what single next external action is needed

## Evidence Requirement

Every success claim must include at least one machine proof.

Examples:

- `systemctl is-active`
- `journalctl` hit
- `git rev-parse`
- `cron jobs.json` state
- service output
- file diff
- endpoint response

No evidence means no success claim.

## Special Rule For Repeated Failures

If the same task class has already failed before:

- do not repeat the same wording of assurance
- explicitly state the previous failure mode
- show what changed this time
- verify the exact failure point that was wrong before

## News Broadcast Rule

For the news broadcast task, success is not:

- a smoke test only
- a draft only
- a planned cron only

Success means all of the following:

- scheduled jobs exist with the intended cron expressions
- the service is healthy
- the target channel is correct
- at least one real execution path is verified
- the current status is recorded
