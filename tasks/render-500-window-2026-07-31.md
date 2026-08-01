# 9 renders failed inside one 4½-minute window, and the sweep is a burst

**Status: S half DONE 2026-08-01**, shipped in the `detector-round3` +
`collapse-guard` image. M1 remains open as `tasks/pool-residency-unbounded.md`.

| | what shipped |
|---|---|
| **S1** | `crawler_pool` raises `RenderCapacityExceeded` instead of `MemoryError`; `api.py` maps it through one `_capacity_429` helper on both the `/crawl` and streaming paths → **429 + `Retry-After`**. Pinned by `test_memory_pressure_is_a_429_not_a_500` and by `test_the_capacity_slot_is_released_when_the_pool_refuses` — the 429 is raised *after* the render gate was acquired, so a burst of refusals must not wedge admission. |
| **S2** | `get_container_memory_percent()` subtracts `inactive_file` (working set), with a guard so a bogus stat larger than usage can never *hide* pressure. `get_memory_breakdown()` + `memory_breakdown()` log anon/file/inactive_file in the guard's error and the janitor's `📊 Pool:` line, so the question that cost an offline probe is answerable from logs forever. Four tests, all faking the cgroup reads — the dev container's `memory.max` is the literal string `max`, so the cgroup path is **not** exercised locally. |
| **S3** | `_close_unused_permanent()` closes the permanent browser when `USAGE_COUNT[DEFAULT_CONFIG_SIG]` is still 0 after `permanent_unused_ttl_sec` (600). Four tests, including that lazy re-init still works and that one real hit keeps it. |

**Original status when written:** cause confirmed and re-diagnosed 2026-08-01
(second pass); the fix designed and split. The coordinator's pass found the right line of
code and two of its three surrounding claims were wrong. A verification session
the same day re-ran every query with an app filter, added four the coordinator
did not run, and measured the memory question offline through the real
production path. Read §"What the logs say — CORRECTED" before planning; the
superseded version is kept in §"What the first pass got wrong".
**Zero live traffic**, still — Log Analytics plus the local fixture origin.
**Priority:** High. The failure population looked small (3.6 % of one probe)
while it read as a per-host rate. It is not one: **all nine landed on a single
replica that was carrying the whole burst because ACA had not scaled yet**, and
scaling from zero is what the sweep's first wave does by definition. The failure
also arrives as the one wire status MAS retries three times, so it multiplies
its own load at exactly the moment capacity is tightest.
**Effort:** S for the part that ships (status code + reading + a dead browser);
**M, carved out to its own task**, for the actual cause. See §"The fix".
**Risk:** low for the S part; it reuses the 429 shape RenderGate already serves.
**Evidence:** `tmp/mas-repo-messages/09-from-us-taxonomy-answer-and-zero-traffic.md`
§2; the queries and the offline probe in §Verification.

## What MAS measured

Their 243-host probe against `0.9.2-failure-class`, 04:44:56 → 05:03:39 UTC on
2026-07-31 — **the only traffic that has gone through the current image**, since
they have had zero production WAA invocations since the deploy (their §2; checked
in `agent_invocations`, not inferred).

| | |
|---|---:|
| total HTTP requests from them | **252** (corrected from 251) |
| HTTP 500 | **9** (3.6 %) across 5 hosts |
| HTTP 504 | **0** |
| max wall time, any single fetch | 34,797 ms |

Every one of the 9 was `{"error":"Internal server error", "failure_class":
"render_error"}`. **All five hosts eventually succeeded and four returned real
content**, so the origins were fine. These are our renders failing.

| host | attempts | correlation_id per 500 | first seen (UTC) |
|---|---:|---|---|
| `eurobull.fi` | 2 | `e7deaf4ececb` | 04:46:07 |
| `meitmeal.fi` | 4 | `631b86527fc3`, `4492bd99f3f7`, `c75787261894` | 04:46:18 |
| `valonkone.com` | 4 | `d0b1d722e133`, `73220db2dd23`, `7b710be5a333` | 04:46:47 |
| `savaterra.fi` | 2 | `3bac649a8171` | 04:47:06 |
| `powerofsun.fi` | 2 | `e9d8eb4e344b` | 04:50:33 |

## What the logs say — CORRECTED 2026-08-01 (second pass)

