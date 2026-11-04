# Optimisation experiments with MAS: one lever per window, measured on both sides

**Status:** open, ongoing. Opened 2026-11-04 by the deploy session, for the session after it.
**Size:** M per lever; the loop itself has no end.
**Partner:** MAS's `task-608` (their side of the same loop). Their Claude session is reachable over Remote
Control (CLAUDE.md §Cross-repo): on 2026-11-04 it was listed as "Task-608 prospect scraping
optimization" and signed as `aitosoft-platform-a3` (the same bridge session that held task-606; find it
with `ListAgents`, or reply to the latest message's `from`). The thread so far is `tmp/mas-repo-messages/54-…` to `90-…`. In `88-…` MAS set the
order: **window 1 is a baseline on never-scraped prospects, window 2 is lever 2**; `89-…` agreed and
corrected lever 2; `90-…` corrected our cost figures for runs (i)/(ii).
**Gate:** none. Tero gave both repos a standing green light on 2026-11-04 to experiment toward
affordable, robust scraping of prospect websites, on real never-scraped prospects with production writes.

## The frame (Tero's, 2026-11-04)

There is no fixed baseline and never will be. MAS's agent changes model now and then, and old models
disappear, so identical inputs will not give identical outputs. The question for every window is
**better or worse than the last one?**, aiming slightly better each time. The asset we are building is
**the ledger below: which levers exist, what each did, measured on both sides.** Technical questions
are ours and MAS's to decide; tell Tero what was decided.

## How a window works (agreed with MAS on 2026-11-04, and it worked twice)

- **MAS announces** the start and the shape (cohort, companies, in-flight, brain). **One change per
  window**; everything else is held still. They send the end time and their counts. Nothing calls
  `-se` outside windows unless announced.
- **We read our side:** `azure-deployment/window-watch.sh` under the Monitor tool during the run;
  `azure-deployment/window-readout.sh <t0> <t1>` after it (`LAW_ID` from PRIVATE.md); replica-minutes
  from Azure Monitor `Replicas`. Wait a few minutes before comparing totals: HTTP rows land after
  console rows.
- **Count the headline numbers on both sides.** Wire statuses agreed to the request in both runs so
  far. If they don't, that disagreement is the finding.
- **Price per request, not per window.** A short window carries a cold start and an idle tail of
  20–24 % of its replica-minutes (AZURE_OPERATIONS §4.5). **Read replica-minutes only once the
  fleet is back at zero** (10–16 min after the last request), split by revision:
  `azure-deployment/replica-minutes.sh <t0> <t1> <t2>` prints the window and its tail separately.
  Both runs' first readouts were taken too early and under-read by ~11 %.
- **Our own deploys go between windows** (AZURE_OPERATIONS §2.1, §2.4: a request sent mid-switch can
  hang on the old revision), announced, and then the next window measures them.
- **Log Analytics keeps 30 days.** Copy each window's aggregates into the ledger the same day.
- **Noise.** About 75 companies (~800 requests) per window shows only gross moves: blocks ran 0 terminal
  in both runs, and a 2-in-814 event (the scale-in 500s) can appear or not by chance. Prefer levers
  whose expected effect is large, or repeat a window.

## The ledger

One row per window. Ours: ¢/request = replica-min (window + tail, to zero) / 60 × $0.3024 ÷ requests.
MAS's columns come from their end message. Detail for the first two rows: `tasks/upgrade-upstream-v0.9.5.md`
§10. Rows (i) and (ii) were corrected on 2026-11-04 from 77.5 / 81.5 replica-minutes, which were read
before the tail ended (AZURE_OPERATIONS §4.5).

