# 9 renders failed inside one 4½-minute window, and the sweep is a burst

**Status:** Open — **the cause is found; the fix is not designed.** A coordinator
pass on 2026-08-01 ran the correlation IDs and the answer came back in two
queries, so this task is no longer an investigation into *what* happened. Read
§"What the logs say" before planning anything; the three competing hypotheses
this file used to open with are all refuted and are kept at the bottom for
calibration. **Zero live traffic**, still — everything here is Log Analytics.
**Priority:** High, and higher than when this file was written. The failure
population looked small (3.6 % of one probe) while it read as a per-host rate.
It is not one: **every 500 landed on a scale-out step**, and scale-out is what
MAS's ~15,000-company sweep does continuously. The failure also arrives as the
one wire status their client retries three times, so it is self-amplifying at
exactly the moment capacity is tightest.
**Effort:** S-M — the diagnosis is done, the fix is a reading and a status code.
**Risk:** low, but it touches the pool's admission path; fixture-driven only.
**Evidence:** `tmp/mas-repo-messages/09-from-us-taxonomy-answer-and-zero-traffic.md`
§2 and its corrections section.

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

## What the logs say — VERIFIED 2026-08-01, not a hypothesis

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
`server_peak_memory_mb` of **204–235 MB** — on a **4 GiB** replica. Those two
numbers cannot both describe the same memory.

### Both of MAS's questions are answered by this, and one of them changes their ledger

1. **The 9 × 500 never reached the origin.** The guard at `crawler_pool.py:179`
   sits *before* `AsyncWebCrawler(...)` and `crawler.start()` — no browser was
   created, so no navigation happened. **MAS's day cost 246 origin hits, not
   255.** Their message 09 correction asked for exactly this number.
2. **The clustering is real and it is a scale-out ramp, not a per-host
   property.** Replica count across the run, from `ContainerGroupName_s`:

   | window (UTC) | distinct replicas | 500s |
   |---|---:|---:|
   | 04:40–04:44 | 2 | 0 |
   | 04:46 | **4** | **8** |
   | 04:48 | 4 | 0 |
   | 04:50 | **6** | **1** |
   | 04:52 → 05:08 | 5–6 | 0 |

   All nine land on the two scale-out steps (2→4, then 4→6) and none land
   anywhere else. MAS was right to flag it and right not to read a 3.6 % per-host
   rate into it.

### What is still open — this is the actual work

The mechanism is known; **why the reading is 85–100 % is not**, and the fix
depends on it. Leading candidate, to confirm and not to assume:

- **`memory.current` includes the page cache.** `get_container_memory_percent()`
  (`deploy/docker/utils.py:411`) is `memory.current / memory.max` on cgroup v2.
  On v2 `memory.current` counts file cache, and a replica that has just pulled
  and started a 1.79 GB image has a large cache component that the kernel would
  happily reclaim under pressure. The standard correction is to subtract
  `inactive_file` from `memory.stat`. If that is it, the guard has been refusing
  work over memory that was never actually scarce — which is what the 235 MB
  process peak already suggests.
- **The create path is the common path, not the rare one.** In the same window:
  **125 "Creating new browser" against 53 cold-pool reuses** for ~252 requests.
  The memory check only runs when a *new* browser is needed, so a pool that
  rarely reuses turns a rare guard into a per-request one. Worth checking whether
  MAS's per-company `browser_config` (their contract — per-company UA, viewport,
  headers) produces a distinct `_sig` per request and therefore defeats pooling
  by design. If so, this compounds with the sweep: 15,000 companies is 15,000
  signatures.
- **The wire status is wrong regardless of the reading.** "We are full" already
  has a correct shape in this codebase — RenderGate answers 429 + `Retry-After`,
  which MAS backs off on. The memory guard answers 500, which MAS retries three
  times, so the response to memory pressure is *more* load. **This is the same
  defect shape as the `render_error` split in
  `cleaned-html-collapse-guard.md`: one condition, two wire statuses, and the
  expensive one is not chosen deliberately.** Fix them with the same reasoning.

Do not lower or raise the 85 threshold as the fix before the reading is
understood; a threshold on a wrong number is still wrong.

### The three hypotheses this file opened with — all refuted, kept for calibration

*Cold/starting replica whose pool browser is not up* — directionally right about
scale-out, wrong about mechanism; nothing in the logs shows an uninitialised
pool. *Concurrency (RenderGate)* — no, RenderGate answers 429 and none were
issued. *A property of those five hosts* — no; four of the five sit in the 04:46
bin with three other hosts' requests, and the same hosts succeeded minutes later.

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

## The fix, once the reading is understood

Do not design it before the page-cache question is settled, but the shape is
already constrained by three things we know:

1. **The reading must describe memory that is actually scarce.** If `inactive_file`
   is the difference, correct `get_container_memory_percent()` there and say in
   the code which number it now reports. This is `deploy/docker/utils.py`, ours
   since the file is Aitosoft-side of the boundary — check `AITOSOFT_FILES.md`
   before assuming.
2. **A refusal is a 429, not a 500.** Match RenderGate: `Retry-After`, and a
   `failure_class` that says capacity rather than `render_error`. MAS retries 500
   three times with 1 s/2 s/4 s backoff, so today a memory-pressure event
   multiplies its own load by four at the worst possible moment.
3. **It is testable offline.** `test-aitosoft/test_crawler_pool.py` already owns
   this module and `test_admission.py` owns the 429 shape. A fake
   `get_container_memory_percent` and a fixture-origin request is the whole
   instrument — no live traffic, no Azure.

Reproducing the *reading* offline is the one part that may not be possible in the
dev container; if not, say so and verify it from the next deploy's logs rather
than inventing a local cgroup.

## Verification

- Zero live requests. Log Analytics + the correlation IDs above. The queries that
  produced §"What the logs say", for re-running rather than re-deriving:

  ```kusto
  // the nine, with cause
  ContainerAppConsoleLogs_CL
  | where TimeGenerated between (datetime(2026-07-31T04:40Z) .. datetime(2026-07-31T05:10Z))
  | where Log_s contains 'server error 500'
  | extend cid=extract('cid=([0-9a-f]+)',1,Log_s), err=extract('"error": "([^"]*)"',1,Log_s)
  | project TimeGenerated, cid, err | order by TimeGenerated asc

  // the scale-out ramp
  ContainerAppConsoleLogs_CL
  | where TimeGenerated between (datetime(2026-07-31T04:40Z) .. datetime(2026-07-31T05:10Z))
  | summarize replicas=dcount(ContainerGroupName_s) by bin(TimeGenerated, 2m)

  // pool churn: creates vs reuses
  ContainerAppConsoleLogs_CL
  | where TimeGenerated between (datetime(2026-07-31T04:44Z) .. datetime(2026-07-31T05:05Z))
  | summarize creates=countif(Log_s has 'Creating new browser'),
              coldreuse=countif(Log_s has 'Using cold pool')
  ```

  Workspace `workspace-aitosoftprodnCsc`, customer ID in `DEPLOYMENT_INFO.md`;
  `az account show` was already authenticated on 2026-08-01.
- Write the verdict into `tasks/waa-eval-2026-07-30-forensics.md` §11 — the file
  currently ends at §10e, so §11 is a new section.
- Both MAS answers go into message 10: **246 origin hits, not 255**, and **the
  clustering is the scale-out ramp**. Both are already established above; the
  session's job is the fix, not re-confirming them.
- If the fix is small, it joins the `cleaned-html-collapse-guard` +
  `detector-round3` image rather than getting its own deploy. **That coupling is
  why this task runs before those two** — after their image ships, this option is
  gone.
