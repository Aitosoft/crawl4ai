# Optimisation experiments with MAS: one lever per window, measured on both sides

**Status:** open, ongoing. **Series 1 closed on 2026-11-04** after five windows (ledger below). The
loop continues when either side has a new lever; MAS's next one is likely their `task-609` (what
the website agent writes).
**Size:** M per lever; the loop itself has no end.
**Partner:** MAS's Claude session over Remote Control (CLAUDE.md §Cross-repo). Series 1 was their
`task-608`, signing as `aitosoft-platform-a3`. Find whoever holds the thread with `ListAgents`, or
reply to the latest message's `from`. The thread for series 1 is `tmp/mas-repo-messages/54-…` to
`132-…`, and its close is `129-…` to `132-…`.
**Gate:** none. Tero gave both repos a standing green light on 2026-11-04 to experiment toward
affordable, robust scraping of prospect websites, on real never-scraped prospects with production
writes.

## The frame (Tero's, 2026-11-04)

There is no fixed baseline and never will be. MAS's agent changes model now and then, and old models
disappear, so identical inputs will not give identical outputs. The question for every window is
**better or worse than the last one?**, aiming slightly better each time. The asset we are building is
**the ledger below: which levers exist, what each did, measured on both sides.** Technical questions
are ours and MAS's to decide; tell Tero what was decided.

## How a window works (the protocol series 1 settled on)

1. **MAS sends "ready"** with the shape (cohort, companies in flight, the one change). Nothing of
   theirs calls `-se` until our "warm".
2. **We fix the fleet:** `./azure-deployment/batch-scale.sh fix 2` (min = max = 2; 2 is right at 5–8
   companies in flight; lever 2). That mints a revision.
3. **Then we check that it's warm, two ways:** both replicas log `Application startup complete` on
   the new revision, and one `/health` answers in under a second. **Don't wait for the system log's
   `Setting traffic weight of '100%'` line.** It wasn't written for two of the day's revisions, and
   waiting for it cost window 5 twelve minutes (AZURE_OPERATIONS §2.4).
4. **We send "warm"**, MAS starts, and we run `azure-deployment/window-watch.sh <t0>` under the
   Monitor tool.
5. **MAS sends its end message, stop or not.** We check that the last `RenderGate ADMIT` is over a
   minute old, then run `batch-scale.sh release`, which restores max from `deploy-image.sh`. Never
   `down`: it would leave max at 2. If one of our deploys is due, run it right after the release,
   through `deploy-image.sh` (`DEPLOY_DIGEST=` of the tested image, plus `DEPLOY_ALLOW_LIVE=1`
   because the released replicas are still up). Folding both into one hand-made `az containerapp
   update` saved nothing when it was tried (the new revision started 2 idle replicas anyway), and it
   skips the script's gates.
6. **We read out once the fleet is at zero** (~6–16 min after release): `window-readout.sh <t0> <t1>`
   and `replica-minutes.sh <t0> <t1> <t2>`, which sums per revision and prints the window and the
   tail apart. HTTP rows land minutes after console rows, so recount the wire before comparing.
7. **Count the headline numbers on both sides.** Wire statuses agreed to the request in all seven
   runs of 2026-11-04 once the HTTP rows had landed. If they ever don't, that disagreement is the
   finding.
8. **Pre-register predictions for our own levers** in the message that proposes them, and report
   against them. It kept us honest four times in series 1.

Our own deploys go between windows, announced. **From ≈2026-11-08 MAS's production traffic arrives
unannounced** (`131-…`, 1–5 in flight at any hour), so "between windows" is no longer "idle":
`deploy-image.sh` now refuses while replicas are live (AZURE_OPERATIONS §2.1).

## What series 1 established (2026-11-04, evidence in the ledger and the message files)

- **At 5 in flight the autoscaler lands a window on 2 or 3 replicas more or less by chance**, and our
  cost per request follows it: 3 in runs (i), (ii) and w2, 2 in w1. It's burst-driven
  (AZURE_OPERATIONS §3.2), so the trigger isn't the lever. A **fixed fleet** is.
- **On a fixed fleet, our cost per company ≈ fleet × MAS's wall-clock per company ÷ companies in
  flight** (plus a fixed ~16 replica-min tail per window). So more companies in flight on the same
  fleet, and a faster brain, both cut our bill. Our cost per company was 0.40–0.47 ¢ on the fixed 2,
  against 0.43–0.64 ¢ when the scaler chose. MAS's model was 0.52–0.60 ¢ a company, and their
  all-in ~2.3–2.6 ¢, of which web-search grounding is the largest line.
- **Two replicas are near their knee at 8 in flight** (render slots 76–82 % busy, gate 429s 62–117,
  0 pages out of retries).
