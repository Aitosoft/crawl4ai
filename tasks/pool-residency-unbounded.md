# Nothing bounds how many browsers the pool holds

**Status:** Open, not started. Carved out of `render-500-window-2026-07-31.md`
on 2026-08-01 as the M half of that diagnosis, deliberately kept out of the
`cleaned-html-collapse-guard` + `detector-round3` image.
**Priority:** High — this is the cause of the 9 × 500 in MAS's 2026-07-31 probe.
The S fixes shipping in that image make the symptom cheap (429 instead of 500)
but do not remove it.
**Effort:** M. Not the code volume — the design. It changes what the pool keeps,
under concurrency, and interacts with three things at once.
**Risk:** medium. This is the admission path for every render.
**Evidence:** `tasks/waa-eval-2026-07-30-forensics.md` §11d;
`tasks/render-500-window-2026-07-31.md` §"The actual cause" carries the queries.

## The gap

Three limits exist and none of them bounds memory:

| limit | what it bounds | where |
|---|---|---|
| `render_capacity: 2` | concurrent **renders** per replica | `aitosoft_admission.py` |
| `max_pages: 5` | **pages** per browser | `crawler_pool.py` |
| — | **live browsers** | *nothing* |

Pool residency is governed by idle TTL alone, so the browser count tracks
*distinct configs seen in the last TTL window*, not concurrency. On 2026-07-31
replica `…-btv4v` held **8 browsers to do 2 renders' worth of work**. At the
measured **139–165 MB of cgroup per pooled browser** — of which a stable
**~130 MB is `anon`**, the rest being a one-time cold-cache fill rather than a
per-browser cost — that is the whole 4 GiB budget. And it is a floor: the fixture
page those figures came from is a few hundred bytes.

Memory is therefore bounded only by a threshold on a reading, which is how a
capacity limit came to be served as an HTTP 500.

## It also thrashes

Across MAS's probe, all replicas:

| | |
|---|---:|
| `Creating new browser` | 125 |
| reuses (cold 53 + hot 46 + overflow 0) | 99 |
| closes (cold 112 + hot 20) | 132 |
| distinct signatures, **per replica** | **10–12** |

Ten to twelve identities produced 125 launches. The janitor's adaptive TTL is
the engine: above 80 % it drops `cold_ttl` to 30 s, closes browsers, and the next
request for that same config must launch a fresh one — allocating memory while
memory is tight, which is exactly what trips the guard at `crawler_pool.py:179`.
**Under pressure the current design responds by making the pressure worse.**

Note what this refutes: MAS's per-company `browser_config` does **not** produce a
signature per company. 243 hosts gave 10–12 signatures per replica. Pooling is
not defeated by their contract — it is defeated by our own eviction policy.

## Shape of the fix, not yet designed

A `pool.max_browsers` cap with LRU eviction of *idle* browsers, so memory is
bounded by construction rather than by a threshold on a reading. The design has
to answer, at minimum:

1. **What is the cap?** It follows from per-browser cost × replica budget, and
   per-browser cost is not a constant — see (3). Do not pick a number before
   `pool-browser-retains-last-page.md` is priced.
2. **Eviction vs `active_requests`.** Never evict a browser with pages in
   flight; the existing `BUSY_SINCE` janitor already owns the stuck-slot case
   and must not be duplicated or contradicted.
3. **Interaction with `pool-browser-retains-last-page.md` (#12).** That task
   lowers per-browser cost, which changes the right cap. Sequence them or price
   them together; deciding the cap first and the retention second means doing
   the cap twice.
4. **The adaptive TTL becomes redundant, or dangerous.** If the cap bounds
   memory, the memory-triggered TTL collapse that causes the thrash has no job
   left. Removing it is probably part of this change, not a follow-up.
5. **What replaces the guard?** With a cap, `get_crawler` blocks or evicts
   instead of refusing. If it can still refuse, it refuses as 429 (that is S1 in
   the parent task, shipping earlier).

## Adjacent, cheaper, already decided elsewhere

- **S3 in the parent task** closes the never-used permanent browser (0 uses in
  224 pool gets, ~130 MB of `anon` per replica). It ships in the earlier image
  and reduces the pressure this task operates under; do not re-litigate it here.
- **`minReplicas: 1`** removes the scale-from-zero burst that made this visible.
  Not code, a standing-spend decision, with Tero.

## Verification

Offline. `test_crawler_pool.py` owns this module; `fixture_origin` +
`ProductionPath` can create N browsers with distinct `browser_config`s through
the real path, which is how the per-browser figure was measured in the first
place (`test-aitosoft/experiment_pool_memory.py`). No live traffic, no Azure.
Assert eviction behaviour and browser counts, never absolute MB — those are
machine- and page-dependent.
