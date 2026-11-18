---
name: steamworks-reports
description: "Read the owner's Steamworks sales and financial reports, including Steam 销售报表, 财务报表, 销量, and 收入. Reuse the authorized Bot Screen session and open the native private Steam Guard prompt when needed."
---

# Steamworks sales and financial reports

Use the owner's authorized Bot Screen browser. For a request such as
“查一下 Steam 销售报表”, proceed with the report workflow.

1. Reuse the current signed-in session. Start from the Steamworks partner
   page at https://partner.steamgames.com/ and follow its **Sales & Activations
   Reports** link to the Valve reporting portal at
   https://partner.steampowered.com/.
2. If an official page requires a password, use the native `browser_vault`
   saved login for the exact current origin. Use its private login prompt if
   the owner must enter credentials. Check the active origin after redirects.
   Each portal may present its own sign-in or Steam Guard challenge.
3. When either portal shows the emailed Steam Guard challenge, call
   `browser_vault` with `action="enter_code"` and `target="browser"`, using the
   saved login handle for that origin when available. This opens the private
   prompt for the owner. Let the tool wait for the response. Never request
   a code in chat or copy it from email or browser output.
4. After the tool reports success, check whether Steam advanced automatically.
   If its same verified challenge still requires a submit action, submit it.
   Verify sign-in from the resulting page, then immediately continue the
   report lookup in the same turn. If the owner cancels, or the private prompt
   cannot open, explain the specific state and offer Bot Screen handoff.
5. Read the requested report for the requested application, date range, and
   currency. If no range was specified, identify the range shown in the report.
   Label gross and net amounts as the page does. This workflow reads existing
   data only. Changes to store, payment, pricing, or publishing settings are
   outside its scope.

Keep account identifiers, credentials, codes, browser session data, and private
report contents out of this skill. Record future verified navigation or field
semantics through the native skill management tool.