- **Identical windows differ by about ±10 %** (w5 repeated w4: MAS's wall-clock per company +11 %,
  our cost +10 %, 429s ×1.9). Believe a move only if it's well outside that, or repeated.
- **Cold-start 429s are a one-replica effect.** The burst happens *at* one replica, after it's up,
  because MAS's brain fans out to 12–13 in flight and a replica holds 6. A warm fleet removes it;
  a single warm replica wouldn't.
- **A short window carries a fixed tail.** A plain release or deploy mints a revision that starts
  as many replicas as the old one had, even with nothing calling, so it costs about one natural
  tail. It doesn't remove the tail.
- **The window found two Chrome regressions that no offline suite could:** http-only sites refused
  since Chrome 157, and http URLs upgraded into hosting placeholders. Both fixed (AITOSOFT_CHANGES).
  Real prospects with production writes are the instrument for what loopback can't show.

## The ledger

One row per window. Ours: ¢/request = replica-min (window + tail, read at zero) / 60 × $0.3024 ÷
requests. MAS's columns come from their end message. Detail for (i)/(ii):
`tasks/upgrade-upstream-v0.9.5.md` §10. Their first readouts (77.5 / 81.5 replica-min) were read
before the tail ended and are superseded here.

| date | window | the one change | requests (/company) | 429 gate + mem / 5xx | ¢ / request | ¢ / company (ours + model) | lost work (MAS) | notes |
|---|---|---|---|---|---|---|---|---|
| 2026-11-04 | (i) | region → Sweden Central (v0.9.2) | 790 (10.53) | 32 + 22 / 0 | 0.056 | 0.58 + 0.76 | 0 | 87.0 replica-min (69.5 + 17.5); scaler went to 3; one replica stalled 55 s at 3.85 GB `anon` |
| 2026-11-04 | (ii) | v0.9.5 + Chrome 157 | 814 (10.85) | 46 + 5 / 2 | 0.055 | 0.60 + 0.77 | 1 (parked domain) | 89.5 (68.0 + 21.5); scaler went to 3; 500s = scale-in, not the merge |
| 2026-11-04 | w1 | none: baseline on 75 never-scraped prospects | 699 (9.32) | 42 + 11 / 20 | 0.046 | 0.43 + 0.53 | 1 | 64.0 (48.0 + 16.0); scaler held **2**; 31 of 42 gate 429s in the first 3 min at 1 replica. 500s: http-only steel-air.fi ×4 (Chrome 157), 3 inline PDFs ×4, 1 JS shell ×4. MAS `93-…`/`97-…`; ours `95-…` |
| 2026-11-04 | (between) | **ours: `0.9.5-https-first`**, 14:24Z | | | | | | not a window |
| 2026-11-04 | w2 | **MAS's**: retry a model-host 429 before the fallback | 656 (8.75) | 29 + 13 / 4 | 0.073 | 0.64 + 0.52 | 1 | 95.0 (77.5 + 17.5); **scaler went to 3 at 22 req/min** with nothing changed on our side. 500s = navigation loops. MAS `102-…`; ours `103-…` |
| 2026-11-04 | w3 | **ours: fleet fixed at 2** | 674 (8.99) | 7 + 1 / 0 | 0.052 | 0.47 + 0.55 | 4 (MAS: parked/placeholder pages) | 70.0 (56.0 + 14.0); against w2 −28 % per request, cold-start 429s gone, best latency (p50/p90/p99 6.0/10.7/18.9 s), MAS window 24:26 against 31:21. MAS `109-…`/`113-…`; ours `110-…` |
| 2026-11-04 | w4 | **MAS's**: 8 in flight on the fixed 2 | 722 (9.63) | 62 + 0 / 8 | 0.041 | 0.40 + 0.60 | 3 (MAS `123-…`) | 59.0 (42.0 + 17.0); slots 82 %; MAS wall-clock per company +19 %. 500s = luppoapartments.fi `ERR_HTTP2_PROTOCOL_ERROR` ×8. Lost: luppo and 2 sites dropping our egress (lever 12). MAS `121-…`; ours `122-…` |
| 2026-11-04 | (between) | **ours: `0.9.5-http-as-asked`**, 17:20Z, in the same update as w4's release | | | | | | Tier 1 3/4: jpond.fi https timeout, unexplained, no path from the change found; 0 `render_timeout` on https in w5 |
| 2026-11-04 | w5 | none: a **repeat of w4** | 764 (10.19) | 113 + 4 / 8 (+ 2 × 400) | 0.054 (≈0.044 with a normal warm-up) | 0.55 (≈0.44) + 0.53 | 0 by MAS's rule | 82.0 (66.0 + 16.0), of which 24 a 12-min warm-up we caused. **The noise reading: ±10 %.** 500s = qaraton.com JS shell ×8; 400s = loopback DNS (lever 13). MAS `129-…`; ours `130-…` |