| date | window | the one change | requests (/company) | 429 gate + mem / 5xx | ¢ / request | ¢ / company (ours + model) | lost work (MAS) | notes |
|---|---|---|---|---|---|---|---|---|
| 2026-11-04 | (i) | region → Sweden Central (v0.9.2) | 790 (10.53) | 32 + 22 / 0 | 0.056 | 0.58 + 0.76 | 0 | 87.0 replica-min (69.5 + 17.5 tail); one replica stalled 55 s at 3.85 GB `anon` |
| 2026-11-04 | (ii) | v0.9.5 + Chrome 157 | 814 (10.85) | 46 + 5 / 2 | 0.055 | 0.60 + 0.77 | 1 (parked domain) | 89.5 (68.0 + 21.5); 500s = scale-in, not the merge |
| 2026-11-04 | w1 | none: baseline on 75 never-scraped prospects, 13:09:35–13:35:28Z | 699 (9.32) | 42 + 11 / 20 | 0.046 | 0.43 + 0.53 (all-in 2.27, MAS) | 1 | 64.0 replica-min (48.0 + 16.0); fleet held at **2** (28 req/min); 31 of 42 gate 429s in the first 3 min at 1 replica. The 20 × 500 were 4 URLs × 4 attempts, all deterministic: http-only steel-air.fi (Chrome 157, fixed before w2), 3 inline PDFs, 1 JS shell. MAS: `93-…`, `97-…`; ours: `95-…` |
| 2026-11-04 | (between) | **ours: `0.9.5-https-first`**, live 14:24:12Z | | | | | | not a window. Chrome 154+ refused http-only sites (AITOSOFT_CHANGES). MAS records it in w2's config beside their change |
| 2026-11-04 | w2 | **MAS's**: retry a model-host 429 on the same host before the fallback; 14:46:58–15:18:19Z | 656 (8.75) | 29 + 13 / 4 | **0.073** | 0.64 + 0.52 | 1 | 95.0 replica-min (77.5 + 17.5). **Nothing changed on our side, and the fleet went to 3 at 22 req/min** (14:59), where w1 held 2 at 28: our cost per request is the scaler's choice of 2 or 3 (lever 2). Gate 429s by fleet size: 13 at 1 replica, 13 at 2, 3 at 3. 4 × 500 = page behaviour (navigation loops). MAS: `102-…`; ours: `103-…` |
| 2026-11-04 | w3 | **ours: fleet fixed at min = max = 2** (lever 2, revised), 15:55:41–16:20:07Z, judged against w2 | 674 (8.99) | 7 + 1 / 0 | **0.052** | 0.47 + 0.55 | 4 (likely the 4 dead sites) | 70.0 replica-min (56.0 incl. ~3 min warm-up + 14.0 after, the release revision's own 2 idle replicas). **Held on every pre-registered line**: −26 % replica-min, −28 % per request vs w2; cold-start 429s gone; 200 p50/p90/p99 6.0/10.7/18.9 s, best of three; MAS window 24:26 (w2 31:21), 0 pages out of retries. vs w1 (2 replicas by luck) +14 % per request = the warm-up. MAS: `109-…`; ours: `110-…` |
| 2026-11-04 | w4 | **MAS's**: 8 companies in flight on the standing fixed 2, 17:01:27–17:19:38Z | 722 (9.63) | 62 + 0 / 8 | **0.041** | 0.40 + 0.60 | 0 | 59.0 replica-min (42.0 + 17.0). Predictions (`112-…`) held: gate 429s 62, slot use 82 % (w3 55 %), 200 p50/p90/p99 9.7/15.5/35.4 s; MAS wall-clock per company +19 %, window 18:11. 0 out of retries. The 8 × 500 = luppoapartments.fi `ERR_HTTP2_PROTOCOL_ERROR` ×8 (lever 9). Two replicas are near their knee at 8. MAS: `121-…`; ours: `122-…` |
| 2026-11-04 | (between) | **ours: `0.9.5-http-as-asked`** (HttpsUpgrades off), live 17:20:26Z in the same update as w4's release | | | | | | acked `115-…`. Tier 1 3/4: jpond.fi https timeout, no known path from the change. Watch `render_timeout` on https and `origin_http_error` 400 on http in w5 |

## Levers, roughly by expected value

Sized from today's runs; argue with every one.

1. **Pages per company: MAS's lever, the biggest on our bill.** ¢/request has stayed near 0.05 from
   August (0.052, day-scale) through both runs (0.055–0.056, window plus tail), so our cost per
   company is pages × ≈0.055 ¢ (6.4 pages in August, 10.5–10.9 now). Their brain and prompt choices move it. Our part is to price each window per
   request so they can see it.
2. **Fix the fleet at 2 (min = max = 2) for an announced window: cost per request, and the cold start.**
   *Revised 2026-11-04 after w2, and agreed by MAS (`104-…`); the floor-only design below is kept
   for its evidence.* At MAS's shape (5 in flight) the scaler lands a window on 2 or 3 replicas more
   or less by chance: 3 in (i), (ii) and w2, 2 in w1. That decides our cost per request (0.046 ¢ in
   w1 at 2 replicas, 0.073 ¢ in w2 at 3, where w2 had 14 % more render-seconds and 6 % fewer
   requests). Render slots were 94 % busy in w1's window and 67 % in w2's (`RequestDuration` sums,
   queue waits included, so both are upper bounds). A floor removes only the cold-start burst, which
   varied 13–31 render-gate 429s between w1 and w2 with nothing changed, so a floor's effect sits
   inside the noise. A fixed 2 also removes the chance third replica.
   - **Pre-registered against w2:** replica-minutes ≈ 2 × (lead + window) ≈ 65–75 against 95
     (**≈−25 % per request**); cold-start 429s gone; render-gate 429s *during* the window may rise
     (w2 had 13 in 9 minutes at 2 replicas); MAS's wall-clock per company may rise; memory-guard
     429s may rise (w1 at 2 replicas: 11). **Failure condition:** any page out of 429 retries, which
     is MAS's stop rule.
   - **Tooling:** `batch-scale.sh fix 2`, and afterwards `batch-scale.sh release`, which restores
     max from `deploy-image.sh`'s `ACA_MAX_REPLICAS`. `down` would keep max at 2. Both mint a
     revision and verify. While max isn't 20, `deploy-image.sh` refuses to deploy (its drift check),
     which guards against a forgotten release.
   - **If it holds,** the sweep lever is a fleet ceiling sized to companies in flight. That needs a
     second point, e.g. 10 in flight at 4, before anyone believes a ratio.
   - **Result (w3, 2026-11-04): it held on every line** (ledger row). It buys *predictability*: our
     cost per request stops depending on whether the scaler adds a third replica. Under a fixed fleet,
     our cost per company = fleet × MAS's wall-clock per company ÷ companies in flight. So **more in
     flight on the same fleet** and **a faster brain** both become levers on our bill. Proposed to
     MAS as the standing setup for their windows (`110-…`). Next point: 8 in flight on the same 2, to
     find where 429s start.
   - **The release revision is not free.** `release` mints a revision that starts as many replicas as
     the old one had (2 at 16:21:05, with nothing calling), and they idle ~5 min before scaling to
     zero. So releasing right after the window replaces the natural tail (14.0 vs 16–17.5
     replica-min) instead of removing it. Per window the protocol costs ≈ the warm-up minutes.

   *The floor-only design, as first corrected (superseded):*
   (MAS's window 2, after their baseline). *Corrected 2026-11-04:* this used to say "pin one warm
   replica, expect `render_slots` 429s → ~0", and one replica is exactly where the burst happens.
   Per minute, `ContainerAppHTTPLogs` `/crawl` by `bin(StartTime, 1m)` with
   `dcount(ReplicaName)` (requests / 429s / replicas): run (i) 08:32 24/14/1, 08:33 31/8/1, 08:34
   31/7/2, 08:35 37/2/2, then 3 replicas at 0–5 a minute; run (ii) 09:30 23/13/1, 09:31 38/15/1,
   09:32 34/14/1, 09:33 39/3/2, then 3 at 0–1. The brain's fan-out puts 12–13 in flight and a
   replica holds 6 (2 rendering + 4 queued). So **N = the steady fleet of the previous window at
   the same shape**: 3 in (i)/(ii); read window 1's (never-scraped prospects may differ).
   - **What it buys, honestly: no captures.** 0 pages ran out of 429 retries in either run. It buys
     a window without the cold start (the first requests' 50–60 s p50, 3–4 min at one replica, the
     429 burst) and without the in-window scale-in kill (lever 3's 500s: the fleet can't drop below
     the pin), at a price we will then know. If that price is flat, the pin can become the standing
     setup for later windows, so their levers are measured on a warm fleet; it is also the
     cold-start answer for any bigger sweep. The clean-context review said not to spend a window
     on it. It rides on window 2's real prospects at no extra model cost, so we kept it, relabelled
     as a measurement-setup change.
   - **Procedure.** Each `minReplicas` change mints a revision (the April log: "the min-replicas
     update rolled `0000020`"), so `up` and `down` both carry §2.4's risks. MAS sends "ready" ~10 min
     ahead and sends nothing until our "warm". Then `batch-scale.sh up N`, and wait for two things:
     the system log's `Setting traffic weight of '100%'` for the new revision (`revision list` lies
     about this, §2.4), and N × `Application startup complete` in the new revision's console log (a
     Running replica on an uncached node may still be pulling, §6.5). Send "warm". At MAS's end
     message, check that the console log has no `RenderGate ADMIT` in the last 60 s (HTTP rows
     lag), then `batch-scale.sh down` (it verifies). Forgetting `down` costs N × $0.30/h.
   - **Pre-registered, against window 1:** `render_slots` 429s **≤ ~5** (per-request routing at 13 in
     flight over 3 replicas: P(some replica gets a 7th) is 10–30 % at the peak, and the gate also
     rejects after a 15 s queue wait); first-minute p50 at the normal 6–8 s; **0 scale-in 500s
     inside the window**; memory-guard 429s not predicted (22 vs 5 between (i) and (ii), and run
     (i)'s came from one replica at 3.85 GB). Cost: N × (lead + window) + whatever the `down`
     revision costs (unmeasured; if it starts a replica for its 300 s cooldown, about +5). At N = 3,
     a 4-min lead and a 26-min window that is ≈90–95 replica-min against (i)/(ii)'s 87–89.5, because
     `down` replaces a 10–16 min tail. So **≈flat to +10 % per request.** Report window and tail
     separately; the `down` revision's own replicas belong to the tail.
   - **Alternatives considered.** MAS ramping its first minute (2 companies, then 5) removes the
     same burst for free, but it is their change and prices nothing on our side. Doing nothing is
     legitimate: retries absorb the burst.
3. **Scale-in kills in-flight renders** (mechanism and size: AZURE_OPERATIONS §2.4; small, absorbed by
   retries). **First verify the mechanism locally**: SIGTERM the local server during a stalled
   `raw://` render; does Playwright's `handle_sigterm` close the browser? Only then write a fix, which
   may be a launch flag in an upstream-owned file (check upstream first, Principle 1). Expected
   effect: scale-in 500s → 0. **Worth less than when it was written:** a pinned window (lever 2)
   can't scale in below the pin, so inside windows it would already be 0. It matters only for
   unpinned runs that scale above the pin. Note for whoever verifies it: production's SIGTERM path
   is supervisord → gunicorn master → uvicorn worker, with no `stopasgroup`. A bare local uvicorn is
   not that path, so reproduce it under supervisord (Principle: patch the layer below the one you
   test).
4. **`delay_before_return_html: 2.0` is MAS's config and ~37 % of our mean render time**
   (AZURE_OPERATIONS §4.5). Lowering it cuts render-seconds per page, so ¢/request, if the fleet
   follows render demand. Risk: pages that paint late come back thin. The capture-point canary is
   MAS's "newly empty" count, plus our `fixture_origin` `/hydrate-after/`. A joint window, their
   change.
5. **Browser identities.** MAS sends a per-company identity, so nearly every company launches its own
   browser (64–70 launches per 75 companies), and six of them filled a 4 GiB replica in run (i). A
   small set of shared identities would mean reuse: fewer launches, less memory, maybe faster renders.
   It's a contract change, so their call. Measure launches per request, `anon`, render p50, and blocks
   (identity may matter to some anti-bot vendors; today's blocks are IP-based).
6. **Parked-domain truthfulness.** fortax.fi was a hosting company's parked page (`/cgi-sys/defaultwebpage.cgi`,
   "verkkotunnus on varattu"), and MAS's agent called it `blocked`. A signature check, theirs or a
   class of ours, makes the outcome true. Size it on MAS's data first: how many of their failed
   companies are parked?
7. **A `contacts` field** (deterministic `mailto:`/`tel:`/pattern extraction before MAS's cleaner).
   MAS's cleaner lost 514 of 535 emails on one directory page. Their `task-438` decides whether they
   want it from us; it's additive for us.
8. **4 vCPU / 8 GiB replicas** (possible since the v2 environment, AZURE_OPERATIONS §3.6, untried). Only
   if memory starts costing work; it doubles the price per replica.
9. **Deterministic 500s: stop paying four attempts for a page that can't render** (found in w1). All
   16 non-http 500s in w1 were URLs that failed identically on every attempt: three inline PDFs
   (Chrome's 356-byte viewer shell; our detector calls it blocked, and with no 403/503 that is
   `render_error`), and one JS shell with 0 visible characters in Chrome *and* Patchright. Each attempt
   costs two renders (Chrome + Patchright with a 10 s capture wait), so ~8 renders per URL, ~12 of
   699 requests. In August, 152 of 163 URLs that ever got a 500 got four in a row. The levers: classify
   the PDF viewer shell as `unrenderable_content` (200, terminal; `test_a_download_is_not_a_retryable_server_error[pdf-inline]`
   is already red for exactly this), and maybe make a both-tiers-empty JS shell terminal. Both change
   what MAS receives (500 → 200), so they need their ack. MAS's side: their extension filter doesn't
   stop the agent fetching a `.pdf` it read in page text (`96-…`). **Small:** ~2 % of requests and
   maybe 3 % of render-seconds a window. Worth it mostly because it also makes the outcome true.
   **Also in this family (w4):** `net::ERR_HTTP2_PROTOCOL_ERROR` (luppoapartments.fi, 8 × 500). It's
   the origin's broken HTTP/2, but our `_NET_ERR` table has no row for it, so it reads as "ours,
   retryable". Adding `ERR_HTTP2_` to the origin prefixes is one line, and it changes MAS's status
   (500 → 200).
10. **A marked `http://` attempt when `https://` fails at connect.** 137 companies in MAS's archive
    failed https at the tunnel and stored nothing (`115-from-us-…`). MAS wants us to do it, marked.
    Task file: `https-connect-failure-http-retry.md`.
11. **The pinning proxy dials only the first DNS answer** (`egress_broker.resolve_and_pin`). One
    stray A record (selosella.fi: `1.101.131.52` among four Fastly addresses) fails a live site
    where a browser would try the next address. Upstream's code, so check upstream before patching.
    Rare: 1 site in 225 companies.

## Instruments worth keeping

- **An old-image A/B arm.** Today the idle West Europe app (old image) answered "is it us or the site?"
  for two pages in one request each. MAS deletes it on or after 2026-11-11. If that question keeps
  coming up, a scale-to-zero second app in `aitosoft-aca-se` running the previous digest is $0 idle,
  and it would share `-se`'s region and egress pool, which makes it a cleaner A/B than West Europe
  ever was. Build it only when a question needs it.
- **630 real raw pages** from run (ii) (`tmp/research/tailloss-data-2026-11-04/`, MAS's export format;
  kept by decision on 2026-11-04). The offline re-scrape corpus for any scraper-side change and for the
  next upstream merge (`tmp/research/tailloss/tailloss.py` loads it; its control checks that the
  offline path reproduces production's markdown).

## What I talked myself out of

- **Anti-bot or stealth work.** 0 terminal blocks in 1,604 requests; 3 Cloudflare challenges, all
  rescued by the existing retry. The one 2026 benchmark credits real Chrome, which we run, for most of
  the advantage (`tmp/research/upstream-and-web-scan-2026-11-04.md`).
- **Trimming our markdown to save model cost.** Page content is about a quarter of a company's model
  cost on MAS's US host (`64-from-us-…`). It might matter for quality (lever 7), not money.
- ~~**Scale-trigger changes.** ¢/request was flat at 2 and at 3 replicas; there is no idle fleet to cut.~~
  **Retired by w2 (2026-11-04):** at 5 in flight the fleet lands on 2 or 3 by chance, and ¢/request
  follows it (0.046 vs 0.073). The trigger is still not the lever, because the scaler is
  burst-driven (AZURE_OPERATIONS §3.2); a fixed or capped fleet is (lever 2).
- **A #2416 patch.** 0 of 630 real pages change (FINDINGS §Parse collapse).

## What the 2026-11-04 afternoon session found wrong in this file

Recorded so the next session can see what changed and argue with it.

1. **Lever 2's "one warm replica" was the shape of the failure, not the fix** (corrected in place,
   evidence there). Found from the per-minute ingress table, which nobody had cut by replica count.
2. **The ledger's cost figures were under-read by ~11 %.** 77.5 and 81.5 replica-minutes were summed
   while the fleet was still stepping down. The same recipe, re-run with the fleet at zero, gives
   87.0 and 89.5. Two instruments agree on the recount: the unsplit recipe and the per-revision
   split. Told MAS in `90-…`, because their ledger uses our per-company figure.
3. **The `Replicas` metric averages overlapping revisions.** That didn't affect (i) or (ii), which
   ran on one revision each. It would have under-read every pinned window, because `up` and `down`
   each mint a revision. Recorded in AZURE_OPERATIONS §4.4. `replica-minutes.sh` splits by revision.
4. **Not wrong, but missing:** that a `minReplicas` change is a revision change, with §2.4's two
   risks (killed in-flight renders, the stranded request). Now part of lever 2's procedure.

## What I am least sure of

1. **~~That ¢/request stays flat as the shape changes.~~ It doesn't, even at a fixed shape** (w1
   0.046, w2 0.073). It follows the fleet size the scaler happens to pick. What I'm now least sure
   of is whether a fixed 2 holds up when the cohort's pages are slow (w2's p90 was 16.5 s), or
   whether the 429 back-off costs MAS more wall-clock than we save.
2. **That the window-to-window noise is small enough** for levers 3–5 to show at ~800 requests.
   Repeating a window is cheap; do it before believing a small move.
3. **That cohorts are comparable.** Each window is a different random draw of companies. The rates
   compare; the pages don't.
4. ~~**What `batch-scale.sh down` costs.**~~ Measured at w3's release: the new revision started 2
   replicas, matching the old one's count, and they idled ~5 min. So ~10 replica-min, about one
   natural tail.