All nine correlation IDs resolve in `ContainerAppConsoleLogs_CL`. **Every one of
the nine 500s is the same line, and it is our own code refusing to work:**

```
server error 500 [cid=e7deaf4ececb]: {"error": "Memory at 95.6%, refusing new browser",
 "server_memory_delta_mb": 1.17, "server_peak_memory_mb": 235.28}
```

That string has exactly one source: `deploy/docker/crawler_pool.py:179`, which
raises `MemoryError` when `get_container_memory_percent()` is at or above
`MEM_LIMIT` — **85.0**, from our own `config.yml` (`memory_threshold_percent`,
commented "Aitosoft: was 95 — leave headroom on 4 GiB replicas").

| cid | reading | | cid | reading |
|---|---:|---|---|---:|
| `e7deaf4ececb` | 95.6 % | | `73220db2dd23` | 89.0 % |
| `631b86527fc3` | 90.2 % | | `7b710be5a333` | 88.0 % |
| `4492bd99f3f7` | 90.3 % | | `3bac649a8171` | 85.1 % |
| `c75787261894` | 92.1 % | | `e9d8eb4e344b` | 86.3 % |
| `d0b1d722e133` | 89.3 % | | | |

Every reading is just over our own 85 % line. The same log lines report
`server_peak_memory_mb` of **204–235 MB** — on a **4 GiB** replica.

### The 235 MB was never the container. That is the whole disagreement.

`server_peak_memory_mb` is `psutil.Process().memory_info().rss`
(`deploy/docker/api.py:105`) — the **single gunicorn worker**
(`supervisord.conf` runs `--workers 1 --threads 4`). Playwright launches a node
driver as a child process and Chrome as *its* children: **7 processes per
browser**, none of them in that RSS. The field is named `server_peak_memory_mb`
and reports only the Python process, which is why it reads like a container
figure and is not one.

Measured offline through the real production path — fixture origin, one pooled
browser per crawl with a distinct `browser_config`
(`test-aitosoft/experiment_pool_memory.py`), run twice: once cold and once with
the file cache already warm from the first run.

| per pooled browser | cold cache | warm cache |
|---|---:|---:|
| worker RSS — what `server_peak_memory_mb` reports | **+2.0 MB** | **+2.3 MB** |
| cgroup `memory.current` — what the guard reads | **+165.0 MB** | **+138.9 MB** |
| of which `anon` (unreclaimable) | +129.9 MB | **+129.4 MB** |
| of which `file` (page cache) | +27.1 MB | +1.8 MB |
| of which `inactive_file` | +26.0 MB | +1.4 MB |

The two numbers were never measuring the same memory, so there is no
contradiction to resolve. **The reading is not the bug.** Sum-of-RSS is not an
instrument either: the same browsers moved process-tree RSS by ~486 MB each
against the cgroup's ~139–165 MB, because Chrome's shared mappings are counted
once by the cgroup and seven times by a naive tree walk.

### The page-cache hypothesis is real but smaller than it looks, and it is not the explanation

`anon` is the stable term — **129.4 and 129.9 MB per browser across two runs** —
and it is exactly the memory the kernel cannot reclaim. The file component is
**not** per-browser: it was 27 MB/browser on the cold run and 1.8 MB/browser once
the cache was warm, i.e. a **one-time fill** of Chrome's binary and libraries
that does not scale with pool size. `inactive_file` is 16 % of the growth on a
cold container and **1 %** on a warm one.

btv4v *was* cold, so it did pay that fill once — a fixed few hundred MB, not a
proportional amount. Subtracting `inactive_file` is still the right change (it is
the standard working-set definition) but it is worth a bounded offset, not a
scaling correction, and it would not have changed the underlying condition. Three
log facts say the memory was genuinely scarce:

- **The cgroup path is live and the limit is real.** btv4v's first reading, 3 s
  after boot, was **8.2 % ≈ 336 MB** against a worker RSS of 235 MB. That is
  `memory.current / memory.max` on a ~4 GiB limit, not the `psutil` host
  fallback in `utils.py`'s bare `except`.