## Levers

Numbers are stable: messages and other docs cite them. A lever that's done says so.

1. **Pages per company: MAS's lever.** On a fixed fleet our cost per company follows MAS's
   wall-clock per company, and pages are most of that wall-clock. Our part is to price each window.
2. **Done: the fixed fleet** (w3, standing since w4). `batch-scale.sh fix N` / `release`. Next point
   if anyone wants it: 10+ in flight, sized with MAS first (3 replicas at 12 would be the guess).
   Not a sweep setting yet: an unannounced 1–5-in-flight production stream (from ≈11-08) runs
   unpinned, and pinning a floor around the clock costs ~$7/day per replica (AZURE_OPERATIONS §3.8).
3. **Scale-in kills in-flight renders** (AZURE_OPERATIONS §2.4; 2 of 814 in run (ii), retried). A
   fixed fleet can't scale in, so inside windows it's gone. It matters again for unannounced traffic
   from ≈11-08. **Verify the mechanism before writing anything:** production's SIGTERM path is
   supervisord → gunicorn master → uvicorn worker, with no `stopasgroup`, so a bare local uvicorn
   isn't that path. Reproduce it under supervisord. The suspect is Playwright's `handle_sigterm`.
   Any fix may be a launch option in an upstream-owned file (Principle 1).
4. **`delay_before_return_html: 2.0` is MAS's config and ~37 % of our mean render time**
   (AZURE_OPERATIONS §4.5). On a fixed fleet it matters only through MAS's wall-clock. Risk: pages
   that paint late come back thin. Canaries: MAS's "newly empty" count, and our `fixture_origin`
   `/hydrate-after/`. Their change, in a joint window.
5. **Browser identities.** MAS sends a per-company identity, so nearly every company launches its own
   browser (57–73 launches per 75 companies). A few shared identities would mean reuse, fewer
   launches and less memory. It's a contract change, so their call.
6. **Parked-domain truthfulness.** Parking pages and hosting placeholders come back 200 and MAS's
   agent calls them `blocked` (fortax.fi in run (ii); two parking pages in w3, `113-…`). A
   signature check, theirs or a class of ours, makes the outcome true. Size it on MAS's data first.
