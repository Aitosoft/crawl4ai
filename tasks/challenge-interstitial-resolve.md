# The challenge family is a capture-timing effect, and the fix is not a global wait

**Status:** **Phase 1 done 2026-08-01 — the number is in.** Phase 2 is a **GO,
re-scoped from M to S** (§Go/no-go). Nothing deployed; phase 1 touched no
production code and made zero live requests.
**Priority:** was highest of the open work; the investigation half is now spent.
Phase 2 is small enough to ride an existing image.
**Effort:** S (phase 1, done), **S** (phase 2 — was M; the recovery vehicle turned
out to already exist).
**Evidence:** this file's §Results; `tmp/mas-repo-messages/07-from-us-243-host-rescrape.md`
§2, §5; `tasks/waa-eval-2026-07-30-forensics.md` §1, §8d, §10b, §10c.

**The grid that produced the numbers is committed:**
`test-aitosoft/experiment_challenge_capture.py` — offline, ~140 crawls against
the fixture origin through the full production path, ~20 min, zero live traffic.

```bash
python test-aitosoft/experiment_challenge_capture.py            # all four blocks
python test-aitosoft/experiment_challenge_capture.py --block A  # just the crossover
```

---

## The one-line answer

**Our capture wait `W` captures any challenge that resolves within `W + 1.22 s`
of `domcontentloaded`, and stores the interstitial for anything slower.** One
constant explains all 84 cells of the crossover grid with zero exceptions. At
MAS's `delay_before_return_html: 2.0` that is a **~3.2 s** budget.

So the hypothesis is **confirmed as a mechanism and refuted as a defect**: we do
store interstitials instead of the pages they become, but only when the challenge
outlasts the wait. There is no race, no lost-after-resolution capture, nothing
that a correctly-sized wait fails to fix. What that buys is that the fix is a
*budget* decision, and budgets can be spent where they pay.

---

## Results

Measured 2026-08-01 against `test-aitosoft/fixture_origin.py` through
`aitosoft_entry` → `api.handle_crawl_request` → a real pool browser. Raw data:
`tmp/challenge-sweep/results.csv` (gitignored; re-run the script to regenerate).

Axes: **R** = how long the interstitial takes to resolve, **W** =
`delay_before_return_html`. Both seconds. `+` = the real page was captured,
`i` = the interstitial was stored as the result.

### Block A — the crossover, and it is one constant

**`/challenge/resolve-after` (DOM rewrite) and `/challenge/resolve-by-nav`
(top-level navigation) produced byte-identical grids.**

| R \ W | 0.1 | 0.5 | 1.0 | 2.0 | 3.0 | 5.0 | 10.0 |
|---|---|---|---|---|---|---|---|
| 0.5 | + | + | + | + | + | + | + |
| 1.0 | + | + | + | + | + | + | + |
| 2.0 | i | i | + | + | + | + | + |
| 3.0 | i | i | i | + | + | + | + |
| 5.0 | i | i | i | i | i | + | + |
| 8.0 | i | i | i | i | i | i | + |

`content ⟺ W + c ≥ R` mispredicts **0 of 84** cells for any `c` in
**[1.00, 1.49]**. The grid brackets it; block B measures it directly at
**1.22 s** (`/ok` elapsed minus W, six waits, spread 1.21–1.24). Two independent
derivations, same constant.

That 1.22 s is our own post-`goto` pipeline — consent-popup removal, the image
dimension pass, the settle steps, capture — and it is **free budget**: it is time
the challenge gets to finish in that nobody asked for.

| MAS's wait | resolves it captures |
|---|---|
| 0.1 (the change they refuted) | ≤ 1.3 s |
| **2.0 (what they send today)** | **≤ 3.2 s** |
| 5.0 | ≤ 6.2 s |
| 10.0 (what they were considering) | ≤ 11.2 s |

**Read against MAS message 09 §6:** their own `raw://` measurement said 2.0
tolerates a paint of "roughly 3–5 s". We confirm the **bottom** of that range and
refute the top — 3.2 s, not 5. A 5 s paint needs W ≈ 5.

### Block B — what a raised wait costs, and the part nobody had priced

