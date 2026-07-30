# Stop laundering origin failures into crawl4ai 5xx — failure classification

**Status:** DRAFT — blocked on MAS's answer to Q2 (`tasks/waa-eval-2026-07-30-forensics.md` §7).
Do not implement the wire-format change until that answer is in. The
*diagnosis* below is settled; only the contract is open.
**Priority:** High. Currently a broken customer website is indistinguishable
from a broken crawler, and MAS's retry policy amplifies it.
**Effort:** M. **Risk:** medium — changes status codes MAS branches on.
**Evidence:** `tasks/waa-eval-2026-07-30-forensics.md` §3, §2a

## Problem

We report *their* failures as *our* failures, with a status code that tells the
client to try again.

`anitamakela.com` serves a genuine `HTTP 500` with a zero-byte body from its own
Apache. Chromium will not render it, `Page.goto` raises
`net::ERR_HTTP_RESPONSE_CODE_FAILURE`, upstream wraps it as
`RuntimeError("Failed on navigating ACS-GOTO: …")` and re-raises it
(`async_webcrawler.py` ~543, when there is one proxy and `max_retries <= 1`),
and `api.py`'s generic `except Exception` turns it into **HTTP 500 from us**.

Prod, 2026-07-27, one host, 35 seconds: **eight** `server error 500` lines. MAS
treats 500 as retryable (3 retries, 1/2/4 s), so a site that is simply down
costs four requests per page and is recorded as a crawler fault. This is
near-certainly the "konecranes HTTP 500" MAS logged in April and July.

The same category error runs through the whole surface:

| Reality | What MAS currently sees | Should be |
|---|---|---|
| origin returns 5xx / unrenderable error | **HTTP 500** (retryable) | not-our-fault, terminal, with the origin's status |
| origin edge-blocks our IP (Fastly 403) | HTTP 200 + `success:false`, or 500 | not-our-fault, terminal, `origin_blocked` |
| origin redirects then blocks | **HTTP 200 + `success:true`** + block page | see `tasks/redirect-status-blinds-block-detection.md` |
| our render genuinely overran | HTTP 504 | ours, retry may help after a fix |
| replica at capacity | HTTP 429 + Retry-After | ours, retry with backoff ✅ (already correct) |

Only the last row is honest today.

## Direction

Introduce an explicit, machine-readable failure taxonomy on the result, and
stop using 5xx for anything the origin did.

Proposed `failure_class` values (final naming to be agreed with MAS):

- `origin_http_error` — origin returned 4xx/5xx; carry its real status
- `origin_blocked` — anti-bot / WAF / edge block (fingerprint or reputation)
- `origin_unreachable` — DNS / TCP / TLS failure reaching the origin
- `render_timeout` — our wall-clock fence fired
- `render_error` — our browser/pipeline broke (a genuine 500 on our side)
- `capacity` — admission gate rejected (429)

Transport mapping — **this is Q2 to MAS**. The option I recommend:

> Anything the origin caused ⇒ **HTTP 200**, `success: false`,
> `failure_class`, `status_code` = the origin's real final status.
> Only our own faults keep 5xx (`render_error` → 500, `render_timeout` → 504),
> and `capacity` keeps 429 + Retry-After.

Rationale: it matches what static mode already does (network failures never
raise; they become `success=false` inside a 200 — `aitosoft_static_mode.py`
docstring), it makes MAS's retry policy correct by construction (200 is never
retried; 5xx/429 always are and are always genuinely ours), and it removes the
"is this us or them?" question from every future incident.

The alternative MAS may prefer is a distinct upstream-error status (502) so
their existing status-code branching keeps working. Both are implementable;
pick one and pin it in `test-aitosoft/test_mas_contract.py`.

## Implementation notes

- Classification belongs in `api.py` around the existing
  `except asyncio.TimeoutError` / `except Exception` blocks, plus a pass over
  per-result `error_message` before the response is built.
- The `ACS-GOTO` wrapper text and the `net::ERR_*` code are the signal for
  `origin_http_error` / `origin_unreachable`. Parse them once, in one place —
  do not scatter string matching.
- `redirected_status_code` is the authoritative origin status once
  `tasks/redirect-status-blinds-block-detection.md` lands. Sequence that task
  first; this one depends on it being right.
- Keep `error_message` human-readable and unchanged in spirit — MAS reads it in
  logs. `failure_class` is the machine field.
- Whatever is chosen must be pinned by `test-aitosoft/test_mas_contract.py`,
  which is the offline contract gate.

## Related

`tasks/antibot-minimal-text-false-positive.md` is the same family: a legitimately
tiny page is classified as a block and surfaces as a 500. A correct taxonomy
plus a `blocked_suspect` flag would resolve both. Consider merging the two once
Q2 is answered.