7. **A `contacts` field** (deterministic `mailto:`/`tel:`/pattern extraction before MAS's cleaner).
   MAS's cleaner lost 514 of 535 emails on one directory page. Their `task-438` decides whether they
   want it from us; it's additive for us.
8. **4 vCPU / 8 GiB replicas** (possible since the v2 environment, AZURE_OPERATIONS §3.6, untried).
   Only if memory starts costing work; it doubles the price per replica.
9. **Deterministic failures should be terminal: 200 with their own class, not a 500 retried four
   times.** Acked by MAS (`131-…`), to be deployed announced, with the class names in the
   announcement. Each costs ~8 renders per URL now (Chrome + Patchright, four attempts). In August,
   152 of 163 URLs that ever got a 500 got four in a row.
   - **Chrome's inline-PDF viewer shell** (356 bytes, 0 visible characters). Our detector calls it
     "blocked", and with no 403/503 that's `render_error`.
     `test_a_download_is_not_a_retryable_server_error[pdf-inline]` is already red for exactly this,
     on real Chrome. MAS's extension filter doesn't stop the agent fetching a `.pdf` URL it read in
     page text (`96-…`).
   - **A both-tiers-empty JavaScript shell:** 0 visible characters in Chrome *and* Patchright
     (getbutton.io/ai-chatbot, qaraton.com/team).
   - **`net::ERR_HTTP2_PROTOCOL_ERROR`**, the origin's broken HTTP/2. `classify_error_text` has no
     row for `ERR_HTTP2_`, so it lands in "ours, retryable". MAS's plain HTTP/2 GET to
     luppoapartments.fi worked, so the breakage is Chrome-only. A retry with HTTP/1.1 would recover
     that company; whether it's worth one is our call.
10. **A marked `http://` attempt when `https://` is refused at connect.** Task file:
    `https-connect-failure-http-retry.md`. Fast refusals only (lever 12 explains the slow ones). MAS
    acks the field name when we propose it.
11. **The pinning proxy dials only the first DNS answer** (`egress_broker.resolve_and_pin`). A host
    with a dead A record among good ones would fail where a browser tries the next. Real but
    unobserved: selosella.fi has one, yet its www name failed without one (lever 12 explains both).
    Upstream's code; check upstream before patching.
12. **Some hosts drop our Sweden Central egress** (AZURE_OPERATIONS §7). The A/B: one static request
    to jekura.fi timed out through `-se` and returned 200 through the West Europe app. A ~30 s
    tunnel timeout is the signature; ~1 s is a closed port 443 (lever 10).
    - **Size:** MAS counts companies with a tunnel failure at 2.4 % since the move (11 of 453),
      against 1.4 % before (396 of 28,568). Treat that as a lead. On a ≈9,500-company sweep, one
      point is ~100 companies lost for good.
    - **Options:**
      - (a) a marked fallback through the West Europe app for 30 s connect timeouts (MAS's
        preference and ours);
      - (b) a static egress address for `-se` (NAT gateway);
      - (c) move the crawler back to West Europe;
      - (d) residential egress.
    - **Decision: Tero and MAS's owner, not a window.** MAS holds the West Europe app past 11-11
      until then (`126-…`, their task-524).
13. **Loopback-resolving domains get `bad_request` 400.** smcbrandstore.fi resolves to 127.0.0.1, so
    the seed SSRF check refuses it (w5). The guard is right and the class is wrong: it's the origin's
    broken DNS, and like `OriginUnresolvable` (`api.py`) it should be 200 `origin_unreachable` on
    `/crawl`, keeping the opaque 400 on other endpoints. Acked by MAS (`131-…`). Tiny.

## Instruments worth keeping

- **The West Europe app as a second egress.** It answers "is it the site, or our Sweden Central
  addresses?" in one request (lever 12), and "is it the new image?" while it runs an older one. MAS
  holds it past 11-11. A same-region old-image arm would be a scale-to-zero second app in
  `aitosoft-aca-se`, at $0 idle; build it only when a question needs it.
- **A bare TCP connect from `az acr run`** (ACR is in West Europe): one SYN per host, no HTTP. It
  separates "the host drops us" from "the host is down" without loading a page.
- **The per-minute ingress table by replica count** (`ContainerAppHTTPLogs` `/crawl`,
  `bin(StartTime, 1m)`, `countif` 429, `dcount(ReplicaName)`). It found lever 2. Cast `StatusCode`
  with `toint()`, and don't name a column `kind`, `first` or `last` (KQL keywords): the query fails
  as "invalid properties".
- **630 real raw pages** from run (ii) (`tmp/research/tailloss-data-2026-11-04/`, kept by decision).
  The offline re-scrape corpus; `tmp/research/tailloss/tailloss.py` loads it.

## What I talked myself out of

- **Anti-bot or stealth work.** Blocks stayed ~0 terminal across ~5,000 requests. The losses that
  matter are egress addresses (lever 12) and deterministic page failures (lever 9), not
  fingerprints.
- **Trimming our markdown to save model cost.** Page content is about a quarter of a company's model
  cost on MAS's US host (`64-from-us-…`). It might matter for quality (lever 7), not money.
- **Changing the scale trigger.** The scaler is burst-driven, so a fixed fleet does what a trigger
  can't.
- **A floor-only warm replica.** It removes only the cold start, whose size varies 13–31 429s with
  nothing changed, so its effect sits inside the noise.
- **A #2416 patch.** 0 of 630 real pages change (FINDINGS §Parse collapse).

## What this file got wrong on 2026-11-04, and what caught it

1. **"Pin one warm replica"** was the shape of the failure. The per-minute table by replica count
   caught it.
2. **The first cost figures were ~11 % low**, read before the fleet reached zero. Re-reading at zero
   caught it.
3. **The unsplit `Replicas` metric averages overlapping revisions.** Caught at the deploy overlap;
   `replica-minutes.sh` splits by revision.
4. **"Cost per request is flat"** was luck in which fleet size the scaler picked. Window 2 caught it.
5. **"Releasing removes the tail."** The release revision starts its own replicas; the w3 replica
   list caught it.
6. **The selosella.fi stray-A-record explanation.** The www name, which has no stray record, caught
   it.
7. **"The traffic-weight log line confirms routing."** It isn't always written, and that cost
   window 5 twelve minutes.

## What I am least sure of

1. **Whether lever 12 is real at scale.** It rests on one A/B on one host and n = 11 in MAS's split.
   The per-host before/after query in MAS's archive decides it.
2. **Whether two replicas hold for a cohort with slow pages at 8 in flight.** Window 2's p90 was
   16.5 s at 5 in flight; at 8 the queue waits could push MAS's wall-clock past their break-even.
3. **That cohorts are comparable.** Each window is a different random draw. The rates compare; the
   pages don't. The ±10 % is one repeat, not a distribution.
4. **jpond.fi's https timeout after the second deploy.** One event, no path from the change found,
   0 https timeouts in window 5. If `render_timeout` on https ever rises, start there.
