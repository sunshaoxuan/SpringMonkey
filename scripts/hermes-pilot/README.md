# Hermes pinned refusal patch

Only the hash-bound refusal policy candidate remains active in this directory.
The user withdrew fee reservation, the USD10 budget gate and pricing prerequisites.
No budget service, price template or budget dependency remains. Existing upstream
model APIs will be used directly in a future authorized deployment.

`upstream-pins.json` binds two files to Hermes v0.23.1 commit
`3b421578588243f920886e6fe79a6faa87ea026e`. `refusal_patch.py` checks those bytes
and prepares a new local candidate, patch and before/after manifest. The reviewed
patch is under `patches/`; apply it with `git apply --unidiff-zero` only after
matching the original commit and digests, then verify the resulting digests.
An existing output directory or changed original is rejected.

Content and provider-policy refusals stay terminal. Availability fallback remains
enabled. The HTTP200 handler preserves the original terminal response, history
cleanup and accounting path. Tests execute the pinned functions with isolated
dependency doubles and verify real patch application; full Hermes adapter/runtime
acceptance remains a future deployment check.

The 12 existing policy/patch regression results remain valid because these files
and their direct inputs were unchanged by withdrawing the budget implementation.
Nothing here deploys Hermes, changes authentication, or connects Discord.

Local regression command when implementation inputs change:

```
python -m pytest scripts/hermes-pilot/tests -q -p no:cacheprovider --hermes-source=<verified-source-cache> --basetemp=<task-temporary-directory>
```
