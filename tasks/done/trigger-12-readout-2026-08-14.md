# The trigger change worked, it overshot its own prediction by 3×, and the fleet is now effectively inelastic

**Status:** readout, closed. Written 2026-08-14 ~17:40 UTC, between MAS's bounded
30-minute run and their resumed weekend sweep.
**Reads:** `tmp/mas-repo-messages/44-to-mas-…` (our ask) and `45-from-us-…`
(their answer). **Amends:** `tasks/crawl-cost-is-idle-replicas-not-slow-renders.md`
(abort rule + two predictions), `tasks/memory-guard-charges-reclaimable-page-cache.md`
(its headroom argument does not survive 2 replicas), `CLAUDE.md` (`utils.py` row).
**Decision it produced:** **continue the weekend sweep unchanged. Deploy nothing.**

---

## 0. The four lines

1. **ACA scale trigger 6 → 12 (revision `--0000042`, live 2026-08-14T15:59:42Z)
   took the fleet from ~12 replicas to a flat 2** on the same workload.
   Render-slot utilisation **7.0 % → 54 %**. Cost **~€89/day → ~€15/day**.
2. **It overshot.** The file predicted "½ × replicas" (~6, ~€44/day). It
   delivered 6×. The loop is *contractive*, not linearly scaled — §3.
3. **Nothing broke.** p50 +7 %, p99 **−28 %**, throughput and success rate
   unchanged, 0 OOM kills, 0 render defects, largest response 3.42 MB.
4. **The fleet is now effectively inelastic**, and the two arguments that chose
   the trigger *over* a `maxReplicas` cap are both refuted by this run — §5. The
   outcome is still good; the reasoning that picked it was not load-bearing.

---

## 1. The matched before/after

Two windows of the same length at nearly the same arrival rate, both real MAS
traffic, `ContainerAppHTTPLogs` + `ContainerAppConsoleLogs_CL`:

| | **before** 08-12 10:00–10:32 | **after** 08-14 16:28–17:00 |
|---|---|---|
| trigger / fleet | 6 / **~12 replicas** | 12 / **2 replicas, flat** |
| requests, rate | 731, 22.8/min | 632, 20.9/min |
| true concurrency (Σ`RequestDuration`/window) | 2.08 | 2.16 |
| render slots held | 24 | **4** |
| **slot utilisation** | **8.7 %** | **54 %** |
| p50 | 4,836 ms | 5,179 ms (**+7.1 %**) |
| p90 | 6,929 ms | 10,554 ms (+52 %) |
| **p99** | 31,684 ms | **22,966 ms (−28 %)** |
| 429 (all) | 39 (5.3 %) | 41 (6.5 %) |
| 500 | 0 | 4 (one host, §6) |
| admits that waited at all | **0.82 %** | **31.05 %** |
| mean admission wait | 0.023 s | **1.127 s** (p90 4.1, max 13, limit 15) |
| mean `in_use` at admit | 1.10 / 2 | 1.63 / 2 |

**Cost.** €0.303/replica-hour, derived from the invoice reconciliation in the
cost file (€374.54 ÷ 1,235 replica-h, itself within 2.1 % of the billed vCPU-second
meter). 12.22 replicas = **€88.9/day**; 2 replicas = **€14.5/day**. The weekend
sweep costs roughly **€30 instead of €178**.

### The 429 split reconciles exactly, from both sides

Ours, from the console: **31** `refusing new browser` + **7** `RenderGate REJECT
(queue full)` + **3** `RenderGate REJECT (wait timeout 15s)` = **41**, which is
the ingress 429 count to the request. MAS independently reported **31 / 7 / 3**.
Two instruments, two repos, no disagreement.

**Capacity-gate 429s rose 23× (0.078 → 1.818 per 100 successful fetches) and the
memory guard did not move (49.1 per 1,000, inside the 40–63 band).** That is the
correct shape: shrinking the fleet is *supposed* to press on the capacity gate
and leave the memory gate alone.

---

## 2. The thing nobody predicted: a small fleet is *more* efficient per request

