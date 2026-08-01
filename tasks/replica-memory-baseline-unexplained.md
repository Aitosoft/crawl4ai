# ~59 % of every replica is memory we cannot account for

**Status:** Open, not started. Opened 2026-08-02 by the session that built
`pool-residency-unbounded.md`, because that task's measurements produced this
one and it is worth more than the cap that was built.
**Priority:** this is the term that actually trips the memory guard. Everything
we have shipped against "the replica ran out of memory" has been aimed at the
other 22 %.
**Effort:** M — it is a measurement problem, not a code problem, and the
instrument we have cannot see it yet.
**Risk of not doing it:** we keep spending images on terms that do not move the
number, and MAS keeps getting 429s on cold waves.

## The finding

Regressing the memory reading on the live browser count, over all 68 `📊 Pool:`
lines of MAS's 2026-07-31 probe (five replicas, 04:44–05:35):

```
mem% = 59.3 + 2.65 × browsers        n = 68, r² = 0.216
```

| browsers | n | mean mem% | min | max |
|---:|---:|---:|---:|---:|
| 3 | 6 | 65.7 | 61.6 | 72.4 |
| 4 | 21 | 69.6 | 60.2 | 86.8 |
| 6 | 12 | 74.1 | 64.4 | 88.6 |
| 8 | 6 | 84.6 | 73.6 | 100.0 |

- The **intercept is 59.3 %** — ~2.4 GB of a 4 GiB replica with *no* pool
  browsers resident.
- Boot is **8.2 %**. So ~2.1 GB appears once the replica starts serving and does
  not scale with resident browsers.
- Browser count explains **22 %** of the variance. The same replica read 82.3 %
  holding 4 browsers and 73.6 % holding 8.

The guard fires at 85 %. With a 59.3 % floor, it has ~9.7 browsers of headroom
and it does not take much of anything else to close that gap.

## Why nobody saw it

`experiment_pool_memory.py` samples **between** crawls — after each one
completes and the pool settles. Every per-browser figure we have
(139–165 MB, and this session's 170 MB against a realistic page) is therefore a
measurement of an **idle** pooled browser. Whatever a *render in flight* costs
has never been measured at all, on any instrument.

That is the leading hypothesis and it is untested: `render_capacity` is 2, and
two concurrent renders of real pages plus our own parse pipeline (a 700 KB
document → lxml tree → `cleaned_html` → markdown → JSON, each stage a multiple
of the last) could plausibly be most of 2 GB. It would fit the shape: appears
with traffic, does not scale with residency, swings on a ~10 s timescale.

## Candidates, in the order they are worth testing

1. **In-render transient memory.** Sample the cgroup *during* `arun`, not
   between crawls. `fixture_origin` + `ProductionPath` can do this today with a
   sampler thread and `/heavy`; no new infrastructure. Vary concurrency 1 → 2 to
   see whether it scales with `render_capacity`.
2. **Our own parse pipeline.** Same instrument, but measure the Python side
   separately — feed a stored 700 KB capture straight through the scraping and
   markdown strategies with no browser at all. If this is big, it is also the
   cheapest to fix and it is entirely ours.
3. **The patchright singleton.** A whole extra Chromium that lives outside
   `HOT_POOL`/`COLD_POOL`, is invisible to `get_pool_snapshot()`, and is
   recycled by use count only — never by memory or idle time. It is started
   lazily by the first blocked result, so during a 243-host probe it is live and
   constant, which is exactly the shape of an intercept.
4. **Page cache the working-set correction does not subtract.**
   `get_container_memory_percent` subtracts `inactive_file` but not
   `active_file`. Cheap to check: the janitor already logs the split
   (`memory_breakdown()`), so a query over the same window answers it without
   running anything.

Test 4 first — it is a Log Analytics query against data we already have. Then 1.

## What would change if it is (1)

The lever stops being the pool and becomes `render_capacity`, which is already
the ACA scale-rule knob — meaning the fix is a config change and a scale-rule
change, not code. That is worth knowing before the sweep, because it is also the
cheapest thing on the list to get wrong: `render_capacity` **must** match the
scale rule (`config.yml`, and the invariant check in `deploy-image.sh`).

## Why the fit is not settled — coordinator re-check, 2026-08-02

**Read this before quoting 59.3, 2.65, 109 MB, or "the cap would not have
helped".** The regression is the load-bearing claim of the whole session and it
has three independent problems. **All three bias browsers downward**, which is
the direction that produced the headline.

### 1. The published binned table does not fit the published line

Weighted OLS over this file's own four bins (n = 45 of the 68):

```
slope 3.42 %/browser   intercept 55.4 %      vs the fitted 2.65 / 59.3
3.42 % of 4096 MB = 140 MB per browser
```

**140 MB is the offline instrument's answer** (142.8 MB `/ok`, 170.0 MB
`/heavy`), measured this same session on a path with no confounder in it. Two
instruments agreeing and the third disagreeing makes the third the suspect.
Binned means are not the raw data and this is not proof — it is a reason the
23 unshown points need looking at, because they are doing all the flattening.

