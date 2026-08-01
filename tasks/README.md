# Open tasks, in the order to do them

**Updated:** 2026-08-01, after the #2 verification session (which corrected the
coordinator pass that preceded it — see #2 and forensics §11e).
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

**The order below is the session order.** #1–#4 were four sessions: two
investigations that produce numbers and no code, then two code tasks that ship in
**one image**. That grouping is load-bearing in both directions — #2's fix, if
small, joins #3+#4's deploy, and after that image ships the option is gone.

**Updated 2026-08-01: #1's investigation half is done and its code half shrank to
S**, so the image is now #1-phase-2 + #2 + #3 + #4, not #3 + #4. Both
investigations produced a decisive **negative** alongside their number (#1: the
`page.content()` nav race costs no captures; #2: the 500s never reached the
origin), which is worth as much to MAS as the positives and should be sent with
the same confidence.

**Updated 2026-08-01 (later): #2 is diagnosed and split.** Its S half (wire
status, reading, the never-used permanent browser) ships in that image; its M
half is the new #11. **Message 10 is unblocked** — both MAS answers are final,
but one of them changed between passes, so send the version in #2 and not the
coordinator's. That two of three coordinator claims on #2 were wrong for one
reason — an unfiltered workspace-wide log query — is written up in forensics
§11e; it is the reusable part.

| # | Task | Gate | Why here |
|---|------|------|----------|
| 1 | `challenge-interstitial-resolve.md` | **phase 1 DONE 2026-08-01**; phase 2 ships with #3+#4 | **The number: a capture wait `W` gets any challenge resolving within `W + 1.22 s`; MAS's 2.0 covers 3.2 s.** One constant, 0/84 mispredictions, zero live requests. Phase 2 is a **go but S, not M** — `maybe_retry_blocked` already re-fetches every detected block with the *same* wait, so it needs a longer wait, not a new mechanism. Two negatives worth the same weight: the `page.content()` nav race cost **no** captures (42/42 identical), and an adaptive shape inherits the detector's recall, so the unmarked interstitial gets nothing. **Message 10 is now unblocked.** |
| 2 | `render-500-window-2026-07-31.md` | none — logs only, **zero traffic** | **Diagnosed and fix designed 2026-08-01; the S half is written, not yet coded.** All 9 × 500 are our own memory guard (`crawler_pool.py:179`) at our own 85 % threshold. The 235 MB was never the container — it is the gunicorn worker's RSS, and Chrome is child processes (measured: **+2 MB worker RSS vs +139–165 MB cgroup per pooled browser**, ~130 MB of it unreclaimable `anon`), so the reading is roughly right and the memory was scarce. **All nine are on one replica that carried the burst alone for 122 s after a scale-from-zero** — not a scale-out ramp, which is what the first pass said. Real cause: **nothing bounds live browsers** (125 creates / 132 closes for 10–12 signatures). **S1 status code + S2 reading + S3 the never-used permanent browser ship with #3+#4; M1 pool cap is carved out.** MAS answers: **246 origin hits, not 255**, and the clustering is scaling lag. |
| 3 | `cleaned-html-collapse-guard.md` | none | **Part 1 DONE 2026-08-01, landed not deployed.** Guard ships as visible-text-in vs markdown-out — **not** the `cleaned_html` ratio the file proposed, which was refuted twice by measurement (it fires on a healthy 73 KB page, and is blind to `unterminated-comment`, which keeps 74,523 B of `cleaned_html` *containing the content* and still yields no markdown). Thresholds measured against 37 stored real captures, zero live requests. `render_error` wire-status split fixed; one mapping site for both render modes. **Root cause NOT solved — the file's "probably already found" was an inference and it is wrong: four shapes, three mechanisms.** Part 2 is now three separate repairs, sequenced in the task file. **Do not deploy alone.** |
| 4 | `detector-round3-evidence-vs-inference.md` | none | Eight hosts measured in prod: four blocks missed (every size gate is on `len(html)`; the vendor pads to 80 KB), four invented (including our own error placeholder reported as the origin blocking us). Defect A has a red test; so does the unmarked-interstitial variant. **Ships #3's image**; gates #6. |
| 5 | `static-fallback-within-fence.md` | none — re-price, likely close | **Drop, not build**, on current evidence. MAS's probe: 0 × 504, nothing within 145 s of the 180 s fence — consistent with `done/render-retry-unbounded-hang.md` having removed the failure this was sized against. 243 fetches is not a workload, but it is the only dataset the current image has seen. |
| 6 | `preflight-batch-endpoint.md` | #4, then MAS's go-ahead | **Do not build speculatively — their words, and now formally answered.** There is no sweep date and timing is not their driver; it runs when their system is ready. They will give real notice. |
| 7 | `blocked-host-retry-economy.md` | none | Still real, but smaller: MAS no longer retries origin-class failures, so a blocked host costs ~4 page loads, not ~12–16. Our half is now **measured, not inferred**: exactly 2 document loads per request (first-tier render + patchright retry), via `FixtureOrigin.hits_for()` against `/block/varnish-403`. Its classifier is still #9's trigger. |
| 8 | `base-config-boolean-defaults-never-applied.md` | none | `simulate_user` has never taken effect and the next boolean won't either. Small. Decide whether the setting should exist at all rather than restoring an intent nobody measured. |
| 9 | `residential-egress-retry-path.md` | **#1 phase 2, then MAS's next sweep, then Tero** | On hold, and the population is now derived rather than asserted: **floor 6, ceiling 29** (4 of the 33 verdicts are our own false positives and belong to #4; 4 are a hard 403 template no wait can fix; 23 are undetermined until #1 phase 2 ships). Phase 1 did **not** shrink it — it made the 23 measurable for free. Still no evidence on either side that a residential IP gets through; the dev container's Finnish consumer ISP egress can test that when the count is real. |
| 10 | `static-mode-tls-impersonation.md` | #1, #9 | Hardens the path #5 makes everything fall back to. IP has dominated fingerprint in every case measured so far; #1 and #9 are what would change that. |
| 11 | `pool-residency-unbounded.md` | none — but design with #12 | **New 2026-08-01, the M half carved out of #2.** `render_capacity` bounds renders and `max_pages` bounds pages; **nothing bounds live browsers**, so 8 were held to do 2 renders' worth of work at a measured 139–165 MB each (~130 MB of it unreclaimable `anon`). The janitor's adaptive TTL then thrashes it — 125 creates and 132 closes for 10–12 signatures — by launching browsers precisely when memory is tight. Needs a `max_browsers` cap with LRU eviction, priced together with #12. |
| 12 | `pool-browser-retains-last-page.md` | none | One document's memory pinned per browser. Was "low impact"; **#2 and #11 make it worth re-reading** — per-browser cost is now measured (139–165 MB cgroup, of which a stable 130 MB is `anon`) and this is a term in it. It sets the right cap in #11, so price the two together. |
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

