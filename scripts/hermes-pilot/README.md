# Hermes B0 local candidate

This directory prepares the pinned v0.23.1 policy patch and an isolated USD10
text-inference budget gate. Nothing here installs Hermes, modifies a gateway,
connects Discord, creates supplier keys, or deploys to SpringMonkey.

## Refusal patch

`upstream-pins.json` binds two original files to commit
`3b421578588243f920886e6fe79a6faa87ea026e`. `refusal_patch.py` accepts only those
bytes and writes a new local candidate, patch and before/after manifest. The
prepared zero-context patch is under `patches/` and uses `git apply --unidiff-zero`.
A drifted source or existing output directory
is rejected. Apply only to the matching upstream commit during a future approved
image build, verify both original digests before applying and both resulting
digests afterwards, then assign a new local image digest. The official image's
old digest does not identify a patched candidate.

Content and provider-policy refusals stop at the shared fallback entry, including
enum and string reasons. The HTTP200 refusal handler preserves its terminal
result, history cleanup and accounting path. Availability failover is retained.
Tests execute the pinned functions with dependency doubles; they do not execute a
complete installed Hermes CLI/Gateway or prove every adapter's classification.

## Budget gate

The total pilot budget is **10,000,000 integer micro-USD**, equivalent to USD10.
It is shared across all sessions, retries, title/compression requests and the
three approved routes. There is no timer reset, public settlement/reset API,
automatic supplier retry, or extra budget per route. Only text Chat Completions
and local model discovery are exposed. Responses, native Anthropic, WebSocket,
batch, audio, images, provider search/OCR/file tools and unknown payload fields
are rejected. Local function-tool definitions are permitted; paid tool services
must remain disabled separately.

The admission reservation uses the entire **supplier-enforced input-context
ceiling**, including chat/tool/template tokens, and the requested capped output:

```
ceil((max_input_tokens * input_micro_usd_per_million
      + output_limit * output_micro_usd_per_million) / 1,000,000)
```

This deliberately avoids an approximate local tokenizer for unknown aliases.
It can stop early when the remaining budget cannot cover a full reservation.
The input/output rates must upper-bound every token category, cache tier, hidden
reasoning and time-of-day tier; the declared context/output limits must be
enforced by that exact upstream route. `price_confirmed` attests to all of this,
including absence of extra per-request/tool fees. A wrong attestation or a
supplier changing/ignoring its billing contract cannot be financially prevented
by this local software. Use a dedicated supplier key/cap as an additional boundary
when available; none has been created or changed in B0.

SQLite `BEGIN IMMEDIATE` serializes admission; at most one supplier request is
admitted at once. Reservations persist before dispatch. Valid usage settles at
the conservative rates. Missing usage, HTTP errors, timeout or incomplete streams
retain the entire reservation as committed cost. A process crash keeps the pending
reservation and prevents startup. Corrupt/missing DB, identity mismatch and stale
or unknown pricing all fail closed. Insufficient budget latches a stop for every
route. A reported usage/cost above the attested bound preserves the pending
reservation and requires operator review. Automatic recovery never grants credit.

The HTTP guard returns 402 when stopped. Hermes may try its other configured
routes, which the same stopped ledger rejects without forwarding. This prevents
further paid inference; it does not kill unrelated host processes or interrupt an
already dispatched supplier request. Such a request has already been reserved.

`pilot-budget.example.json` is deliberately **not startable**: gateway GPT/Qwen
prices/context ceilings are unverified. DeepSeek uses the documented peak
cache-miss/output rates and a conservative 1,048,576 input-token ceiling for the
documented 1M context. Its output cap is 4096; the preliminary reservation is
USD0.319488. Confirm the exact supplier cap when freezing an executable profile.
Zero/free prices are unsupported in this initial gate. Unknown costs are never
silently converted to zero.

The policy hash is bound to the ledger. Changing prices, model, identity or the
policy validity window cannot silently create another budget. An eventual policy
change requires explicit, reviewed state migration preserving prior cost; no such
migration is included in this initial candidate. Never delete/reinitialize the
ledger to resume this pilot. The real DB must live on a durable administrator-owned
volume, never a temporary container layer or a directory writable by Hermes.

Before any future runtime, all model and auxiliary clients must target this gate:

| Role | Future Hermes base URL | Upstream held only by gate |
| --- | --- | --- |
| GPT | `http://127.0.0.1:41000/gpt/v1` | user-specified HTTPS gateway |
| DeepSeek | `http://127.0.0.1:41000/deepseek/v1` | DeepSeek official HTTPS |
| Qwen | `http://127.0.0.1:41000/qwen/v1` | same HTTPS gateway as GPT |

The loopback addresses require a deliberately shared container network namespace
or equivalent approved private transport, with separate process/filesystem
namespaces. The gate alone receives real upstream keys and ledger/policy mounts;
Hermes receives only a distinct gate credential. No Docker socket or other paid
API keys are exposed to Hermes. Keep native auxiliary clients on the same approved
Chat Completions path. The actual namespace/mount/egress boundary and all full
Hermes adapters still require B1 verification; prompts alone are not isolation.

CLI actions are `validate`, explicit one-time `init`, read-only `status`, and
`serve`. Supply `--policy`; state actions also require `--ledger`. `serve` binds
only loopback port41000 and reads `HERMES_PILOT_GATE_TOKEN` plus the approved
upstream key environment references. There is no deployment script. Existing
provider credentials are not copied by these tools. Use new scoped pilot keys
before future deployment.

## Local verification

Use existing task Python dependencies from `requirements.txt`; no host install
has been performed. Tests also require pytest. The exact third-party source cache
is supplied explicitly, and missing cache fails rather than skipping policy tests.

```
python -m pytest scripts/hermes-pilot/tests -q -p no:cacheprovider --hermes-source=<verified-source-cache> --basetemp=<task-temporary-directory>
```

The suite covers the original-policy regression, real patch application, policy
refusals and availability errors, real local HTTP forwarding, auth/route/input
boundaries, atomic budget admission, exact USD10 exhaustion, all three routes,
retries/auxiliary calls, unknown cost, disconnect, timeout, corruption and restart.
All prices/keys in fixtures are synthetic. No fixture contacts a paid supplier.
The production template must fail validation until its missing attestations are
provided; that expected block does not mean the production pilot is ready.