- **It reached 100.0 % and nothing died.** No OOM kill in
  `ContainerAppSystemLogs_CL`, and `🔥 Creating permanent default browser`
  appears exactly once on btv4v (04:44:51) — the worker never restarted. Some of
  the 4 GiB was therefore reclaimable, which is consistent with a cold
  container's one-time cache fill; an all-anon cgroup pinned at `memory.max`
  OOM-kills.
- **The browsers account for it.** At the peak the janitor logged `hot=5,
  cold=2` plus the permanent = **8 live browsers**. At the measured 165 MB that
  is ~1.3 GB over baseline; on the unreclaimable `anon` term alone it is still
  ~1.0 GB. Both are **floors** — the fixture page is a few hundred bytes and
  each pooled browser retains its last document
  (`pool-browser-retains-last-page.md`).

### Both of MAS's questions are answered, and the second one is answered differently

1. **The 9 × 500 never reached the origin.** Unchanged and confirmed: the guard
   at `crawler_pool.py:179` sits *before* `AsyncWebCrawler(...)` (line 191) and
   `crawler.start()` (192) — no browser was created, so no navigation happened.
   **MAS's day cost 246 origin hits, not 255.**
2. **The clustering is real, but it is not a scale-out ramp — it is the
   opposite.** All nine 500s are on **one replica**,
   `crawl4ai-service--0000031-7b48d7666b-btv4v`, and every one of them landed
   *before* the replica that was supposed to relieve it served anything.
   `ContainerAppSystemLogs_CL` + first `RenderGate ADMIT` per replica:

   | UTC | event |
   |---|---|
   | 04:40:00 | `KEDAScaleTargetDeactivated` — **scaled to zero** |
   | 04:44:43 | `KEDAScaleTargetActivated` 0 → 1 |
   | 04:44:49 | btv4v container started; first render admitted 04:44:52 |
   | 04:44:56 | MAS's probe starts |
   | 04:46:02–04:46:53 | **8 of the 9 × 500**, btv4v alone, 59 admits in ~2 min |
   | 04:46:54 | replica 2 (`5hbkd`) admits its **first** render |
   | 04:47:07 / 04:48:07 | → 3 replicas / → 4 replicas |
   | 04:48:37 | → 5 requested; `AssigningReplicaFailed`, *waiting for infrastructure* — node-pool scale-up |
   | 04:50:25 | **the 9th 500**, still btv4v |
   | 04:50:56 | replica 5 (`r7bt4`) finally admits its first render |

   So the mechanism is **scale-from-zero plus scaling lag**, not the act of
   adding a replica: one cold replica carried the entire opening burst for 122
   seconds, and the ninth failure lands in the 2½-minute node-pool stall. MAS was
   right to flag the clustering and right not to read a per-host rate into it.
   The consequence for the sweep is *worse* than the first pass said — every
   wave that starts from an idle service reproduces this exactly.

### The actual cause: nothing bounds how many browsers the pool holds

`render_capacity: 2` bounds concurrent **renders**. `max_pages: 5` bounds pages
**per browser**. Nothing bounds the **number of live browsers** — pool residency
is governed by idle TTL, so the browser count tracks *distinct configs seen in
the last TTL window*, not concurrency. btv4v held 8 browsers to do 2 renders'
worth of work, and at 165 MB each that is the 4 GiB.

The pool then thrashes on top of that. Across the run, all replicas:

| | |
|---|---:|
| `Creating new browser` | **125** |
| reuses (cold 53 + hot 46 + overflow 0) | 99 |
| closes (cold 112 + hot 20) | **132** |
| **distinct signatures, per replica** | **10–12** |

Ten to twelve distinct browser identities produced 125 creations. Under memory
pressure the janitor drops `cold_ttl` to 30 s, closes browsers, and the next
request for that same config must launch a fresh one — allocating memory while
memory is tight, which is what trips the guard. That is the loop.

Two corrections to the first pass fall out of the same numbers:

- **The 15,000-signature worry is unfounded.** 243 hosts produced **10–12**
  distinct signatures per replica, not one per company. MAS's per-company
  `browser_config` varies over a small set of identities. Pooling is not
  defeated by their contract.
- **NEW: the permanent browser is never used.** `Using permanent browser` fires
  **0 times** against 125 creates and 99 reuses. MAS always sends a
  `browser_config`, so `_sig` never equals `DEFAULT_CONFIG_SIG` and the boot
  browser serves nothing while holding ~165 MB for the replica's whole life.

