# Put the capacity gate in the 429 envelope

**Status:** DONE — implemented and deployed 2026-08-17. **Size:** planned S (~30 production lines),
delivered S (+~100 production lines of which most are comment, +190 test).
**Written:** 2026-08-14, rewritten 2026-08-17 after the final sweep and MAS's `49-…`.
Implemented the same day by a separate session, which found four things wrong with it —
**the load-bearing one being that the invariant this whole feature is sold on was not
achievable as specified.** See "What the implementing session found" at the bottom; read that
before you trust anything above it.

---

## The concern

**Two completely different mechanisms in this service return HTTP 429, and from outside they are
indistinguishable.**

- **RenderGate** (`aitosoft_admission.py`) — per-replica concurrency admission. Refuses when
  `render_capacity` (2) renders are in flight and the queue of 4 is full or a waiter times out.
  **This is a capacity signal.** The fix for a high rate is more replicas or a lower trigger.
- **The pool's memory guard** (`crawler_pool.py:410-433`) — refuses to launch a new browser when
  `get_container_memory_percent()` reads ≥ `memory_threshold_percent` (85.0). **This is not a
  capacity signal at all**; it is a threshold crossing on a gauge whose median sits *above* its own
  trip point. The fix for a high rate is nothing.

Both raise `RenderCapacityExceeded`, and both therefore emit a byte-identical envelope:
`failure_class: "capacity"`, `Retry-After: 5`, HTTP 429 — differing only in the free text after
`Replica at render capacity:`.

**Consequence, and it is not hypothetical.** We handed MAS a stop-trigger for an unattended weekend
run phrased as "429s materially above ~4.5 %". They pointed out — correctly, in `45-…` §3 — that
they could not evaluate it, because **the two gates are one number on their side**. Taking it
literally would have aborted a healthy run at minute two. We conceded this in `46-…` §1. We had
*already* documented internally that a 429 count must be split before anything is read into it, and
wrote the ask anyway.

## The evidence, and why it is stronger now than when this was first written

**The split, measured across the whole final sweep** (186,178 requests, 2026-08-09 → 2026-08-16):

| | trigger 6 (122 h) | trigger 12 (54 h) | sweep |
|---|---:|---:|---:|
| `RenderGate REJECT` | 47 | 613 | **660** |
| `💥 Memory pressure` (the guard) | 5,391 | 4,485 | **9,876** |
| wire 429 | 5,434 | 5,098 | **10,532** |

`RenderGate REJECT + memory refusals = wire 429` holds **to the request** in the trigger-12 regime
(613 + 4,485 = 5,098) and is off by 4 at the regime boundary. So **~94 % of every 429 MAS has ever
received from us is the memory guard**, and the one they would reasonably read as "you are full" is
6 %.

**MAS reads our gauge out of the prose today, and it took them a fortnight to notice they could.**
`49-…` §1 is the argument for this task and it is better than anything in the original write-up.
Every memory refusal we send carries the reading verbatim:

```
HTTP 429: Replica at render capacity: memory at 90.2% (limit 85.0%), refusing new browser.
```

They eventually regexed 4,455 of those into a distribution and used it to separate two hypotheses a
rate could not. **Their extraction turned out to be a better instrument than our own logs** — our
janitor picks its sampling interval *from the reading it just took* (10 s above 80 %, 60 s below
60 %), so it oversamples high states; their samples are triggered by request arrivals and are
unbiased. Their p25/p50/p75/p95/max match our refusal log to one decimal.

**A structured field would have made their §1 a dashboard instead of a fortnight.**

## What to build, and the reasoning behind the shape

**An additive `capacity_gate` field, NOT a new `failure_class` value.** Both need identical
plumbing, so this is not an effort argument — it is a compatibility one:

- A new enum value breaks the two places that pin `capacity`
  (`test_failure_classification.py:317`, `AITOSOFT_CHANGES.md:1559`).
- It would **split MAS's own 429 baseline mid-programme.** They have counted `capacity` across
  several thousand events; keeping it as the stable total and adding a sibling field means their
  history stays comparable.

**Carry `memory_pct` and `limit_pct` alongside it.** This is the half `49-…` actually asked for, and
it is what turns their log from prose into data. Emit them only for the memory gate; absent for
RenderGate is meaningful.

**Always present, so absence means "old build".** That property is worth more than the field itself
— it is how MAS tells a stale image from a healthy one without asking us.

