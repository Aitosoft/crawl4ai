# Put the capacity gate in the 429 envelope

**Status:** open, ready to implement. **Size:** S (~30 production lines, ~75 test, ~35 doc).
**Written:** 2026-08-14, rewritten 2026-08-17 after the final sweep and MAS's `49-…`.
**Not gating anything.** No active campaign; MAS's request rate is near zero until the next one,
which makes this the right window for a revision change.

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