### 2. The slope was fitted through a live control loop

The adaptive TTL — **removed by this very session** — collapsed `cold_ttl` to
30 s above 80 % memory, *closing browsers when memory was high*. That is a
feedback path from memory to browser count, active throughout the probe. An
observational slope fitted across it estimates the controller, not the cost:
high-memory samples systematically carry fewer browsers, flattening the slope
and inflating the intercept.

This file's own headline anecdote — *"the same replica read 82.3 % holding 4
browsers and 73.6 % holding 8"* — is the signature of that loop, not evidence
against browsers. It is what a janitor shedding under pressure produces.

### 3. The metric changed between the data and today

The 68 lines are from rev `--0000031` (2026-07-31). `get_container_memory_percent`
began subtracting `inactive_file` in `13fcecb`, deployed **2026-08-01**. So the
intercept is in **raw `memory.current`** — reclaimable page cache included.
Candidate 4 below spots that `active_file` is still not subtracted; it misses
that in *this data* neither was. A chunk of "59 % nobody can account for" may be
a term the current build already removes.

### What follows

- **The cap still ships.** It is correct under 2.65, under 3.42, and under the
  cardinality argument, which does not depend on memory at all. Nothing here
  blocks the deploy.
- **"`max_browsers` would not have prevented the nine 500s" is withdrawn as
  stated.** The nine readings were 85.1–95.6 %. Capping 9–10 browsers to 6:
  at 85.1 % it clears the guard under *both* slopes (77.1 % / 74.8 %); at
  95.6 % it is marginal under 2.65 and clears under 3.42. The supportable claim
  is **"it would have prevented some of them, and the fraction turns on a slope
  we have not settled"** — which is still a real correction to the old record,
  just a smaller one.
- **Removing pressure-driven shedding was decided by the disputed number.** With
  the adaptive TTL gone and the memory guard refusing *before* `_evict_for_capacity`
  runs, a replica over 85 % now holds its idle browsers for the constant
  `idle_ttl_sec: 300` instead of shedding in ~30 s. That is fine if a browser is
  2.65 %; it is a regression on the cold-burst path if it is 3.42 %. Same number,
  second decision — which is why re-deriving it is worth more than it looks.
- **The 68 raw points are not in the repo.** A load-bearing number with no stored
  data cannot be re-checked by the next session. Store them under
  `test-aitosoft/artifacts/` with the query and the metric's build date.

**Re-derive first, then test the candidates below.** Fit on data drawn with the
TTL loop gone (the current build), or restrict to samples where browser count
was not falling; and state which metric definition each sample used.

## What NOT to conclude

- **Not "the browser cap was pointless".** It bounds a real term by construction
  and it is the only reclamation mechanism the pool has, because per-browser
  cost is a ratchet set by the heaviest page a browser ever loaded
  (`pool-browser-retains-last-page.md`). It just is not this.
- **Not "the guard threshold is wrong".** 85 % on a 4 GiB replica with no OOM
  kills observed is a defensible setting. Raising it to make the symptom go away
  would be tuning against an unmeasured term.

## Verification

Offline. Log Analytics for candidate 4 (read-only, no traffic). `fixture_origin`
+ `ProductionPath` + a cgroup sampler for 1–3. Zero live requests — none of this
needs a customer's website.