Same window lengths, same instrument:

| | before, 12 replicas | after, 2 replicas |
|---|---|---|
| admits | 729 | 612 |
| **browser launches** | **269** | **81** |
| launches per admit | **0.369** | **0.132** |
| hot-pool hits | 194 (26.6 %) | **370 (60.5 %)** |
| LRU evictions | 65 | 70 |
| fleet CPU (`UsageNanoCores`) | 0.287 cores/replica ⇒ **3.44 cores** | 0.775 ⇒ **1.55 cores** |

**2.8× fewer Chromium launches and 2.3× the pool hit rate, for the same work.**
MAS sends a per-company browser identity, so each company is a distinct pool
signature; with 12 replicas a company's ~7 pages scatter round-robin and each
replica pays its own cold launch. With 2 they mostly do not.

This is §4 of `crawl-cost-is-idle-replicas-not-slow-renders.md` — *"the
over-provisioning manufactures its own load"* — **running in reverse, and it is
the first direct measurement of that loop in either direction.** It also explains
the p99 improvement and MAS's observation that their steady-state buckets
(4,405–4,676 ms) came in *faster* than their pre-change p50 of 4,840 ms. Total
fleet CPU **halved**.

---

## 3. Why it overshot: the trigger crossed a threshold, it did not scale a knob

The cost file's downstream-connection model (≈65 open connections held ~300 s,
independent of fleet size) predicts `ceil(65/12)` = **6 replicas** at trigger 12.
**We observed 2. That model is refuted at the new operating point** — no single
idle-hold constant produces 12 replicas at trigger 6 *and* 2 at trigger 12 from a
fleet-independent connection count.

What survives is the *upstream* variant the file raises but does not fit: the
metric tracks Envoy→replica connections, which is ≈ (peak concurrency routed to a
replica) × replicas. A replica holds at most `render_capacity 2 + admission_queue
4 = 6` before it starts rejecting, so:

| trigger | metric ÷ trigger | behaviour |
|---|---|---|
| 2 | 3 × replicas | runaway to the cap — matches the observed 38 |
| **6** | 1 × replicas | **neutral — fleet keeps whatever a burst gave it, never drains** |
| **≥ 7** | < 1 × replicas | **contractive — drains to the demand floor** |

**The corollary matters more than the mechanism: 12 is not a tuned value, it is
just "above 6".** Anything ≥ 7 lands in the same place. And **6 was the worst
possible setting** — it sat exactly on the neutral point, which is why the fleet
size was set by history rather than load, and why slot utilisation was 7.0 % on
*every* day of the sweep to one decimal.

### The probe: neither request rate nor queue pressure moves the fleet

`sustained_rate_probe.py --label surge-trigger12 --rate-per-min 30 --fanout 4
--duration-min 12 --keepalive-expiry 300`, `raw://`, zero egress, 17:21–17:35 UTC
while MAS was stopped. The probe writes
`test-aitosoft/sustained_<label>_<ts>.json` (360 per-request rows); **it is not
committed** — no `sustained_*.json` ever has been, and `test-aitosoft/artifacts/*`
is gitignored (open item 4). Everything load-bearing is in the table below, and
the command above reproduces it at zero egress.

**1.44× MAS's arrival rate. The fleet stayed at 1 replica for all 12 minutes.**

| | |
|---|---|
| requests | 360 (322 × 200, **38 × 429**, all `failure_class: capacity`) |
| 429 rate | **10.6 %** |
| client p50 / p90 / p99 / max | 9.28 / 12.77 / 14.36 / 17.85 s (render target ~5 s) |
| mean concurrency | 4.22 |
| server-side admission wait | mean **5.26 s**, p50 5.0, p90 8.8, max 10.3 (limit 15) |
| replica count, minute by minute | **1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1** |

One replica queued for as long as it rendered, rejected 38 requests, and the
scaler added nothing for twelve minutes.

