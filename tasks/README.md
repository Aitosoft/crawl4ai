# Open tasks, in the order to do them

**Updated:** 2026-08-01, coordinator pass before the session run.
**This file holds ordering and gating only** — the reasoning lives in each task
file, the evidence in `waa-eval-2026-07-30-forensics.md`. If they disagree, the
task file wins and this index is stale; fix it.

Production is current (`0.9.2-failure-class`, rev `--0000031`). Nothing below is
a deploy blocker.

**The re-scrape re-ordered this list.** Three items moved down because the fixes
that shipped on 2026-07-30 took most of their value, and three new items moved to
the top because MAS measured defects we did not know about. Read §10 before
trusting any priority written before 2026-07-31. The old #0 (`fixture-origin.md`)
shipped the same day and is in `done/`; #1–#3 are what it was for.

**Standing rule as of 2026-07-31: live traffic is the last instrument, not the
first.** Every failure class since 2026-04 was diagnosed against a customer's
website, all of it leaving from one shared Azure address that is not contractually
ours, and MAS's requests and our test requests are the same egress. The fixture
origin (`done/fixture-origin.md`) removed the reason — it is now TESTING.md
golden rule 0. **Tasks #1–#3 were each drafted with live hits and each now needs
zero**; every one of them already has routes and, in two cases, a red test
waiting to be inverted. Add a route before you add a request.

**The order below is the session order.** #1–#4 are four sessions: two
investigations that produce numbers and no code, then two code tasks that ship in
**one image**. That grouping is load-bearing in both directions — #2's fix, if
small, joins #3+#4's deploy, and after that image ships the option is gone; and
#1+#2 together are what message 10 to MAS is waiting on.

| # | Task | Gate | Why here |
|---|------|------|----------|
| 1 | `challenge-interstitial-resolve.md` | none — **experiment first, no code** | 202 turns out to be the challenge layer's code, and it serves both the interstitial and the real page. If we are capturing the interstitial, 23 of the 31 blocked hosts may come back for free and the proxy question shrinks to 4. The fixture already pins both halves (interstitial at a 0.1 s wait, real page at 2.0 s, same 202); phase 1 owes the curve between them. **First because MAS is holding their capture-timing design for it** — it is the only open item blocking another team. |
| 2 | `render-500-window-2026-07-31.md` | none — logs only, **zero traffic** | **Cause found 2026-08-01, fix not designed.** All 9 × 500 are our own memory guard (`crawler_pool.py:179`) refusing to create a browser at our own 85 % threshold — while the process held 235 MB on a 4 GiB replica. Every one landed on a scale-out step (2→4 replicas, then 4→6), which is what the sweep does continuously, and it arrives as the one status MAS retries 3×. Both of MAS's questions are answered by it: **the 9 never reached the origin (246 hits, not 255)** and **the clustering is the ramp**. |
| 3 | `cleaned-html-collapse-guard.md` | none | Second silent whole-body loss in a month; the first ran 3½ months across 406 pages at `success: true`. **A third is already reproduced offline** — `/collapse/unclosed-noscript` loses the whole body through the real production path. Enumerate through the browser, not only through libxml2 — that is what hid this one. Also fixes the `render_error` wire-status split it uncovered. **Do not deploy alone.** |
| 4 | `detector-round3-evidence-vs-inference.md` | none | Eight hosts measured in prod: four blocks missed (every size gate is on `len(html)`; the vendor pads to 80 KB), four invented (including our own error placeholder reported as the origin blocking us). Defect A has a red test; so does the unmarked-interstitial variant. **Ships #3's image**; gates #6. |
| 5 | `static-fallback-within-fence.md` | none — re-price, likely close | **Drop, not build**, on current evidence. MAS's probe: 0 × 504, nothing within 145 s of the 180 s fence — consistent with `done/render-retry-unbounded-hang.md` having removed the failure this was sized against. 243 fetches is not a workload, but it is the only dataset the current image has seen. |
| 6 | `preflight-batch-endpoint.md` | #4, then MAS's go-ahead | **Do not build speculatively — their words, and now formally answered.** There is no sweep date and timing is not their driver; it runs when their system is ready. They will give real notice. |
| 7 | `blocked-host-retry-economy.md` | none | Still real, but smaller: MAS no longer retries origin-class failures, so a blocked host costs ~4 page loads, not ~12–16. Our half is now **measured, not inferred**: exactly 2 document loads per request (first-tier render + patchright retry), via `FixtureOrigin.hits_for()` against `/block/varnish-403`. Its classifier is still #9's trigger. |
| 8 | `base-config-boolean-defaults-never-applied.md` | none | `simulate_user` has never taken effect and the next boolean won't either. Small. Decide whether the setting should exist at all rather than restoring an intent nobody measured. |
| 9 | `residential-egress-retry-path.md` | **#1's outcome, then Tero** | On hold. The population is 31, not 3 — an order of magnitude more than we told Tero on 2026-07-30. But ≤8 of those may survive #1, and no one on either side has evidence a residential IP gets through. We can now test that for free: the dev container egresses from a Finnish consumer ISP. |
| 10 | `static-mode-tls-impersonation.md` | #1, #9 | Hardens the path #5 makes everything fall back to. IP has dominated fingerprint in every case measured so far; #1 and #9 are what would change that. |
| 11 | `pool-browser-retains-last-page.md` | none | One document's memory pinned per browser. Was "low impact"; **#2 makes it worth re-reading** — a memory guard now demonstrably refuses work, the pool created 125 browsers for ~252 requests, and this is why our memory numbers have never been readable. Do not merge it into #2, but read it there. |
| — | `antibot-minimal-text-false-positive.md` | — | **Merged into #4** — the latent defect was observed live (`norex.com`). Close it when #4 ships. |
| — | `file-upstream-prs.md` | upstream | Standing tracker, four PRs open. Small `fix(docker):` PRs merge in 1–5 days; core behavioural changes sit for months — expect no movement. |
| — | `waa-eval-2026-07-30-forensics.md` | — | Reference, not a task. Never close it; task files cite it instead of re-deriving. |