The value travels: `RenderCapacityExceeded` (`aitosoft_admission.py:71-74`) → raised at `:140` and
`:160`, and at `crawler_pool.py:431` and `:466` → caught by `_capacity_429` (`api.py:825-829`) and
its streaming twin (`:1278-1282`) → serialised in `server.py:540-547`.

**Note there are three raise sites in `crawler_pool.py`, not two**, and the third is worth
distinguishing: `:466` is the `max_browsers` cap (`🚧 Browser cap reached`), which fired **0 times
in 186,178 requests** — exactly as `config.yml:161-169` predicts. Give it its own gate value anyway;
a gate that never fires is a useful thing to be able to prove.

## The doc half of this item is already done

The original write-up bundled a fix for `DEPLOYMENT_INFO.md:484` ("a 429 means the render slots are
full" — a line that would send a session at `maxReplicas`, which was never the constraint). That
file is now `AZURE_OPERATIONS.md` and **§3.8 states the two-population split correctly**, so there
is nothing left to fold in. **What remains is the code change only.**

## What I am least sure of

**Whether MAS would rather have a response header than an envelope field.** A one-line
`X-Capacity-Gate` header is the true minimum and needs no `server.py` change at all. They asked for
the envelope (`45-…` §3) and we agreed to it in `46-…` §2, so the envelope is the commitment — but
if you get into `server.py` and the serialisation path is uglier than it looks from here, the header
is a defensible substitute. **Tell them if you switch; do not switch silently.**

**Whether `memory_pct` should be the raw reading or something more honest.** The raw reading is what
they already parse, so it is the compatible choice. But we now know that reading is cache-inclusive
and that its threshold sits below its own median — so shipping it as a clean structured field risks
dignifying a number we have publicly called uninformative. A `memory_pct` field *plus* a one-line
doc note that it is a working-set figure including active page cache is probably the honest
middle. Decide this deliberately rather than by default.

**Whether this is worth a revision change at all.** Honest sizing: our 429s cost MAS **29 captures
in 60,874 attempts (0.05 %)** across the whole sweep, and this task does not reduce that number by
one. Its value is entirely in *observability* and in discharging a commitment. That is a real but
modest justification, and if you find a reason it is more disruptive than it looks, saying "not
worth it, here is why" and telling MAS is a legitimate outcome.

---

## What the implementing session found (2026-08-17)

The diagnosis held: three render-path raise sites, one byte-identical envelope, ~94 % memory
guard. The *specification* did not. Four corrections, in descending order of how much they
mattered.

### 1. "Present on every 429" was not achievable as written, because there are four 429 mechanisms, not three

**`slowapi.errors.RateLimitExceeded` subclasses starlette's `HTTPException` with
`status_code=429`.** `/crawl` carries `@limiter.limit(...)` (`server.py:944`) and slowapi's own
handler is registered only by `Limiter.init_app`, which this app never calls — there is no
`app.state.limiter` and no `add_exception_handler(RateLimitExceeded, …)` anywhere in
`deploy/docker/`. So an inbound rate-limit breach lands in **our** `_http_exception_handler`
today and already emits `{"detail": "1000 per 1 minute", "failure_class": "capacity"}`. There is
a third non-render source too: the background-job quota at `api.py:82` (`/llm`, `/job`) — and
**that one is structurally dead, not merely quiet**: `config.yml:51` sets `per_principal: 0`, which
`work_queue.py:15` documents as "never 429". So `unspecified` rests on slowapi alone, which is
sufficient: it is live, and it is on `/crawl` itself.

Neither has ever fired. Note the inbound limit is **not** per caller as `config.yml` reads: slowapi
keys on `get_remote_address`, which behind the ACA ingress is the platform proxy, so 1000/min is
effectively per replica process — against a sweep average of ~18/min either way. But **the invariant MAS builds on is "an absent
`capacity_gate` means old build"**, and an invariant that is true 99.99 % of the time is one
somebody debugs at 03:00. Fixed at the *serialisation* point rather than the raise sites:
`envelope_extra_for` defaults any 429 with no attached fields to a fourth value,
`capacity_gate: "unspecified"`. That value is **not** in the `46-…` §2 contract — it is additive,
inert for MAS, and it is the one thing in this change they should be *told* rather than asked.

### 2. `_capacity_429` and "the stream twin" were duplicated code, not one shape with two callers

The task file's plumbing trace is accurate but reads as though the two sites shared a builder.
They did not — `/crawl` built the `HTTPException` inline inside `handle_crawl_request` and
`/crawl/stream` repeated the same four lines at `api.py:1278`. **A field added the obvious way
would have been present on one endpoint and missing on the other**, which is the precise failure
mode this feature exists to remove, one layer down. Collapsed into a module-level
`_capacity_http_exception(e)` — `+27/−11` in api.py, most of it the docstring.

### 3. `GATE_BROWSER_POOL` is correct to ship and is unobservable today — for a reason the file did not state

The file says "a gate that never fires is a useful thing to be able to prove". Agreed, and it
shipped. But the reason it has never fired is only half the pool-arithmetic comment at
`crawler_pool.py:454-458`. The other half: **from the five ungated endpoints where that refusal
*is* reachable — `/md`, `/html`, `/screenshot`, `/pdf`, `/execute_js` — it comes out as a 500, not
a 429**, because all five re-wrap every non-`HTTPException` into `HTTPException(500, …)`
(`api.py:440-445`, `server.py:666`, `:730`, `:765`, `:842`). That is the **2026-07-31
render-500-window regression still live outside `/crawl`**, three weeks after it was fixed there.

**Not fixed here, deliberately.** It is ~5 lines but a different change with a different blast
radius (it converts a 500 into a 429 on endpoints nobody calls), and MAS's traffic is 100 %
`/crawl`. It is written into the code comment at the raise site so the next reader does not have
to re-derive it. **If anyone does fix it, the gate value shipped here is what makes the result
countable.**

### 4. The wire vocabulary belongs in `aitosoft_failure_class.py`, not next to the exception

The plumbing trace implies the constants live with `RenderCapacityExceeded` in
`aitosoft_admission.py`. Putting them in `aitosoft_failure_class.py` instead means `server.py`
gains **no new import** (it already imports `envelope_class_for_status` from there), keeps the
repo's declared "single place a class becomes a wire status" true, and costs no circularity —
that module imports nothing of ours. Final `server.py` diff: **+7/−1, entirely inside the hunk
that was already Aitosoft's.**

### Two open questions from the file, both resolved without switching

- **Header vs envelope.** Envelope, no switch, nothing to tell MAS. The serialisation path turned
  out to be one line; and a header cannot carry `memory_pct`/`limit_pct` cleanly.
- **Raw reading vs something more honest.** Raw reading, **rounded to one decimal** — that is the
  precision of the `memory at 90.2% (limit 85.0%)` prose MAS has been regexing, so the structured
  field is directly comparable with the 4,455 readings they already hold. The honesty problem is
  real and is handled in prose, not by changing the number: `AZURE_OPERATIONS.md` §3.8 says what
  the reading is (cache-inclusive working set, threshold below its own median) and the addendum to
  `50-…` repeats it.

### The thing that should worry the next reader

**Every one of the 245 existing offline tests passed with the production change in place and
would have passed with it wrong.** No test constructed `RenderCapacityExceeded` with more than one
positional argument, and the two envelope-level tests assert only status + `Retry-After` +
`"memory" in detail`. That is the 2026-08-05 shape again — a suite that cannot see the layer it is
nominally covering.

So the new tests are deliberately placed on both sides of the seam: **five in
`test_mas_contract.py` assert the serialised body through the real exception handler** (api.py
builds it, server.py emits it — a field that is set and never emitted fails there), and **three
assert the label at the real raise sites** (`test_admission.py` ×2 through
`handle_crawl_request`, `test_crawler_pool.py` ×1 through `get_crawler`), because the contract
tests construct the exception themselves and would pass happily if `crawler_pool` mislabelled the
94 % population as the 6 % one.

A first pass got this half-wrong in an instructive way: it asserted the `render_slots` label at
`RenderGate`'s **queue-full** raise site only, and `RenderGate` has **two** — the wait-timeout
branch is separately live in production and deleting *its* `gate=` kwarg left the entire suite
green. Caught by the post-implementation review, not by the tests.

**Mutation-checked twice, not assumed:** deleting the one-line merge in `server.py` fails 4 of the
5 contract tests and leaves the negative test green; dropping the wait-timeout label fails exactly
the test written for it. **318/318** offline and browser tests pass (312 before this change).