| W | `/ok` (healthy) | `/challenge/never` (a wall) |
|---|---|---|
| 0.1 | 4.04 s ¹ | 2.64 s |
| 0.5 | 1.74 s | 3.47 s |
| 1.0 | 2.21 s | 4.66 s |
| 2.0 | **3.21 s** | **6.47 s** |
| 3.0 | 4.22 s | 11.22 s ¹ |
| 5.0 | 6.22 s | 12.50 s |
| 10.0 | **11.24 s** | **25.22 s** |

¹ two single-sample outliers.

> **Footnote scope corrected, coordinator pass 2026-08-01.** "Within 0.03 s of
> the model" holds for the `/ok` column, where every non-outlier cell matches
> `W + 1.22` to 0.01–0.02 s. It does **not** hold for the wall column against
> `2 × (W + 1.22)`: W=1.0 is 0.22 s over (4.66 vs 4.44) and **W=10 is 2.78 s
> over (25.22 vs 22.44)**. The rest fit within 0.06 s.
>
> This does not touch any conclusion — every cost figure above is subtraction of
> *measured* values, not model output (the +18.8 s is 25.22 − 6.47). But the one
> cell that misfits is the largest wait on a wall, which is the closest analogue
> to what phase 2 actually does: raise the wait **on the retry**. Something costs
> extra there beyond a doubled budget — patchright startup is the obvious
> candidate and was not isolated. **Phase 2 should measure the retry leg
> directly rather than assume `2 ×`**, since that leg is the whole of its cost.

Healthy pages are exactly `W + 1.22`. **A wall is `2 × (W + 1.22)`** — because
`maybe_retry_blocked` re-runs the whole fetch through patchright, and
`aitosoft_patchright_fallback.py:208` passes **the same `CrawlerRunConfig`**, so
the raised wait is paid a second time. Confirmed by hit counts: every one of the
32 `origin_blocked` cells in block A served **exactly 2** document loads.

So `2.0 → 10.0` costs **+8.0 s on every page and +18.8 s on every wall** — the
raise is most expensive precisely on the hosts it cannot help.

**Priced against MAS's sweep (~120,000 fetches):**

| shape | added render time |
|---|---|
| global 2.0 → 10.0 | 120,000 × 8 s = **267 render-hours** |
| longer wait on the retry only, at their re-scrape's 13.6 % blocked rate | **36 render-hours** |
| same, at a plausible whole-corpus 3 % | **8 render-hours** |

and the targeted shapes add **zero page loads**, because that second fetch
already happens today.

### Block C — the families, including the one that is invisible

| marker | detected? | what we store |
|---|---|---|
| `robot-suspicion` | yes, tier 1 | `success:false`, `origin_blocked`, 202 |
| `checking-browser` | yes, challenge tier | `success:false`, `origin_blocked`, 202 |
| **`none` (unmarked)** | **no** | **`success:true`, `failure_class:none`, 54 markdown chars** |

Five cells came back `success: true` with the interstitial still in the HTML.
All five were `marker=none`. **The detector is the trigger any adaptive shape
would fire on, so an adaptive shape can only ever rescue interstitials we already
correctly call blocked.** The silent family gets nothing — and cannot even be
counted. That is `tasks/detector-round3-evidence-vs-inference.md`'s territory and
it is the ceiling on phase 2's reach.

### Block D — adaptive vs global

Simulated at the harness level: capture at W=0.1, and if the detector fires,
fetch again at W=5.0.

| R | fires | recovers | adaptive elapsed | global W=5.0 elapsed |
|---|---|---|---|---|
| 0.5, 1.0 | no | — (already captured) | **1.35 s** | 6.22 s |
| 2.0, 3.0, 5.0 | yes | **yes** | 8.9–11.7 s | 6.22 s |
| 8.0 | yes | no (5.0 + 1.22 < 8.0) | 15.2–17.9 s | 6.22 s (also fails) |

Identical for both routes. The trade is exactly what it looks like: adaptive pays
the short-wait cost on everything that captures cleanly and a roughly doubled
cost on the minority that does not. Since "captures cleanly" is the overwhelming
majority of any real corpus, adaptive wins on total render time by the ratio in
block B.