### The wire status is wrong regardless of all of the above

"We are full" already has a correct shape in this codebase — RenderGate answers
429 + `Retry-After` (`api.py:763–775`), which MAS backs off on. The memory guard
answers 500, which MAS retries three times with 1 s/2 s/4 s backoff, so the
response to memory pressure is **four times the load** at the worst possible
moment. **Same defect shape as the `render_error` split in
`cleaned-html-collapse-guard.md`: one condition, two wire statuses, and the
expensive one is not chosen deliberately.** Fix them with the same reasoning.

Do not move the 85 threshold as the fix. The reading is now understood and
roughly right; a threshold is not what is broken.

### What the first pass got wrong, kept for calibration

The coordinator pass found the right line of code in two queries. Two of the
three claims it built on that line were wrong, and both errors came from the
same place: **the queries had no app filter, and `ContainerAppConsoleLogs_CL` is
workspace-wide.**

- **"Replica count went 2 → 4 → 6."** `summarize dcount(ContainerGroupName_s) by
  bin(TimeGenerated, 2m)` counted the `aitosoft-edge` app's replica as one of
  ours, and counted *replicas that logged in a bin* rather than replicas that
  existed. The app was scaled to **zero** at 04:40 and went 0 → 1 → 2 → 3 → 4 →
  5. Always filter `ContainerGroupName_s startswith 'crawl4ai'`, and take replica
  history from `ContainerAppSystemLogs_CL`, which states it rather than infers it.
- **"All nine land on the two scale-out steps."** They land on one replica,
  before the scale-out arrived. Adding `by ContainerGroupName_s` to the query
  that was already run shows this immediately.
- **"The two numbers cannot both describe the same memory."** Correct that they
  disagree, wrong that this indicts the reading — they describe disjoint process
  sets, and the reading is roughly right. The suggested `inactive_file`
  correction is worth ~16 % of the growth, not the discrepancy.

### The three hypotheses this file opened with

*Cold/starting replica whose pool browser is not up* — **closer than it was
credited.** Wrong about the pool being uninitialised, right that a cold
scaled-from-zero replica is the whole setting. *Concurrency (RenderGate)* — no,
RenderGate answered correctly throughout (59 admits on btv4v, capacity honoured)
and issued no 429s; it bounds renders, and browsers are what cost memory. *A
property of those five hosts* — no; the same hosts succeeded minutes later on
other replicas.

## What this replaces

`tasks/post-deploy-measurement-0.9.2-failure-class.md` is **closed** by MAS's §2.
Its remaining half was a production log census, and there is no production
traffic to census — 86 WAA runs on 2026-07-30, all before the 18:24 deploy, none
since. This probe is the entire dataset the current image has seen, so the census
is this task.

One thing the probe did settle in passing: **0 × 504, and nothing came within
145 seconds of the 180 s fence.** That is consistent with the render-hang fix
having removed the failure `static-fallback-within-fence.md` was sized against.
243 fetches on one afternoon is not a workload, but it points the way we
suspected — record it there.

## The fix — decided 2026-08-01, split S / M

**The S half ships with the `cleaned-html-collapse-guard` + `detector-round3`
image. The M half does not, and is carved out to its own task.** That split is
the decision this session was asked to make explicitly, and it is made on the
grounds that S1–S3 are independently correct, reuse shapes that already exist,
and are testable offline in the suites that already own these modules — while M1
changes how the pool decides what to keep, under concurrency, and would be the
only unreviewed design in an image whose other two items already have red tests
waiting.

### S1 — a refusal is a 429, not a 500 *(the one that matters most)*

`crawler_pool.get_crawler` raises `MemoryError`, which `api.py`'s generic
`except Exception` turns into a 500 with `failure_class: render_error`. Raise a
dedicated capacity exception instead and map it exactly as
`RenderCapacityExceeded` is mapped at `api.py:763–775`: **429, `Retry-After`,
`failure_class: capacity`**. The taxonomy already has `CAPACITY`
(`aitosoft_failure_class.py:66`) and already maps 429 → capacity (line 276);
nothing new is invented. This alone removes the 4× amplification, and it is
correct whatever we later do about the pool.

Test: `test_admission.py::test_handle_crawl_request_maps_to_429` is the template
— same assertion, `get_container_memory_percent` monkeypatched over the
threshold instead of the gate filled.