**⛔ Read this narrowly — and narrower than I first wrote it.** The obvious
reading, "the scaler ignores queue pressure", is **not supported**, because this
arm held its TCP connections constant: pooled httpx with a 300 s expiry means
~4 connections total, and the 38 rejections rode the same 4. If the metric is
connections, a flat fleet is exactly what this arm *should* produce, rejections
or not. It is also **not** a clean A/B against the trigger-6 arm (11 replicas at
19 req/min, 15:35–15:57), which ran httpx's 5 s default expiry ⇒ effectively one
connection per request. **Two variables moved. Do not quote it as a trigger A/B.**

What it does establish: **arrival rate alone does not move the fleet at trigger
12** — 30 req/min on one replica, versus MAS's 20.9 req/min on two. Whatever the
input is, it is not requests per second and it is not render occupancy.

**And the sharp consequence, which points the opposite way from the rest of this
file.** If MAS's connection churn (~0.65 new connections per request) is what
sizes our fleet, then their elasticity is intact — their fleet grows when their
load grows, at roughly a sixth the old gain, which is what we want. But it also
means **the client-side fix we have been contemplating asking them for would
remove our scale-up entirely**, leaving us pinned at 1. If that ask is ever made,
the trigger must come back down in the same change. Nobody had noticed that these
two levers fight.

**The clean third arm was designed and deliberately not run** — same rate, same
trigger, `--no-keepalive` — because it now decides ~€7/day, not €75/day. The
cheap lever already deleted 85 % of the problem, and the mechanism question is
worth what is left, not what it was worth this morning. Command is in §8.

---

## 4. Memory: unchanged in rate, materially thinner in margin

237 `📊 Pool:` samples across the two replicas, 16:28–17:00:

| | guard's reading `mem=` | true `anon` |
|---|---|---|
| p05 | 73.8 % | 57.8 % |
| **p50** | **84.0 %** | **68.8 %** |
| p95 | 94.0 % | 75.2 % |
| **max** | **97.7 %** | **84.4 %** |

Active file cache (`file − inactive_file`) reached **999 MB**, and only
`inactive_file` is subtracted (`utils.py:498-501`).

Two readings taken 3 seconds apart, same replica:

```
16:40:17  Pool: hot=5, cold=1, resident=6/6, mem=75.6%, anon=2941MB
16:40:20  Memory pressure: 89.4% >= 85.0% (anon=2819MB) — refusing new browser
```

**The reading moved 13.8 points while `anon` moved −4 %.** So the sharpest
statement of the defect is not "the guard is ~14 points high" — it is that
**the guard's median reading (84.0 %) sits on its own threshold (85 %), and the
noise on its input is larger than its distance to the trip point.** Refusals are
sampling noise, not a memory event. 0 of 31 refusals had `anon` ≥ 85 %.

**⛔ And this is the part that changes the memory task file's recommendation.**
That file argues from ~1.25 GB of headroom, measured at ~12 replicas where `anon`
p50 was 68.6 %. At 2 replicas the fleet **peak** `anon` is **3,455 MB = 84.35 %**
— **0.65 percentage points, 27 MB, below an 85 % threshold read on `anon`
directly.** A metric-only fix would still have refused zero times tonight, by a
rounding error. One measured browser is 143–170 MB on ordinary pages and ~434 MB
at the production slope; `render_capacity: 2` permits two launches in flight
against one meter reading.

**So the metric fix now needs a companion bound** (`max_browsers` 6 → 4, or a
threshold on `anon` well under 85), and neither that file nor `config.yml`
evaluates `max_browsers` as a *companion* — both only reject it as a competing
fix for the refusals, which it correctly loses. **Do not ship the metric fix
alone.**

### The long-replica worry, checked and closed

Trigger 12 pins the fleet, so replicas now live for the whole sweep. That was
named as the reason *not* to cap `maxReplicas`. It is fine, for two measured
reasons:

- **It was never new.** During the 08-11 → 08-14 sweep at trigger 6, three
  replicas lived **40.3–42.6 hours**. `anon` vs replica age across that sweep:
  p50 2,485 MB at age 0–4 h → 2,804 MB at 40 h (**+319 MB over 40 h**); p95 flat
  at 3,100–3,235; max flat. No ratchet.
