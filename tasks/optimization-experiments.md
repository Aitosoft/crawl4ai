# Optimisation experiments with MAS: one lever per window, measured on both sides

**Status:** open, ongoing. Opened 2026-11-04 by the deploy session, for the session after it.
**Size:** M per lever; the loop itself has no end.
**Partner:** MAS's `task-608` (their side of the same loop). Their Claude session is reachable over Remote
Control (CLAUDE.md §Cross-repo). The thread so far is `tmp/mas-repo-messages/54-…` to `83-…`; `83-…` offered MAS lever 2 for their next window.
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
  about a fifth of its replica-minutes (AZURE_OPERATIONS §4.5).
- **Our own deploys go between windows** (AZURE_OPERATIONS §2.1, §2.4: a request sent mid-switch can
  hang on the old revision), announced, and then the next window measures them.
- **Log Analytics keeps 30 days.** Copy each window's aggregates into the ledger the same day.
- **Noise.** About 75 companies (~800 requests) per window shows only gross moves: blocks ran 0 terminal
  in both runs, and a 2-in-814 event (the scale-in 500s) can appear or not by chance. Prefer levers
  whose expected effect is large, or repeat a window.

## The ledger

One row per window. Ours: ¢/request = replica-min / 60 × $0.3024 ÷ requests. MAS's columns come from
their end message. Detail for the first two rows: `tasks/upgrade-upstream-v0.9.5.md` §10.

| date | window | the one change | requests (/company) | 429 gate + mem / 5xx | ¢ / request | ¢ / company (ours + model) | lost work (MAS) | notes |
|---|---|---|---|---|---|---|---|---|
| 2026-11-04 | (i) | region → Sweden Central (v0.9.2) | 790 (10.53) | 32 + 22 / 0 | 0.049 | 0.52 + 0.76 | 0 | one replica stalled 55 s at 3.85 GB `anon` |
| 2026-11-04 | (ii) | v0.9.5 + Chrome 157 | 814 (10.85) | 46 + 5 / 2 | 0.050 | 0.55 + 0.77 | 1 (parked domain) | 500s = scale-in, not the merge |

## Levers, roughly by expected value

Sized from today's runs; argue with every one.

1. **Pages per company: MAS's lever, the biggest on our bill.** ¢/request has been flat at ≈0.05 from
   August through both runs, so our cost per company is pages × 0.05 ¢ (6.4 pages in August,
   10.5–10.9 now). Their brain and prompt choices move it. Our part is to price each window per
   request so they can see it.
2. **Cold-start 429 burst: pin one warm replica for an announced window** (`batch-scale.sh up 1` at
   the start, `down` at the end). Nearly all of a window's `render_slots` 429s land in its first
   minutes, on one replica receiving MAS's parallel scrape calls (AZURE_OPERATIONS §3.8). Retries
   absorbed all of them, so the cost is wall-clock, not pages. At most ~$0.15 a window, mostly for a
   replica the run would have started anyway. Expect `render_slots` 429s → ~0 and an earlier start.
   Cheap and clean. Do it first.
3. **Scale-in kills in-flight renders** (mechanism and size: AZURE_OPERATIONS §2.4; small, absorbed by
   retries). **First verify the mechanism locally**: SIGTERM the local server during a stalled
   `raw://` render; does Playwright's `handle_sigterm` close the browser? Only then write a fix, which
   may be a launch flag in an upstream-owned file (check upstream first, Principle 1). Expected
   effect: scale-in 500s → 0.
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
- **Scale-trigger changes.** ¢/request was flat at 2 and at 3 replicas; there is no idle fleet to cut.
- **A #2416 patch.** 0 of 630 real pages change (FINDINGS §Parse collapse).

## What I am least sure of

1. **That ¢/request stays flat as the shape changes.** Three points (August, (i), (ii)), all at 5 in
   flight. At 15 in flight, or with a warm replica pinned, it could move either way.
2. **That the window-to-window noise is small enough** for levers 3–5 to show at ~800 requests.
   Repeating a window is cheap; do it before believing a small move.
3. **That cohorts are comparable.** Each window is a different random draw of companies. The rates
   compare; the pages don't.