Found on our side 2026-08-01 (logs + offline probe, zero traffic — see #2 and
forensics §11; the coordinator's first pass on this is superseded):

- **The 9 × 500 were our memory guard, not a render failure.** `crawler_pool.py:179`
  refuses to create a browser at `memory_threshold_percent: 85.0`; the readings
  were 85.1–95.6 %.
- **The 235 MB and the cgroup reading were never measuring the same memory.**
  `server_peak_memory_mb` is the gunicorn worker's RSS (`api.py:105`) and Chrome
  is ~7 child processes per browser. Measured on the real path: **+2.0 MB worker
  RSS vs +139–165 MB cgroup per pooled browser**, of which a stable **130 MB is
  `anon`**. So the reading is roughly right and the memory was scarce; the page
  cache term is a one-time cold-container fill (27 MB/browser cold, 1.8 warm),
  not the story.
- **"We are full" is answered with two different wire statuses**, exactly like
  `render_error`: RenderGate says 429 + `Retry-After`, the memory guard says 500,
  and 500 is the one MAS retries three times. Memory pressure currently
  multiplies its own load by four.
- **It was scale-from-zero, not scale-out.** The app was at zero replicas at
  04:40; all nine 500s are on the one replica that came up at 04:44:49, and the
  second replica served its first render at 04:46:54 — after eight of the nine.
- **Nothing bounds the number of live browsers.** `render_capacity` bounds
  renders and `max_pages` bounds pages; residency is governed by idle TTL alone,
  so 8 browsers were held to do 2 renders' worth of work. 125 creates and 132
  closes for **10–12 distinct signatures per replica** — so per-company
  `browser_config` does *not* defeat pooling, and the "15,000 signatures" worry
  is unfounded. Carved out as M1.
- **The permanent browser is never used** — 0 hits in 224 pool gets, because MAS
  always sends a `browser_config`. ~130 MB of `anon` per replica, for its whole life.

Found on our side 2026-08-01 (#3 part 1, offline, zero traffic):

- **Four markup shapes swallow the body, not one**, by three distinct mechanisms,
  all deterministic. `deep-nesting` is **harmless at 1.5 KB and fatal at 73 KB** —
  enumerating unpadded misses root causes, not just thresholds. `apteam.fi`'s
  fingerprint fits at least two of them, so the cause is still unknown; their
  bytes are now worth asking for to pick which repair goes first.
- **A collapse guard cannot be an HTML-byte ratio.** The healthy control padded
  to 73 KB gives the same 0.0036 `cleaned_html` ratio as the collapsed page, and
  `accountor.com`'s real cookie wall is 99,649 → 230. Text-to-text is the only
  measure that separates them.
- **`bad_request` was one line from becoming a retried 500.** Static mode attaches
  it to a result when the egress broker refuses a redirect hop; its unconditional
  200 was making "MAS must never retry it" true by accident. Caught before
  shipping, now in `NON_RETRYABLE_CLASSES`.
- **`test_the_wall_clock_fence_is_a_504_and_ours` is load-flaky** (pre-existing,
  untouched by #3): it asserts `elapsed_s < 3` against a 1 s fence, so ~2 s of
  pool + page + teardown overhead has to fit, and a fully-loaded suite run
  sometimes does not. Failed once in three full runs. Not diagnosed — someone
  should either widen the margin deliberately or measure fence latency separately
  from harness overhead.

Owed to MAS, to go out together as message 10 once #1 and #2 land:

- **The 202 result — ANSWERED 2026-08-01, offline.** `W + 1.22 s` is the capture
  budget; their 2.0 covers a 3.2 s challenge, which confirms the bottom of their
  own 3–5 s `raw://` figure and refutes the top. **Tell them not to raise it
  globally**: at ~120,000 fetches, 2.0 → 10.0 is 267 render-hours, and a blocked
  host pays the raise *twice* because our patchright retry re-fetches with the
  same config. We do the targeted version server-side for 8–36 render-hours and
  zero extra page loads. Caveat to send with it: it cannot rescue interstitials
  we do not detect, and only their stored corpus can size that class.
  Also worth telling them: `delay_before_return_html` is already
  per-request-settable, so a per-host value on their side needs no deploy from us.
- **The wire status we will serve the collapse guard at — BUILT 2026-08-01.**
  HTTP 200 + result-level `success: false` + `failure_class: render_defect`,
  content still attached. The `render_error` split is fixed in the same change:
  one mapping site, both render modes. Send when the image ships. Tell them the
  new class is **ours and permanent** — the distinction the taxonomy was missing
  is permanence, not ownership.
- **Two things we did NOT bundle**, both agreed with them and both deliberately
  held back: flipping envelope `success` to the aggregate (their own message 09
  says they never read it for 2xx, and it breaks a pinned contract in an image
  already changing static mode's wire status), and the `fodbar.fi`
  "content was present despite the origin status" field (a new contract field
  should arrive with a message, not inside an image about something else).
  Propose both in message 10 and ship them together afterwards.
- **Whether the 9 × 500 reached the origin — ANSWERED 2026-08-01: they did not.**
  The memory guard raises before the browser is created, so no navigation
  happened. **Their day cost 246 origin hits, not 255.** Under the shared-egress
  finding this is our number to produce, and it is produced.
- **Whether the 04:46–04:50 clustering means anything — ANSWERED: yes, and it is
  not a per-host rate.** All nine are on a single replica that absorbed the
  opening burst alone for 122 s, because the service was scaled to zero when
  their probe started and the second replica did not serve until 04:46:54. It is
  scaling lag, **not** a scale-out ramp — an earlier draft of this answer said
  the latter; do not send that version. They were right to flag it and right not
  to interpret it.
- **`fodbar.fi`:** they agree we should report the origin's status rather than
  overrule a 403 that serves content, and would like a small field saying *content
  was present despite the origin status* — moving the decision to their side,
  where 117,000 stored pages are. Cheap; fold into #3.
- **A second source of 429 is coming, and they should hear it before it lands.**
  Once #2's S half ships, memory-pressure refusals arrive as **429 +
  `Retry-After`** instead of 500. Their client already backs off correctly on
  429, so nothing breaks — but the *shape* changes: on a cold first wave a single
  replica can answer a burst of them, which is right behaviour and still looks
  like a stall from their side. Send it with the scale-from-zero finding, since
  the two are the same event seen from either end, and say plainly that the 429
  makes the symptom cheap without removing the cause (#11 is the cause).