- **Browsers cannot ratchet, because they do not survive.** 70 evictions in 32
  minutes over 6 slots ⇒ each pool slot turns over about every **2.7 minutes**.
  A browser's memory floor is the heaviest page it ever loaded, and only closing
  it resets that — the pool is closing them constantly.

Zero OOM kills, zero exit 137, ever. The blast radius did change, though: an OOM
kill now removes **50 %** of the fleet instead of 8 %.

---

## 5. Two arguments that chose this option, and both are refuted by it

`crawl-cost-is-idle-replicas-not-slow-renders.md` picked trigger 12 over
`maxReplicas: 4-6` at equal cost. Four reasons were given; **the two that did the
work do not survive**:

- **"Elasticity matters *because* this is an unattended multi-day run. A cap of 4
  has no response to a surprise; trigger 12 still has 20 replicas behind it."**
  The fleet performed **one** scale-up event in 30 minutes of real load and then
  held flat at 2 through ten RenderGate rejections; the synthetic arm held 1
  replica through six minutes of 5 s queue waits. The 20 replicas behind it are
  nominal. **We bought the cap's behaviour while arguing we were not.**
- **"A cap turns 30-minute replicas into 3-day replicas with no memory reset."**
  Trigger 12 does exactly that. §4 shows it is harmless, but that was not known
  when the argument was made — and the same evidence would have exonerated the
  cap.

The two reasons that *do* survive are the ones that were about evidence, not
mechanism: the trigger is the only lever ever run against production, and it is
self-correcting in the direction that matters (a smaller fleet that lengthens
requests raises the metric).

**The lesson is not "we chose wrong" — the outcome is good and cheaper than the
prediction.** It is that **both options were the same intervention wearing
different clothes**, and the discriminating arguments were about a mechanism
neither of us could observe. When two options are argued apart on an unobservable,
expect to have chosen arbitrarily.

---

## 6. The four 500s are one host and one known family

All four are `https://www.koodikarhu.fi`, 16:53–16:55, `failure_class=render_error`
at HTTP 500, each ~22 s. The origin serves **1,069 bytes with 14 characters of
visible text**; tier-3 structural inference (`minimal_text on small page`) calls
that blocked, the patchright leg re-fetches and agrees, and 500 is retried by
MAS's ladder — 4 attempts × 2 renders ≈ 88 s of a 4-slot fleet for one company.

Not a regression and not capacity: the same class ran at 1.1 % of requests
(118 / 10,537) during the previous sweep and 0.63 % tonight. It is the
`pdf-inline` family one row over — *inference*, not evidence, deciding
`render_error`. Worth pricing later precisely because a smaller fleet makes each
retry storm a larger share of it. Not tonight.

Everything else in the window: `origin_unreachable` 16 (MAS drew their
never-scraped prospect pool, ~20 % dead hosts — expected), `origin_blocked` 2,
0 render defects, 0 collapse recoveries, 0 fence-504s.

---

## 7. What was decided, and what was deliberately not done

**Continue the weekend sweep unchanged. Deploy nothing.** Every measured axis is
neutral or better; the two axes that worsened (queue wait, memory margin) are
bounded and self-limiting; and a deploy means a revision transition plus an
unreviewed change entering an unattended run. `test-aitosoft` has one prior case
of a fix that passed 229 offline + 54 browser + 316 upstream tests and a green CI
run and still broke production, because every test patched the layer above the
broken line.

**Not done, with reasons:**

