# TimesCar on SpringMonkey Hermes

As of 2026-11-18, searches of the public web and GitHub repository metadata
did not identify a verified TimesCar MCP or a usable public TimesCar skill.
SpringMonkey already contains earlier TimesCar automation and site discovery
notes. The current integration uses the Hermes browser and authored skill.

The official TimesCar site was retrieved from the running Hermes dashboard
container without authentication. The personal member form exposes 4 digits
in `cardNo1`, 6 digits in `cardNo2`, and a separate password input.

## Runtime changes

- The installed catalog remains read-only. `skills.create_dir` now points
  to `/workspace/authored-skills` on the existing shared workspace mount.
- The TimesCar skill installed there explains the two fields, human handoff,
  authorized reservation reads, change preparation and confirmation.
- The live working instructions explicitly tell Hermes to open an authorized
  site's official entry, use the owner-authorized browser session, and ask
  for handoff when login is required. Hermes may author reusable skills
  in the authored directory using its native approval flow when prompted.

Both running containers loaded the installed skill through `skill_view`,
resolved the same writable creation directory, and verified the original skill
catalog was still read-only. In an isolated Hermes home the native
`skill_manage` created a synthetic skill in an alternative directory and
`skill_view` could read it back. A real new conversation on the dashboard
profile loaded TimesCar and explained the 4+6 field split, login handoff and
learning a selector correction. The reported original rejection was not
located in the dashboard conversation database checked during this work.

## First private use

In a new Hermes chat, ask it to use the TimesCar skill and open the official
site in Bot Screen. When sign-in is required, use Take over to enter the
two member-number fields and password. Hand back to Hermes and ask it to
inspect the reservation list. Reserve, change, or cancel only when the
owner has authorized the current operation. Confirm the outcome in the
reservation list after any submission.

No private TimesCar login, reservation read, modification, or recurring
job was performed in this verification. Rollback copies of the previous
policy and workspace instructions are under `/srv/hermes-pilot/b15-timescar`.

- [TimesCar official member login instructions](https://share.timescar.jp/faq/mypage/15.html)
- [Hermes Bot Screen and handoff](https://hermes-agent.nousresearch.com/docs/user-guide/features/bot-screen)
- [Hermes native skill creation](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)