**Caveat on this block, stated because it flatters the result:** the simulation
re-*navigates*, which is an upper bound on cost and, for `resolve-by-nav`,
restarts the challenge clock. The real implementation (below) re-uses a fetch we
already perform, so it is cheaper than this block shows.

---

## The four questions phase 1 owed, answered

| Question | Answer |
|---|---|
| Where does the capture start winning? | `W + 1.22 s`. 0/84 mispredictions. MAS's 2.0 covers ≤ 3.2 s. |
| Does `resolve-by-nav` differ from `resolve-after`? | **No — identical across all 42 paired cells.** |
| What does a wall cost? | `2 × (W + 1.22)`. The raise is paid twice on exactly the hosts it cannot rescue. |
| Does adaptive beat a global wait? | **Yes, by 7–33×**, and for less than phase 2 was drafted to cost. |

The second answer is the one that changes the design, and it is a **negative**:
forensics §1's `page.content()` race — a navigation replacing the execution
context — **did not lose a single capture in 42 cells**. Our `_capture_html`
settle-and-retry (`async_crawler_strategy.py:540`) already covers it. The
argument that "a global wait cannot fix the nav case, so adaptive is forced" is
dead. **Phase 2 is justified on cost alone, not on correctness.** If the cost
argument ever stops holding, phase 2 should be dropped, not rescued.

---

## Go/no-go — **GO**, re-scoped from M to S

**What changed:** phase 2 was drafted as a new "detect-then-re-capture inside the
same render" mechanism. It does not need to be built, because **we already
re-fetch every detected block.** `api.py:829-848` runs `maybe_retry_blocked`
*inside* the wall-clock fence, and it hands patchright the same
`CrawlerRunConfig` — hence the same `delay_before_return_html`, hence a second
attempt that by construction cannot resolve anything the first one could not.

**Phase 2 is therefore: give that retry a longer capture wait.** One config value
and one config-copy in `aitosoft_patchright_fallback.py`, which is 100 % ours.

Why this is the right shape:

1. **Zero extra page loads.** The population that would get the longer wait is
   exactly the population already costing two loads.
2. **Zero cost on the happy path.** Nothing changes for a page that captures
   first time.
3. **Bounded blast radius, already fenced.** The retry runs inside
   `asyncio.wait_for(_deadline)`, so it cannot push a request past the wall-clock
   fence — the failure mode `done/render-retry-unbounded-hang.md` paid for.
4. **Cheap to be wrong.** If the real vendor's challenge never resolves for us,
   we pay the longer wait once per blocked host per sweep — at 31 hosts and +8 s,
   about four minutes. Against a possible 23 hosts recovered.
5. **No upstream delta.** It lands in our own file.

Open sizing question for the implementer, and the only one: **how long.** Block A
gives the exchange rate directly — a retry at W=10 buys resolves up to 11.2 s.
The wall-clock fence is 180 s and the retry is the only thing after the first
render, so 10 s is affordable. Justify the number against block A rather than
picking one.

**What phase 2 must NOT do:**

- Propose raising the global `delay_before_return_html`. Priced above: 267
  render-hours per sweep, landing on replicas whose measured capacity is 2
  concurrent renders.
- Claim it rescues the silent family. It cannot — block C. Say so to MAS.
- Ship alone. It is small; put it in #3+#4's image.

---

## What phase 1 deliberately did not establish, and still has not

**That this vendor's challenge resolves for us at all.** Only a live host shows
that, and `/challenge/never` is the standing reminder that a wall stays a wall:
at W=10 it cost 25.22 s and returned the interstitial anyway. Do not spend a live
request to find out — MAS re-scrapes these hosts naturally, so once phase 2 ships
their next sweep is the confirmation at zero marginal traffic. A live probe
remains a separate decision with Tero, not a step inside this task.

Vendor identification is likewise still deferred. `d1rozh26tys225.cloudfront.net`
is a CloudFront distribution over an S3 bucket (verified 2026-07-31: `server:
AmazonS3`, wildcard certificate, no owner information), so the asset host
identifies nothing. The page markup would, and MAS may be able to supply one from
a stored capture without either side making a request. Ask before fetching.

---

## Audit of this file's own claims, 2026-08-01

