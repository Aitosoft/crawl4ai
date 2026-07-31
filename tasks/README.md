# Open tasks, in the order to do them

**Updated:** 2026-07-31, after the fixture origin shipped.
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

| # | Task | Gate | Why here |
|---|------|------|----------|
| 1 | `challenge-interstitial-resolve.md` | none — **experiment first** | 202 turns out to be the challenge layer's code, and it serves both the interstitial and the real page. If we are capturing the interstitial, 23 of the 31 blocked hosts may come back for free and the proxy question shrinks to 4. The fixture already confirms both halves are reproducible (interstitial at a 0.1 s wait, real page at 2.0 s, same 202); what phase 1 owes is the number against the real families. |
| 2 | `cleaned-html-collapse-guard.md` | none | Second silent whole-body loss in a month; the first ran 3½ months across 406 pages at `success: true`. **A third is already reproduced offline** — `/collapse/unclosed-noscript` loses the whole body, and it matches `apteam.fi`'s fingerprint. Enumerate through the browser, not only through libxml2 — that is what hid this one. |
| 3 | `detector-round3-evidence-vs-inference.md` | none | Eight hosts measured in prod: four blocks missed (every size gate is on `len(html)`; the vendor pads to 80 KB), four invented (including our own error placeholder reported as the origin blocking us). Defect A has a red test; so does the unmarked-interstitial variant of it. Gates #6. |
| 4 | `render-500-window-2026-07-31.md` | none — logs + correlation IDs, **zero traffic** | 9 of MAS's 252 probe requests were our HTTP 500s, and **5 of the 70 hosts probed in one 4½-minute window failed while 0 of the other 173 did**. A per-host property does not cluster like that; a property of our replicas at that moment does — and the window sits ~90 s into a burst at a service that scales to zero. That is the exact condition the sweep creates. Also answers two questions MAS asked us. |
| 5 | `static-fallback-within-fence.md` | #4 | Likely **drop, not build**. MAS's probe: 0 × 504, and nothing came within 145 s of the 180 s fence — consistent with `done/render-retry-unbounded-hang.md` having removed the failure this was sized against. 243 fetches is not a workload; #4 is where the verdict gets written. |
| 6 | `preflight-batch-endpoint.md` | #3, then MAS's go-ahead | **Do not build speculatively — their words.** There is no sweep date and timing is not their driver; it runs when their system is ready. They will give real notice. |
| 7 | `blocked-host-retry-economy.md` | none | Still real, but smaller: MAS no longer retries origin-class failures, so a blocked host costs ~4 page loads, not ~12–16. Our half is now **measured, not inferred**: exactly 2 document loads per request (first-tier render + patchright retry), via `FixtureOrigin.hits_for()` against `/block/varnish-403`. Its classifier is still #9's trigger. |
| 8 | `base-config-boolean-defaults-never-applied.md` | none | `simulate_user` has never taken effect and the next boolean won't either. Small. Decide whether the setting should exist at all rather than restoring an intent nobody measured. |
| 9 | `residential-egress-retry-path.md` | **#1's outcome, then Tero** | On hold. The population is 31, not 3 — an order of magnitude more than we told Tero on 2026-07-30. But ≤8 of those may survive #1, and no one on either side has evidence a residential IP gets through. We can now test that for free: the dev container egresses from a Finnish consumer ISP. |
| 10 | `static-mode-tls-impersonation.md` | #1, #9 | Hardens the path #5 makes everything fall back to. IP has dominated fingerprint in every case measured so far; #1 and #9 are what would change that. |
| 11 | `pool-browser-retains-last-page.md` | none | One document's memory pinned per browser. Low impact, but it is why our memory numbers have never been readable. |
| — | `antibot-minimal-text-false-positive.md` | — | **Merged into #3** — the latent defect was observed live (`norex.com`). Close it when #3 ships. |
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

Owed to MAS, to go out together as message 10 once #1 and #4 land:

- **The 202 result, either way** — they are holding their capture-timing design
  for it and have explicitly not shipped a global wait.
- **The wire status we will serve the collapse guard at** (decided: 200 — but
  send it when it ships, with the `render_error` split fixed alongside).
- **Whether the 9 × 500 reached the origin**, from the correlation IDs. It changes
  *their* site-safety ledger: 255 origin hits if `render_error` fires after the
  fetch, 246 if before.
- **Whether the 04:46–04:50 clustering means anything on our side.** They would
  rather know before reading a 3.6 % rate into anything.
- **`fodbar.fi`:** they agree we should report the origin's status rather than
  overrule a 403 that serves content, and would like a small field saying *content
  was present despite the origin status* — moving the decision to their side,
  where 117,000 stored pages are. Cheap; fold into #3.