### S2 — report the working set, and log its parts

`get_container_memory_percent()` (`deploy/docker/utils.py:411`) returns
`memory.current / memory.max`. Subtract `inactive_file` from `memory.stat`
(`total_inactive_file` on cgroup v1) so it reports the working set, and say in
the docstring which number it now is. Correct on its own terms, and worth most
on exactly the replica that failed — a cold one, which pays a one-time cache
fill — but it is a bounded offset, not a scaling correction. Ship it because it
is right, not because it fixes this.

Then **log the split** in the guard's error and in the janitor's `📊 Pool:`
line: anon, file, inactive_file. One deploy later that question is answered from
logs forever, instead of from an offline probe. This is the cheap half of the
instrument this session had to build by hand.

Note for whoever writes the test: the dev container's `memory.max` is `max`, so
`int()` raises and the function falls through its bare `except` to
`psutil.virtual_memory().percent` — the cgroup path is **not** exercised
locally. Fake the file reads; do not infer from a local run.

### S3 — stop paying for a browser nobody uses

`Using permanent browser` fired 0 times in 224 pool gets. Let the janitor close
`PERMANENT` when `USAGE_COUNT[DEFAULT_CONFIG_SIG] == 0` and it has been idle;
`get_crawler` already lazily re-creates it (`crawler_pool.py:104–113`), and that
path is already covered by
`test_crawler_pool.py::test_permanent_reinit_after_stuck_force_close`. Recovers
~165 MB per replica for free. The most droppable of the three if the image gets
tight — it is a saving, not a defect.

### M1 — bound pool residency *(own task, not this image)*

The cause. `render_capacity` bounds renders and `max_pages` bounds pages, but
nothing bounds live browsers, so memory is bounded only by a threshold on a
reading — which is how a capacity limit became a 500. The fix is a
`pool.max_browsers` cap with LRU eviction of idle browsers, so memory is bounded
by construction. It has to be designed against `active_requests`, the janitor's
adaptive TTL (which currently *causes* the create/close thrash: 125 creates and
132 closes for 10–12 signatures), and `pool-browser-retains-last-page.md` —
which lowers the per-browser cost and therefore changes the right cap. Open it
as a task; do not slip it into this image.

### Not code, and not ours to decide

Every one of the nine happened because a scaled-to-zero service took a burst on
one cold replica. `minReplicas: 1` removes that condition entirely and no code
changes. It is a standing-spend decision, so it goes to Tero with a number, not
into a deploy.

## Verification

