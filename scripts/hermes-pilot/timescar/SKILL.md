---
name: timescar
description: Use the owner's authorized TimesCar member website to check availability, inspect reservations, or prepare a specific reservation change with browser handoff.
---

# TimesCar

Use the persistent headed browser on Bot Screen for owner-authorized TimesCar
tasks. Start at [the official site](https://share.timescar.jp/) and follow its
visible member or reservation navigation. Check the current domain and page
before proceeding, especially after a redirect or human handoff.

## Login and handoff

The personal member login uses one 10-digit membership number displayed as two
inputs. The current official page exposes `#cardNo1` for the first 4 digits,
`#cardNo2` for the last 6, and `#tpPassword` for the password. Verify both input
lengths if the site changes. Preserve any leading zeros.

If signed out, open the official login screen and ask the owner to select
**Take over** to enter the two segments, password, and any verification the
site requires. Resume after **Hand back**. Check the signed-in homepage or the
reservation list before reporting success. An expired session, access error,
or maintenance page is not an empty reservation list.

## Workflows

- For availability, verify the requested station, dates, time in Asia/Tokyo,
  and vehicle before reporting options.
- For reservation review, use the member site's reservation list. Report only
  the dates, station, and vehicle relevant to the task.
- For a requested change, verify the current reservation and check for an
  existing matching booking. Prepare the proposed details on the official page
  and report the station, vehicle, date, times, extra options, and fees shown.
  Use the current task's specific authorization for any final submission.
- After an authorized submission, return to the reservation list and verify the
  result independently before reporting that the operation succeeded.

Capture reusable selector and navigation corrections through `skill_manage`.
Keep member numbers, credentials, codes, session data, and private reservation
records out of skill content. Use isolated synthetic data for workflow tests.