| considered | verdict |
|---|---|
| revert trigger to 6 | **no** — 6 is the neutral point, the worst available value |
| lower trigger further (16, 20) | **no** — nothing above ~7 changes the outcome; §3 |
| `maxReplicas` 20 → smaller | **no** — saves €0, still correct as tail protection |
| `minReplicas: 0 → 1` | **no** — €7.3/day is half the new bill to remove an 11.5 s cold start that occurs at gaps only |
| `admission_queue` 4 → 8 | **no** — trades 7 fast 429s for up to 15 s of queue; MAS's ladder absorbs 429s |
| memory-guard metric fix | **no, and now harder** — §4: needs a companion bound first |
| `max_browsers` 6 → 4 | **not now** — but it is the metric fix's *companion*, not its rival |
| gunicorn `--keep-alive 300` → short | **not now** — worth ~€7/day post-fix, and it is a deploy |
| the third probe arm (`--no-keepalive`) | **not run** — §3; it decides €7/day now, not €75 |
| the gate in the envelope (MAS's ask) | **yes, after the sweep** — §8 |

---

## 8. Next, in order

1. **Monitor the weekend** via `OVERNIGHT_PLAYBOOK.md`. Split every 429 by token
   before reading anything into it. Escalate on `anon=` ≥ 85 % in the guard line
   (not the percentage), `Reason_s == "OOMKilled"`, exit 137, or a sustained
   `RenderGate REJECT` rate above ~3 % of requests.
2. **Ship `capacity_gate` in the 429 envelope** (MAS `45-…` §3). Scoped: an
   additive field, **not** a new `failure_class` value — both need identical
   plumbing, but a new enum value additionally breaks the two places that pin
   `capacity` (`test_failure_classification.py:317`, `AITOSOFT_CHANGES.md:1559`)
   and splits MAS's own 1,953-429 baseline mid-programme, while a sibling field
   keeps `capacity` as the stable total. `gate` on `RenderCapacityExceeded`
   (`aitosoft_admission.py:71-74`), passed at `:140`, `:160` and
   `crawler_pool.py:431,466`, attached in `_capacity_429` (`api.py:825-829`) and
   its stream twin (`api.py:1278-1282`), emitted in `server.py:540-547`. ~30
   production lines. `DEPLOYMENT_INFO.md:484` is **actively wrong today** ("429 +
   Retry-After means the replica's render slots are full" — ~99 % are the memory
   guard) and must go in the same change.
3. **Then** the memory-guard metric fix **with** its companion bound (§4).
4. **Only if the remaining ~€7/day is worth a deploy**, the connection arm:
   `python sustained_rate_probe.py --label conn-b --rate-per-min 30 --fanout 4
   --duration-min 12 --no-keepalive`, compared against tonight's
   `surge-trigger12`. Same trigger, same rate, same shape; only downstream
   connection reuse differs.

---

## 9. What I am least sure of

- **The contractive-loop model in §3 is a fit with one free parameter, same as
  the model it replaces.** It explains four observations (runaway at 2, park at
  6, drain at 12, the 7.0 % constant) with one number, and no ACA metric exposes
  the scaler's input, so it is unfalsifiable from here. **The operational claim
  does not depend on it** — the fleet is 2 and 54 %-utilised whatever the reason.
  Do not let the model do work the measurement can do.
- **"Anything ≥ 7 lands in the same place" is an inference, not a measurement.**
  We have run 2, 6 and 12. Nothing was run at 7–11.
- **The elasticity conclusion is drawn from one 30-minute window and one
  confounded probe.** If MAS's rate rises materially, their connection count
  rises with it, and the fleet may grow after all. I would not bet either way
  above ~40 req/min.
- **The 2-replica regime has 30 minutes of characterisation.** `anon` peak
  84.4 % is one datapoint from one window; the age-vs-`anon` curve behind §4's
  "no ratchet" was measured at **one sixth** the per-replica request rate, and
  the eviction argument is what actually carries it.
- **The browser-efficiency result (§2) has one before-window and one
  after-window.** It is large (2.8×) and mechanistically obvious, but n=2
  windows. It should be re-counted over the weekend, where it is nearly free.
- **`--concurrency 5`.** MAS ran `PROCS=1 × --concurrency 5` tonight, not the 2
  that CLAUDE.md's in-flight-ceiling row is written against. Their ceiling is
  flag × fan-out ≈ 20 against our 12 (2 replicas × [2 + 4]). That gap is the
  whole capacity-429 population, and it closes if they lower the flag or if we
  ever gain a replica — neither of which is being changed tonight.