## Cross-repo state

MAS (`aitosoft-platform`) is our only consumer. The exchange is markdown files in
gitignored `tmp/mas-repo-messages/`, numbered and direction-labelled, relayed by
Tero both ways. Durable conclusions get copied into the forensics record; the
messages are the transcript, not the source of truth.

Settled 2026-07-31 (their message 07):

- **Envelope `success`:** flip it to the aggregate, **conditional on the HTTP
  wire status staying 200**. That condition is the load-bearing half. Shipping in
  #3.
- **Their `DEGENERATE_CAPTURE_CHARS = 500` floor is 500 markdown characters**,
  not HTML bytes. The unit hazard is live — we reason in HTML bytes, they store
  markdown. Name the unit every time.
- They now store `cleaned_html` alongside markdown when a capture comes back
  degenerate, which removes the round-trips that dominated 2026-07-30.

Settled 2026-07-31 (their message 09), and it reframes the contract:

- **The wire status is the contract; `failure_class` is documentation.** Their
  retry branch is `retryableStatuses.includes(response.status)`, evaluated before
  the body is parsed — `failure_class` is received, logged and unread. So a
  detected collapse goes out as **HTTP 200 + result-level `success: false`**, the
  shape `savaterra.fi` proved end to end at zero retries. Never behind 500/502/503.
- **`render_error` is currently served at two wire statuses.** Static mode returns
  it inside a 200 (`aitosoft_static_mode.py:316` — static never raises), full mode
  at 500. Same class, opposite retry behaviour, decided by `render_mode`.
  Ours to fix, in #2.
- **They have had zero production traffic since our deploy** — 86 WAA runs on
  2026-07-30, all before 18:24 UTC, none since. Their 243-host probe is the only
  workload the current image has seen. Do not read their silence as "seeing none".
- **No sweep date, and that is deliberate.** It runs when their system is ready.
- **The shared-egress finding landed on their side too**, with a consequence we
  had not drawn: a residential-vendor probe *run from our egress cannot answer the
  question it exists to answer*. They have marked their residential analysis
  part-superseded and will bring us the sweep's shape — waves, concurrency,
  per-host spacing — before wave 1.

Found on our side 2026-08-01 (coordinator pass, logs only — see #2):

- **The 9 × 500 were our memory guard, not a render failure.** `crawler_pool.py:179`
  refuses to create a browser at `memory_threshold_percent: 85.0`; the readings
  were 85.1–95.6 % while the process held 204–235 MB on a 4 GiB replica. The
  reading and the process cannot both be describing the same memory.
- **"We are full" is answered with two different wire statuses**, exactly like
  `render_error`: RenderGate says 429 + `Retry-After`, the memory guard says 500,
  and 500 is the one MAS retries three times. Memory pressure currently
  multiplies its own load by four.
- **The pool barely reuses**: 125 browser creations against 53 cold-pool reuses
  across ~252 requests. Worth checking whether per-company `browser_config` —
  their contract — produces a distinct pool signature per request. At 15,000
  companies that would be 15,000 signatures.

Owed to MAS, to go out together as message 10 once #1 and #2 land:

- **The 202 result, either way** — they are holding their capture-timing design
  for it and have explicitly not shipped a global wait. **The only one still
  genuinely unknown**, and the reason message 10 waits at all.
- **The wire status we will serve the collapse guard at** (decided: 200 — but
  send it when it ships, with the `render_error` split fixed alongside).
- **Whether the 9 × 500 reached the origin — ANSWERED 2026-08-01: they did not.**
  The memory guard raises before the browser is created, so no navigation
  happened. **Their day cost 246 origin hits, not 255.** Under the shared-egress
  finding this is our number to produce, and it is produced.
- **Whether the 04:46–04:50 clustering means anything — ANSWERED: yes, and it is
  not a per-host rate.** All nine 500s land on the two scale-out steps and none
  anywhere else. They were right to flag it and right not to interpret it.
- **`fodbar.fi`:** they agree we should report the origin's status rather than
  overrule a 403 that serves content, and would like a small field saying *content
  was present despite the origin status* — moving the decision to their side,
  where 117,000 stored pages are. Cheap; fold into #3.
