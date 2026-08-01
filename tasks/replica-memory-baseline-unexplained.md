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
