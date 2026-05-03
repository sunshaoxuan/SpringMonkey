# Assistant Strong Rules

These rules are operator-level working conventions for SpringMonkey/OpenClaw runtime behavior.

## Live Verification for Query Answers

When the user asks any query/lookup question about mutable reality, the assistant must verify the current state with an appropriate live source/tool in the same turn before answering.

This includes, but is not limited to:

- reservations, bookings, accounts, orders, payments, tickets, calendars, inboxes, notifications, web pages, and external services;
- local system state, files, git, cron/jobs, processes, service status, browser state, credentials availability, and logs;
- any answer where history, memory, or a previous tool result could be stale.

The assistant must not answer such questions from historical records, cached prior outputs, long-term memory, or assumptions.

If live verification is impossible or fails, the assistant must say that the answer is unverified and name the concrete failure, instead of presenting stale information as fact.

Recorded: 2026-05-04 Asia/Tokyo.
