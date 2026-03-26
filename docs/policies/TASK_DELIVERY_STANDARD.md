# Task Delivery Standard

## Required Output Shape

For any meaningful operational task, the delivery report should contain:

1. requested end state
2. actual end state
3. evidence
4. remaining risk

## Forbidden Completion Phrases Without Proof

Do not claim completion with phrases equivalent to:

- already done
- already fixed
- has been enabled
- should now work

unless the report also includes verification evidence.

## Blocked State Standard

If the task is blocked, the report must distinguish:

- blocked but recoverable locally
- blocked by policy
- blocked by missing external dependency

Recoverable local blocks should trigger another attempt, not a final stop.

## Record Standard

If a rule or mechanism was added during troubleshooting, it must be written to:

- a policy or runtime note if it is durable
- a report if it is incident-specific

Durable fixes must not remain chat-only.
