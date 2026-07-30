# Stop laundering origin failures into crawl4ai 5xx — failure classification

**Status:** UNBLOCKED 2026-07-30 — MAS answered Q2 **(a), unreservedly**. Ready
to implement, and it is now the **deploy gate**: the redirect fix is already
committed, so the next deploy carries it, and shipping that without this one
moves redirect-blocked hosts from a wrong-but-parseable 200 to an opaque,
retried 500. Both must land in the same image.
**Priority:** HIGHEST of the remaining batch (raised 2026-07-30). Currently a
broken customer website is indistinguishable from a broken crawler, and MAS's
retry policy amplifies it — and the redirect fix that shipped 2026-07-30 moved
more hosts into that class. See "Sharper statement of the problem" below.
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

## Sharper statement of the problem (added 2026-07-30, verified in code + live)

The `except Exception` path in api.py is not the main channel. The main channel
is upstream's own all-failed rule plus our security handler:

```python
# deploy/docker/server.py:940
if all(not result["success"] for result in results["results"]):
    raise HTTPException(500, f"Crawl request failed: {results['results'][0]['error_message']}")
```
```python
# deploy/docker/server.py:517-528  — 5xx detail is stripped for security
if exc.status_code == 500:
    return JSONResponse({"error": "Internal server error", "correlation_id": cid}, 500)
```

**Under the single-URL contract these compose into: every full-mode failure,
whatever its cause, reaches MAS as an opaque HTTP 500.** No `status_code`, no
`redirected_status_code`, no `error_message`, no `crawl_stats`. Verified
end-to-end 2026-07-30 against a fixture origin: a 403 block page, a wedged
render and an origin 5xx are byte-identical on the wire.

Two consequences that change how this task should be framed:

1. **The "konecranes HTTP 500" is this path, not §3's.** Block detected →
   `success:false` → 500 → genericized. §3's ACS-GOTO mechanism is real but is
   `anitamakela.com`'s. Both land in the same opaque response.
2. **`tasks/redirect-status-blinds-block-detection.md` (shipped 2026-07-30)
   enlarged this population** — every redirect-to-block host joins it. That was
   accepted deliberately: the alternative was leaving block pages in MAS's
   corpus as content. But it raises this task's priority, and it means MAS's
   client-side `redirected_status_code >= 400` mitigation stops being available
   for exactly those hosts once we deploy.

Static mode already has the right shape and is the reference implementation:
`aitosoft_static_mode.py` computes `success = 200 <= status < 400` from the
final hop and never raises, so the same host returns HTTP 200 + `success:false`
+ the real `status_code`. **Full mode is the only path that turns a perfectly
well-understood finding into an unattributable 500.**

Minimum viable version if Q2 stays unanswered: at `server.py:940`, return the
envelope with `success:false` instead of raising, whenever the result carries a
real origin `status_code`/`redirected_status_code` (i.e. we reached the origin
and it answered). Keep 500 for the no-status cases (navigation failure, browser
crash, budget exhausted). That is one branch, no new vocabulary, and it does not
pre-empt the `failure_class` naming.

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

Transport mapping — **SETTLED. MAS chose (a), our recommendation, unreservedly:**

> Anything the origin caused ⇒ **HTTP 200**, `success: false`,
> `failure_class`, `status_code` = the origin's real final status.
> Only our own faults keep 5xx (`render_error` → 500, `render_timeout` → 504),
> and `capacity` keeps 429 + Retry-After.

**Placement, as MAS specified:** `failure_class` at the **result level, present
on every result including successes** (`null` or `"none"`), so a missing field
never needs interpretation. Envelope level *additionally* for request-scoped
failures only — capacity, auth, malformed request — where there is no result to
attach it to. Both, with that division of labour rather than duplication.

**They explicitly rejected (b):** *"A distinct 502 would preserve our existing
branching, but it preserves the wrong branching: it keeps 'is this retryable?'
as a thing we infer from a status code you had to overload."*

**Also required by this task (MAS asked):** document `redirected_status_code` in
the response contract. It is absent from their `CrawlResult` interface
(`crawl4ai-client.ts:33-56`) — they found it in our reply, not in a contract.

Rationale: it matches what static mode already does (network failures never
raise; they become `success=false` inside a 200 — `aitosoft_static_mode.py`
docstring), it makes MAS's retry policy correct by construction (200 is never
retried; 5xx/429 always are and are always genuinely ours), and it removes the
"is this us or them?" question from every future incident.

Pin the chosen shape in `test-aitosoft/test_mas_contract.py`.