The 2026-07-31 rewrite followed a draft that described fixture routes which did
not exist, so every claim was re-checked against the code before anything was
built on it. **The route table and both pinned test halves were accurate.** Four
things were not, and are corrected above:

1. **"the checks we already own — the challenge tier *and the collapse ratio*".**
   The collapse ratio is **not shipped**; it is `tasks/cleaned-html-collapse-guard.md`,
   open as #3. It was listed as an asset and is a dependency. Phase 2 above uses
   the detector only.
2. **"a per-page rather than per-host split, which is what a race produces".**
   The 7.7 % / 40.7 % figures are per-host block rates within two *April-derived*
   cohorts, measured one page per host. They are not a per-page observation of
   the current run, and MAS's own reading of the same number — "the partials were
   mid-rollout in April and have since finished" (their §2) — fits it equally
   well. Downgraded from evidence to consistency. It was the weakest of the three
   supporting observations and was presented as the strongest.
3. **"the residential-proxy case shrinks to the 4 hosts serving a hard 403
   template".** 31 − 23 = 8, not 4. The derivation is in
   `residential-egress-retry-path.md`, corrected there.
4. **Phase 2's mechanism.** The file proposed building a re-capture. We already
   have one. Found by reading `aitosoft_patchright_fallback.py`, confirmed by
   hit counts (2 loads on every blocked cell).

Two facts the file did not have, both of which make phase 2 cheaper:

- `delay_before_return_html` is in `UNTRUSTED_FIELD_ALLOWLIST`
  (`async_configs.py:247`), so **MAS can already set it per request today** — a
  per-host value on their side needs no deploy from us. Worth telling them; it is
  the fallback if they want control before phase 2 ships.
- The patchright retry runs **inside** the wall-clock fence (`api.py:848`), so
  the boundedness requirement in §Verification is already satisfied by placement.

**One gap in the instrument, found by using it.** `fixture_origin.CONTENT_HTML`
renders to ~149 markdown characters, which is *below* MAS's
`DEGENERATE_CAPTURE_CHARS = 500`. So a **successful** fixture capture is
degenerate by MAS's own floor, and the collapse-ratio trigger cannot be exercised
against this fixture as it stands. It did not affect phase 1 (which triggers on
the detector), but `cleaned-html-collapse-guard.md` (#3) will need the content
page grown past 500 markdown characters before it can measure its own threshold.
Recorded, not worked around.

---

## Interaction with MAS — send this before they change their config

They are holding their capture-timing design for this result (their message 09
§6) and have explicitly not shipped a global wait. What they need:

1. **Their 2.0 covers resolves up to 3.2 s.** Confirms the bottom of their own
   3–5 s `raw://` figure, refutes the top.
2. **Do not raise it globally** — 267 render-hours per sweep, and the raise is
   paid twice on blocked hosts.
3. **We will do the targeted version server-side** at 8–36 render-hours, zero
   extra page loads, on the retry we already run.
4. **It cannot rescue interstitials we do not detect**, and we cannot count
   those. Their stored corpus can: an interstitial we returned at
   `success: true` is a page under ~500 markdown characters whose HTML carries a
   challenge asset. If they can count that class across 117,000 pages, it sizes
   `detector-round3-evidence-vs-inference.md` for both of us.
5. **`delay_before_return_html` is per-request-settable today** if they want a
   per-host value before phase 2 ships.

---

## What this does not cover

The 4 hosts serving an 80,671-byte `403 - Forbidden` template are a Block action,
not a Challenge action. No wait resolves those. They belong to
`residential-egress-retry-path.md` and are its floor.

---

## Verification (phase 2)

- Offline, `test_fixture_origin.py`: `/challenge/resolve-after/5.0` at MAS's
  W=2.0 must come back as **content** after the fix (it is `i` today — block A,
  row R=5.0). `/challenge/never` must still come back `origin_blocked`, and
  `test_an_interstitial_that_never_resolves_stays_blocked` already asserts it.
- Assert the happy path never re-captures — `fixture_origin.hits_for()` on `/ok`
  must stay 1.
- Assert the wall-clock fence still fires: `/ok?stall=` with the retry's raised
  wait must still 504 at the fence, not past it.
- Tier 1 regression 4/4 with wall-clock recorded, to prove the happy path did not
  get slower.