- Zero live requests. Log Analytics + the local fixture origin. Workspace
  `workspace-aitosoftprodnCsc`, customer ID
  `be17d63b-1807-49da-9846-82091ac8971d` (`az monitor log-analytics workspace
  list`); `az account show` was authenticated on 2026-08-01.

  **Every console query needs `ContainerGroupName_s startswith 'crawl4ai'`** —
  the table is workspace-wide and `aitosoft-edge` logs into it too. That omission
  is what produced the wrong replica counts in the first pass.

  ```kusto
  // 1. the nine, with cause AND the replica they landed on
  ContainerAppConsoleLogs_CL
  | where TimeGenerated between (datetime(2026-07-31T04:40Z) .. datetime(2026-07-31T05:10Z))
  | where Log_s contains 'server error 500'
  | extend cid=extract('cid=([0-9a-f]+)',1,Log_s), err=extract('"error": "([^"]*)"',1,Log_s),
           peak=extract('"server_peak_memory_mb": ([0-9.]+)',1,Log_s)
  | project TimeGenerated, cid, err, peak, replica=ContainerGroupName_s
  | order by TimeGenerated asc          // -> all 9 on ...-btv4v

  // 2. replica history — state it, don't infer it from console-log bins
  ContainerAppSystemLogs_CL
  | where TimeGenerated between (datetime(2026-07-31T04:40Z) .. datetime(2026-07-31T05:40Z))
  | project TimeGenerated, Reason_s, Log_s | order by TimeGenerated asc
  //   -> KEDAScaleTargetDeactivated 04:40, Activated 0->1 04:44:43, 1..5,
  //      AssigningReplicaFailed "Waiting for infrastructure" 04:48:37-04:49:44

  // 3. when each replica STARTED SERVING (not when it was scheduled)
  ContainerAppConsoleLogs_CL
  | where TimeGenerated between (datetime(2026-07-31T04:44Z) .. datetime(2026-07-31T04:52Z))
  | where ContainerGroupName_s startswith 'crawl4ai'
  | where Log_s has 'RenderGate ADMIT'
  | summarize firstadmit=min(TimeGenerated), admits=count() by ContainerGroupName_s
  | order by firstadmit asc             // -> replica 2 first admit 04:46:54

  // 4. the memory series and the pool beside it, on the failing replica
  ContainerAppConsoleLogs_CL
  | where TimeGenerated between (datetime(2026-07-31T04:44Z) .. datetime(2026-07-31T05:12Z))
  | where ContainerGroupName_s == 'crawl4ai-service--0000031-7b48d7666b-btv4v'
  | where Log_s has 'Pool: hot='
  | project TimeGenerated, Log_s | order by TimeGenerated asc
  //   -> 8.2% at boot, 100.0% at 04:46:32 with hot=5 cold=2, 45.1% by 04:51
  //   CAVEAT: janitor() reads mem_pct BEFORE its sleep and logs it AFTER the
  //   cleanup, so `mem=` is up to `interval` seconds staler than the hot/cold
  //   counts printed beside it. Do not pair them as simultaneous.

  // 5. pool churn and signature diversity — the actual cause
  ContainerAppConsoleLogs_CL
  | where TimeGenerated between (datetime(2026-07-31T04:44Z) .. datetime(2026-07-31T05:35Z))
  | where ContainerGroupName_s startswith 'crawl4ai'
  | summarize creates=countif(Log_s has 'Creating new browser'),
              coldreuse=countif(Log_s has 'Using cold pool'),
              hotreuse=countif(Log_s has 'Using hot pool'),
              permreuse=countif(Log_s has 'Using permanent'),
              closed=countif(Log_s has 'Closing cold browser' or Log_s has 'Closing hot browser')
  //   -> 125 / 53 / 46 / 0 / 132.  permreuse=0 is S3.

  ContainerAppConsoleLogs_CL
  | where TimeGenerated between (datetime(2026-07-31T04:44Z) .. datetime(2026-07-31T05:35Z))
  | where ContainerGroupName_s startswith 'crawl4ai'
  | where Log_s has 'Creating new browser'
  | extend sig=extract('sig=([0-9a-f]+)',1,Log_s)
  | summarize creates=count(), distinct_sigs=dcount(sig) by ContainerGroupName_s
  //   -> 10-12 distinct sigs per replica. Not 15,000.

  // 6. no OOM, no worker restart, while the reading said 100.0%
  ContainerAppConsoleLogs_CL
  | where ContainerGroupName_s == 'crawl4ai-service--0000031-7b48d7666b-btv4v'
  | where Log_s has 'Creating permanent default browser'   // -> exactly 1, at 04:44:51
  ```

- **The RSS-vs-cgroup measurement was offline**, not from Azure: the fixture
  origin driven through `ProductionPath`, 8 crawls with a distinct
  `browser_config` each so every one creates a browser, sampling
  `psutil.Process().memory_info().rss`, the process-tree RSS, `memory.current`
  and `memory.stat` after each. That is the probe behind the per-browser table
  above. It reproduces the *relationship* (worker RSS is blind to browsers; anon
  dominates file) but not the *percentage* — the dev container has no memory
  limit, so it cannot show the guard firing. Fold it into
  `test_crawler_pool.py` as a documented measurement or leave it as a
  scratch instrument; do not assert absolute MB in CI, they are machine- and
  page-dependent.
- Verdict written into `tasks/waa-eval-2026-07-30-forensics.md` §11 (2026-08-01).
- Both MAS answers go into message 10: **246 origin hits, not 255**, and **the
  clustering is one replica carrying the burst before ACA scaled** — *not* a
  scale-out ramp, which is what the first pass would have told them. Correct the
  wording before it is sent.
- **Image decision, made 2026-08-01: S1–S3 join the `cleaned-html-collapse-guard`
  + `detector-round3` image. M1 does not** and needs its own task. That is why
  this task ran before those two; the S half now has to be written before that
  image ships, or the coupling is lost.
