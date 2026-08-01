# Open tasks, in the order to do them

**Updated:** 2026-08-01, after the four-item image shipped (#1 phase 2, #2's S
half, #3 part 1, #4). Items 1-4 are **done or reduced**; the table below is
re-ordered around what is left.

**What that image taught, and it is the fourth session in a row to teach it:**
the task file was materially wrong about something load-bearing. #4's file said
"the four caught hosts prove the pattern side already works", so moving the
size gates would be enough — measured, **no pattern matched that body at all**;
they were caught by a status rule, and half the fix was missing from the
specification. Its fixture was also unfaithful on the one axis that decided the
answer. **Verify the diagnosis, not just the plan**: for a detector claim that
means asserting *which branch fired*, not that a verdict was returned.
**This file holds ordering and gating only** — the reasoning lives in each task
file, the evidence in `waa-eval-2026-07-30-forensics.md`. If they disagree, the
task file wins and this index is stale; fix it.

**Standing rule since 2026-07-31: live traffic is the last instrument, not the
first.** Every failure class since 2026-04 was diagnosed against a customer's
website, all of it leaving from one shared Azure address that is not
contractually ours, and MAS's requests and our test requests are the same
egress. The fixture origin (`done/fixture-origin.md`) removed the reason — it is
now TESTING.md golden rule 0. **The four items in the image below cost zero live
requests between them**, investigation and implementation alike; the only live
traffic was the Tier 1 regression that gates the deploy. Add a route before you
add a request — and check `test-aitosoft/artifacts/` before you add a route,
since the second instance of the detector defect was already sitting there.

## Shipped 2026-08-01 — one image, four items

`0.9.2-detector-round3`, revision `--0000032`, deployed and smoke-tested
2026-08-01. Closed: `challenge-interstitial-resolve.md` (both
phases), `detector-round3-evidence-vs-inference.md`,
`antibot-minimal-text-false-positive.md`, and the S half of
`render-500-window-2026-07-31.md`. `cleaned-html-collapse-guard.md` part 1 is
deployed; **part 2 (root cause, three separate repairs) stays open** and is #1
below.

Four results worth carrying forward:

- **Detection widened and invention narrowed, in the same deploy, on purpose.**
  A block page padded to 80 KB at status 202 is now caught as *evidence*
  (`origin_blocked`); a verdict derived from an empty-looking page is now
  *ours* (`render_error`). The unpadded form of the same page proves they
  compose: without the new tier it would have flipped from `origin_blocked` to
  `render_error` — a real block reported as our bug.
- **A real second instance was sitting in `test-aitosoft/artifacts/`.**
  `monidor.com`, a stored capture returned to MAS at `success: true`, is an
  11,515-byte interstitial with 58 characters of text. We had the evidence for
  weeks. **Check the corpus we already hold before designing against a fixture.**
- **Phase 2 rescues slow-hydrating shells, not just challenges** — MAS's
  `revisol.fi` class, absorbed server-side at zero extra page loads. Nobody
  predicted this; a test went green on its own and the reason was worth having.
- **The cost of #4 defect B, stated:** two of MAS's four cases move from a
  terminal 200 to a retried 500. Correct direction, real cost. Watch it in the
  next sweep.

| # | Task | Gate | Why here |
|---|------|------|----------|
| 1 | `cleaned-html-collapse-guard.md` **part 2** | none | **Part 1 DONE and DEPLOYED 2026-08-01.** Guard ships as visible-text-in vs markdown-out — **not** the `cleaned_html` ratio the file proposed, refuted twice by measurement. `render_error` wire-status split fixed; one mapping site for both render modes. **Root cause NOT solved: four shapes, three mechanisms**, and `apteam.fi`'s fingerprint fits at least two — part 2 is three separate repairs, sequenced in the task file. Their `revisol.fi` half shrank for free when #1's phase 2 shipped. |
| 2 | `static-fallback-within-fence.md` | none — re-price, likely close | **Drop, not build**, on current evidence. MAS's probe: 0 × 504, nothing within 145 s of the 180 s fence — consistent with `done/render-retry-unbounded-hang.md` having removed the failure this was sized against. 243 fetches is not a workload, but it is the only dataset the current image has seen. |
| 3 | `preflight-batch-endpoint.md` | **#4 is done — MAS's go-ahead is now the only gate** | **Do not build speculatively — their words, and now formally answered.** There is no sweep date and timing is not their driver; it runs when their system is ready. They will give real notice. |
| 4 | `blocked-host-retry-economy.md` | none | Still real, but smaller: MAS no longer retries origin-class failures, so a blocked host costs ~4 page loads, not ~12–16. Our half is now **measured, not inferred**: exactly 2 document loads per request (first-tier render + patchright retry), via `FixtureOrigin.hits_for()` against `/block/varnish-403`. Its classifier is still #8's trigger. |
| 5 | `base-config-boolean-defaults-never-applied.md` | none | `simulate_user` has never taken effect and the next boolean won't either. Small. Decide whether the setting should exist at all rather than restoring an intent nobody measured. |
| 6 | `pool-residency-unbounded.md` | none — but design with #7 | **New 2026-08-01, the M half carved out of #2.** `render_capacity` bounds renders and `max_pages` bounds pages; **nothing bounds live browsers**, so 8 were held to do 2 renders' worth of work at a measured 139–165 MB each (~130 MB of it unreclaimable `anon`). The janitor's adaptive TTL then thrashes it — 125 creates and 132 closes for 10–12 signatures — by launching browsers precisely when memory is tight. Needs a `max_browsers` cap with LRU eviction, priced together with #7. |
| 7 | `pool-browser-retains-last-page.md` | none | One document's memory pinned per browser. Was "low impact"; **the memory work makes it worth re-reading** — per-browser cost is now measured (139–165 MB cgroup, of which a stable 130 MB is `anon`) and this is a term in it. It sets the right cap in #6, so price the two together. |
| 8 | `residential-egress-retry-path.md` | **phase 2 has shipped — MAS's next sweep, then Tero** | On hold, and the population is now derived rather than asserted: **floor 6, ceiling 29** (4 of the 33 verdicts are our own false positives and belong to #4; 4 are a hard 403 template no wait can fix; 23 are undetermined until #1 phase 2 ships). Phase 1 did **not** shrink it — it made the 23 measurable for free. Still no evidence on either side that a residential IP gets through; the dev container's Finnish consumer ISP egress can test that when the count is real. |
| 9 | `static-mode-tls-impersonation.md` | #8 | Hardens the path #2 makes everything fall back to. IP has dominated fingerprint in every case measured so far; #8 is what would change that. |
| — | `challenge-interstitial-resolve.md` | **DONE 2026-08-01, both phases** | Phase 1's number — a capture wait `W` gets any challenge resolving within **`W + 1.22 s`** — turned out to be the whole design. Phase 2 is one config value: the patchright retry (which already runs for every detected block) now waits 10 s instead of inheriting the request's 2.0. Zero extra page loads. **Retry leg measured at 11.26 s = `W + 1.22`**, answering phase 1's own footnote. Unpriced dividend: it also rescues slow-hydrating shells, i.e. MAS's `revisol.fi` class. It cannot reach interstitials we do not detect — which is why #4 shipped beside it. |
| — | `render-500-window-2026-07-31.md` | **S half DONE 2026-08-01**; M1 is #6 | All 9 × 500 were our own memory guard at our own 85 % threshold, on **one replica carrying the burst alone for 122 s after a scale-from-zero**. Shipped: S1 the refusal is now **429 + `Retry-After`**, not the 500 MAS retries 3× (memory pressure was quadrupling its own load); S2 the reading is the working set and the anon/file split is logged; S3 the permanent browser — **0 hits in 224 pool gets** — is closed when unused. MAS answers for message 10: **246 origin hits, not 255**, and the clustering is scaling lag, not a scale-out ramp. |
| — | `detector-round3-evidence-vs-inference.md` | **DONE 2026-08-01** | Eight hosts measured in prod: four blocks missed, four invented. **Its own file was wrong about the fix** — no pattern matched the missed body at all, so moving the size gates closed nothing and a new block-notice tier was needed; and a naive text gate would have re-opened MAS's Shopify false-positive family, whose fixture has 247 visible chars. Both defects shipped together because they cancel otherwise: the unpadded block page would have flipped from `origin_blocked` to `render_error`. |
| — | `antibot-minimal-text-false-positive.md` | — | **CLOSED 2026-08-01** — the latent defect was observed live (`norex.com`: our own placeholder reported as the origin blocking a customer) and is fixed by #4 defect B. Moved to `done/`. |
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

Owed to MAS as message 10. **#1 and #2 have now landed and the image has
shipped, so nothing gates this message any more** — every item below is final:

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
  "content was present despite the origin status" field. The field was
  conditional on message 10 describing it first; message 10 had not gone out
  when the image was ready, so per that condition it was dropped rather than
  delaying the deploy. Both are additive. Propose them in message 10 and ship
  them together afterwards, in their own change where a surprise is attributable.
- **The detector now catches two classes it used to store as content, and
  invents one class fewer** (shipped 2026-08-01). Tell them:
  (a) a block page padded past our size gates — their four 202 hosts — is now
  `origin_blocked`; (b) four of their 33 `origin_blocked` verdicts were our
  inference, not the origin, and two of those (`norex.com`,
  `jarvenkylamaatila.fi`) now arrive as **`render_error` at HTTP 500, which they
  retry 3x** — a real cost we chose deliberately, because the alternative was
  telling them a healthy host is permanently blocked; (c) `snuup.fi` is now
  `origin_http_error`, still terminal; (d) `fodbar.fi` is unchanged, as agreed.
- **Ask them to count the silent family.** We still cannot detect an
  interstitial that carries no marker, no interstitial prose and no refusal
  notice, and we cannot count it either — any rule that caught it would be the
  same inference we just removed. Their stored corpus can: a page under ~500
  markdown characters whose HTML carries a challenge asset. That number sizes
  the remaining gap for both sides and is the one thing we cannot produce.
- **Memory-pressure refusals now arrive as 429 + `Retry-After`, not 500.**
  Their client already backs off correctly, so nothing breaks, but on a cold
  first wave a single replica can answer a burst of them. That is right
  behaviour and still looks like a stall from their side. Send it with the
  scale-from-zero finding — the two are the same event seen from either end —
  and say plainly that the 429 makes the symptom cheap without removing the
  cause.
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
  makes the symptom cheap without removing the cause (`pool-residency-unbounded.md` is the cause).