**The `server.py:940` branch is the crux.** Today `if all(not result["success"] …)`
raises `HTTPException(500, …)`, and the security handler at `server.py:517-528`
genericizes it to `{"error": "Internal server error", "correlation_id": …}` —
stripping `status_code`, `redirected_status_code`, `error_message` and
`crawl_stats`. Under the single-URL contract that fires on *every* full-mode
failure. Return the envelope when we have a real origin status; keep 500 only
for `render_error`.

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
plus a `blocked_suspect` flag would resolve both. Q2 is now answered — decide
whether to merge them as part of this work.

`tasks/antibot-detector-challenge-blindspot.md` matters here too: `origin_blocked`
is only as accurate as the detector, which MAS measured as missing ~370 of ~400
challenge pages in their corpus.

---

## Implemented 2026-07-30 — this was the deploy gate

**New file:** `deploy/docker/aitosoft_failure_class.py` — the vocabulary, all
error-text matching, and the transport mapping, in one place. Nothing else in
the codebase matches on `net::ERR_*` or on the ACS-GOTO wrapper text.

### The crux — `server.py`'s all-failed branch

```python
_status = http_status_for(r.get("failure_class") for r in results["results"])
if _status == 200: return JSONResponse(results)     # origin's fault: full envelope
if _status == 504: raise HTTPException(504, ...)    # ours: fence fired
raise HTTPException(500, ...)                       # ours: render broke
```

Under the single-URL contract this branch fired on *every* full-mode failure and
the security handler then replaced the body with
`{"error": "Internal server error"}`. `status_code`, `redirected_status_code`,
`error_message` and `crawl_stats` all reached MAS as nothing.

### The second channel — `api.py`'s `except Exception`

Upstream re-raises a navigation failure when there is a single proxy and
`max_retries <= 1`, so `anitamakela.com`'s zero-byte Apache 500 arrived as an
exception rather than a result and became our 500 (8 client retries in 35 s).
That path now classifies the exception and, when the origin owns it, returns the
same envelope shape a failed result would have.

### Contract, as MAS specified it

| | |
|---|---|
| `failure_class` | on **every** result including successes (`"none"`), so a missing field means an old build, never a success |
| envelope `failure_class` | only where no result exists — `capacity` (429), `auth` (401/403), `bad_request` (400), plus `render_error`/`render_timeout` on our 5xx |
| origin-caused | HTTP 200 + result `success:false` — `origin_http_error`, `origin_blocked`, `origin_unreachable` |
| ours | 500 `render_error`, 504 `render_timeout` |
| capacity | 429 + Retry-After, unchanged |

**`status_code` now carries the origin's real FINAL status** — the last redirect
hop — which is what MAS asked for and what static mode has always reported under
that name. Full mode reported the *first* hop, so an apex→www redirect to a 403
block page was labelled 301. `redirected_status_code` is untouched, so MAS's
client-side `redirected_status_code >= 400` mitigation keeps working through the
transition, and it is now part of the documented contract as they requested.

Static mode carries `failure_class` too, so both render modes parse identically.

### Classification bias — deliberate, and stated

Unrecognised failures classify as `render_error` (ours, 500, retryable), never
as an origin class, and an unknown `net::ERR_*` logs a breadcrumb so the table
grows from evidence. Wrong in that direction costs wasted renders and is loud;
wrong the other way tells MAS a healthy company site is permanently broken,
silently — the failure mode they called the most expensive thing that happened
to them this month.

### Verified

- `test-aitosoft/test_failure_classification.py` — 33 tests: the three real
  incidents (anitamakela ACS-GOTO, konecranes block, konecranes redirect chain),
  the `net::ERR_*` table, unknown-error bias, timeouts staying ours, the
  `Page.content` race staying ours, `"none"` on success, the full transport
  matrix, and two end-to-end runs through `api.handle_crawl_request`.
- `test-aitosoft/test_mas_contract.py` — two new tests drive the **real app**
  through `TestClient` including the security exception handler: an origin block
  returns 200 with `status_code`/`redirected_status_code`/`error_message`
  intact; our own crash still returns 500 carrying envelope
  `failure_class: render_error`.
- Full offline gate: **126/126**.

### One open question for MAS

Envelope `success` stays `true` when the single result failed, matching static
mode exactly ("the request was processed"; the result carries the outcome). Our
own monitor already treats an all-failed batch as a failure, so the envelope is
the last place still saying "green". Left alone deliberately — static mode is
the shape they are adopting *right now* as a pre-delete gate, and flipping it
under them mid-adoption is the kind of change that should be asked for, not
shipped. Ask whether they want envelope `success` to become the aggregate; it is
a one-line change in both paths once they answer.
