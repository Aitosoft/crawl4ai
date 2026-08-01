# Open tasks, in the order to do them

**Updated:** 2026-08-02 by the coordinator, after a deliberate scope cut from
nine open items to three. Read "The scope cut" below before picking anything up
— several files still on disk are **parked on purpose**, not waiting for a free
session. Row numbers are not stable across revisions; cross-references name the
task file, never the number.

**This file holds ordering, gating and current state.** The reasoning lives in
each task file, the evidence in `waa-eval-2026-07-30-forensics.md`. If a task
file and this index disagree, **the task file wins and this index is stale** —
fix it.

## Where we actually are

**The service works.** Production is `0.9.2-detector-round3`, revision
`--0000032`, 2 vCPU / 4 GiB, `minReplicas: 0`, health 200. On MAS's 243-host
probe — the only real workload the current generation has seen — roughly **15 of
243 failures were ours** (9 memory refusals, 4 detector false positives, ~2 parse
collapses). About 6 %, and **13 of those 15 are already fixed and deployed**.
Zero timeouts. Everything below is tail work; nothing is a deploy blocker and
nothing is on fire.

**MAS has had no production traffic since 2026-07-30** and there is no sweep
date. We are building against a workload nobody has run yet. That is the single
biggest reason to keep scope small — see CLAUDE.md principle 7.

**`main` is ahead of production by one change: the browser cap** (`8e69c3a`,
merged 2026-08-02, **not deployed**). `max_browsers: 6` with LRU eviction, the
memory-adaptive TTL removed, and large corrections to the record. Offline-green,
reviewed, and it should ship — two small fixes first, listed in the table. The
old `pool-browser-cap` branch is now identical to `main` and can be ignored.

**So `git log` on `main` is ahead of what is running.** Before assuming a fix is
live, check the deployed image tag against `azure-deployment/` rather than the
commit history.

## The scope cut, 2026-08-02

Tero asked whether we were over-engineering. We were, and the evidence is
specific: `tasks/done/overnight-intervention-log-2026-04-14.md` recorded in
**April** that `az containerapp update --memory 8.0Gi` "doubles headroom at zero
cost (MS credits)". It was never tried. Between then and now we produced three
task files apportioning the 4 GiB, a regression over 68 log lines, and a
coordinator review disputing its slope — to divide a budget we may be able to
double with one command.

**So the open list is cut from nine items to three.** What was dropped was not
wrong, it was *unasked for*: work sized against a sweep that has no date, for a
customer who explicitly said do not build ahead of them.

**Do not re-expand this list without a reason that arrives from outside** — a
MAS message, a production failure, or a measurement. "There is a session free"
is not a reason.

## Decision pending with Tero — resize the replica

**This is the highest-leverage open question and it is not code.** Current sizing
is 2 vCPU / 4 GiB, `minReplicas: 0`. The environment has **no workload profiles**
(`profiles: null` — Consumption only), so the CPU:memory ratio is constrained and
`--memory 8.0Gi` at 2 vCPU will probably be **rejected**; 4 vCPU / 8 GiB is the
likely shape. Ten seconds to find out, and Azure either accepts it or errors.

If it works it plausibly deletes most of the memory thread, and 4 vCPU would also
let `render_capacity` rise from 2 — that number was benchmarked *as a 2-vCPU
limit* (2026-07-17), so it is not a law of nature. **`render_capacity` MUST match
the ACA `http-renders` scale rule**; `deploy-image.sh` has an invariant check,
do not break it.

Separately: **`minReplicas: 1` for the sweep window only** removes the
scale-from-zero burst that caused every 500 we have seen. Both are `az
containerapp update` scale settings — **not** `--set-env-vars`, which is the
operation that has broken MAS's token before.

**Do not change production sizing without Tero's go-ahead.** Ask, then measure.

## The three open items

| # | Task | State | What to know |
|---|------|-------|--------------|
| 1 | `pool-residency-unbounded.md` — **two fixes, then ship it** | BUILT and merged to `main` (`8e69c3a`), offline-green (196 pure-function tests), **not deployed** | Ship it: it is cheap, safe, and it is the only thing standing between us and a real cliff — `user_agent_mode: "random"` is in `UNTRUSTED_FIELD_ALLOWLIST` **and recommended by our own client doc**, and it would make every request launch a new browser. **Stop justifying it with memory arithmetic.** The regression it cites (`mem% = 59.3 + 2.65 × browsers`) is disputed on three counts in `replica-memory-baseline-unexplained.md` §"Why the fit is not settled" — read that before quoting any number from it. Two things to fix before deploy, both small: (a) the memory guard refuses **before** `_evict_for_capacity` runs, and the pressure-driven TTL is gone, so a replica over 85 % now holds idle browsers for the full `idle_ttl_sec: 300` instead of shedding — make the guard **evict, re-read, then refuse**; (b) strip the disputed slope out of the `config.yml` comment and cite the cardinality argument, which does not depend on memory at all. |
| 2 | `cleaned-html-collapse-guard.md` **part 2, repair 1 only** | Part 1 deployed 2026-08-01 | **Do repair 1. Do not do repairs 2 and 3.** Repair 1 is the raw-text re-serialization family (`unclosed-noscript`, `unclosed-script`) — a genuine upstream bug, the strongest of our upstream PRs, and the one shape the collapse guard is structurally blind to (`unclosed-script` has 0 visible text, so no text-ratio guard can see it). Repairs 2 (libxml2 depth limit) and 3 (unterminated comment) are **parked**: the guard already catches both and reports them to MAS truthfully at HTTP 200 + `success: false`, so they cost accuracy, not data. Re-open only if MAS's residual count says the population is large. |
| 3 | `flaky-fence-test-margin.md` | Open, ~1 hour | Our only pre-deploy gate is "the offline suite is green"; this test fails ~1 run in 3 for reasons unrelated to the code. **Diagnose before widening** — the same red can mean harness overhead *or* a fence that unwinds slowly under load, and the second is a finding about our 180 s fence against Azure's 240 s ingress limit. |

## Parked on purpose — do not pick these up unasked

| Task | Why parked | What would un-park it |
|---|---|---|
| `replica-memory-baseline-unexplained.md` | The 59 % may be an artefact of a metric that has since changed, and a resize would make it moot | Tero declines the resize, **or** the guard still fires after it |
| `pool-browser-retains-last-page.md` | **Closed as refuted** — `about:blank` returns 0.5 MB even against a 100 MB JS heap; per-browser memory is a ratchet only a close resets | Nothing. Kept as a record of a measured negative |
| `static-fallback-within-fence.md` | 0 × 504 in the only workload we have; the hang it was sized against was fixed in `done/render-retry-unbounded-hang.md` | A real 504 population in MAS's sweep |
| `blocked-host-retry-economy.md` | Cost optimisation, not a defect. And lever 1 now also skips the slow-hydration rescue (the patchright retry gained a 10 s wait) | The sweep showing blocked-host cost actually hurts |
| `base-config-boolean-defaults-never-applied.md` | `simulate_user` has never taken effect and nothing has missed it. "Delete the line" is the likely right answer | Someone wanting a boolean in `base_config` to work |
| `preflight-batch-endpoint.md` | **MAS said do not build speculatively.** Their words | MAS asks |
| `residential-egress-retry-path.md` | Population is floor 6 / ceiling 29 and the 23 undetermined resolve for free in MAS's next sweep. Costs money | A real count, then Tero |
| `static-mode-tls-impersonation.md` | Hardens a path nothing currently falls back to | `residential-egress` |
| `file-upstream-prs.md` | Standing tracker, four PRs open. Core behavioural changes sit for months | Nothing — check occasionally |
| `waa-eval-2026-07-30-forensics.md` | **Reference, not a task.** Never close it | — |

## Standing rules that have earned their place

**Live traffic is the last instrument, not the first** (since 2026-07-31, now
TESTING.md golden rule 0). Every failure class since 2026-04 was diagnosed
against a customer's website, all of it leaving from one shared Azure address
that is not contractually ours — and MAS's requests and our test requests share
that egress. `test-aitosoft/fixture_origin.py` is a local origin driven through
the real production path; **add a route before you add a request**, and check
`test-aitosoft/artifacts/` before you add a route. The entire 2026-08-01 image
and the 2026-08-02 pool work cost **zero live crawl requests** between them.

**Five consecutive sessions have found the previous session's task file
materially wrong about something load-bearing.** That is the separation of roles
working (CLAUDE.md principle 6), not a quality problem — but it means: verify the
diagnosis, not just the plan, and **check the arithmetic**, not just the logic.
The 2026-08-02 case is the sharpest: the record said 8 browsers at 165 MB "is the
whole 4 GiB budget". That is ~36 %. Four sessions read past it.

## Shipped 2026-08-01 — one image, four items

`0.9.2-detector-round3`, revision `--0000032`. Closed:
`challenge-interstitial-resolve.md` (both phases),
`detector-round3-evidence-vs-inference.md`,
`antibot-minimal-text-false-positive.md`, and the S half of
`render-500-window-2026-07-31.md`. `cleaned-html-collapse-guard.md` part 1 is
deployed.

- **Detection widened and invention narrowed in the same deploy, on purpose.** A
  block page padded to 80 KB at status 202 is caught as *evidence*
  (`origin_blocked`); a verdict derived from an empty-looking page is now *ours*
  (`render_error`). They compose: without the new tier, the unpadded form would
  have flipped from `origin_blocked` to `render_error` — a real block reported as
  our bug.
- **A real second instance was sitting in `test-aitosoft/artifacts/`.**
  `monidor.com`, returned to MAS at `success: true`, is an 11,515-byte
  interstitial with 58 characters of text. We had it for weeks.
- **Phase 2 rescues slow-hydrating shells, not just challenges** — MAS's
  `revisol.fi` class, absorbed server-side at zero extra page loads.
- **The cost of `detector-round3` defect B:** two of MAS's four cases move from a
  terminal 200 to a retried 500. Correct direction, real cost. Watch it in the
  next sweep.

## Cross-repo state

MAS (`aitosoft-platform`) is our only consumer. The exchange is markdown files in
gitignored `tmp/mas-repo-messages/`, numbered and direction-labelled, relayed by
Tero both ways. Durable conclusions get copied into the forensics record; the
messages are the transcript, not the source of truth.

**Status as of 2026-08-02: the ball is with them.** Message 10 (ours) was relayed
2026-08-01 and answered every open item. We are waiting on four things, of which
**only one changes what we build** — the sweep's shape (waves, concurrency,
per-host spacing), which is the input to the `minReplicas` / resize decision. The
other three (naming the `fodbar.fi` field, the residual empty-capture count, a
count for the unmarked-interstitial class) are small or informational. **Nothing
on our side is blocked on any of them.** No reply is owed by us.

**Two agreed changes are unblocked and unshipped**, both additive, both waiting
only on a reason to open an image: the `fodbar.fi` "content was present despite
the origin status" field (MAS names it), and flipping envelope `success` to the
aggregate — which must ship **alone**, since it breaks a pinned contract
(`test_static_mode.py:257`) and buys no behaviour.

**How to run this exchange**, since it is easy to get wrong: the *channel* is
correspondence, but the *contract* has no home — MAS's model of our behaviour is
reconstructed from ten messages, which is how `render_error` came to mean two
wire statuses for weeks without either side noticing. If a third party ever joins,
or if the taxonomy changes again, write the contract down as its own versioned
document rather than growing the message chain. And **never let a relay block a
deploy**: that coupling is what dropped the `fodbar.fi` field from a finished
image. Additive changes ship and get announced; behaviour changes wait for the
relay.

Settled 2026-07-31 (their message 07):

- **Envelope `success`:** flip it to the aggregate, **conditional on the HTTP
  wire status staying 200**. That condition is the load-bearing half.
  **Deliberately NOT shipped in the 2026-08-01 image** — it buys no behaviour
  (they never read it on 2xx) and would have been a third contract change in one
  deploy. Proposed in message 10; ship it on its own afterwards.
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
- ~~**`render_error` is currently served at two wire statuses.**~~ **FIXED and
  deployed 2026-08-01.** Static returned it inside a 200 (static never raises),
  full mode at 500. Both modes now route through `server._crawl_response` →
  `http_status_for`. The missing axis was **permanence, not ownership**:
  `render_defect` is entirely ours *and* must not be retried.
- **They have had zero production traffic since our deploy** — 86 WAA runs on
  2026-07-30, all before 18:24 UTC, none since. Their 243-host probe is the only
  workload the current image has seen. Do not read their silence as "seeing none".
- **No sweep date, and that is deliberate.** It runs when their system is ready.
- **The shared-egress finding landed on their side too**, with a consequence we
  had not drawn: a residential-vendor probe *run from our egress cannot answer the
  question it exists to answer*. They have marked their residential analysis
  part-superseded and will bring us the sweep's shape — waves, concurrency,
  per-host spacing — before wave 1.

Found on our side 2026-08-01 (logs + offline probe, zero traffic — see
`render-500-window-2026-07-31.md` and forensics §11; the coordinator's first pass on this is superseded):

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
  renders and `max_pages` bounds pages; residency was governed by idle TTL alone.
  ~~so 8 browsers were held to do 2 renders' worth of work~~ **Corrected
  2026-08-02: peak was 9–10 per replica.** Capped at 6. The replacement claim —
  `mem% = 59.3 + 2.65 × browsers`, r² = 0.22, "browsers are not where the memory
  is" — is **disputed on three counts** and must not be quoted as settled: see
  `replica-memory-baseline-unexplained.md` §"Why the fit is not settled". What
  survives: the *old* arithmetic (8 × 165 MB = "the whole 4 GiB") was wrong.
  What is open: by how much, and whether a resize makes it moot.
- **The "15,000 signatures" refutation is weaker than it reads.** The `dcount`
  was **per replica** over ~5 replicas, so it cannot bound global cardinality;
  nobody ran it without the `by`. Structurally it is probably bounded (the
  persona reference is 11 personas → 10 distinct payloads) but **we cannot show
  MAS runs that file**, and `user_agent_mode: "random"` — allowlisted, and
  recommended by our own shipped client docs — would make it one signature per
  request. The cap is correct under both models; that is now its main
  justification.
- **The permanent browser is never used** — 0 hits in 224 pool gets. ~130 MB of
  `anon` per replica for its whole life. ~~because MAS always sends a
  `browser_config`~~ **Corrected 2026-08-02: because `init_permanent` skips
  `enforce_egress`**, so its signature differs from every request's in
  `ignore_https_errors`. It is unreachable by construction, not by contract.

Found on our side 2026-08-01 (`cleaned-html-collapse-guard.md` part 1, offline,
zero traffic):

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
  untouched by the collapse-guard work; now tracked as
  `flaky-fence-test-margin.md`): it asserts `elapsed_s < 3` against a 1 s fence, so ~2 s of
  pool + page + teardown overhead has to fit, and a fully-loaded suite run
  sometimes does not. Failed once in three full runs. Not diagnosed — someone
  should either widen the margin deliberately or measure fence latency separately
  from harness overhead.

**Message 10 was RELAYED 2026-08-01** (Tero confirmed to the coordinator):
`tmp/mas-repo-messages/10-to-mas-the-202-answer-and-four-deploys-in-one-image.md`.
MAS now knows all of it — including that two of their four corrected verdicts
cost them retries, and that a second source of 429 exists. **Two things unblock
on the relay, both additive and both previously held only because the message
had not gone:**

- **The `fodbar.fi` field.** Its stated condition was "message 10 describes it
  first". Condition met; §7.2 asks MAS to name it. Ships in the next image once
  they answer, or is dropped if they say no.
- **Flipping envelope `success` to the aggregate.** Announced in message 10's
  closing section. Ship it **on its own**, never bundled — it breaks a pinned
  contract (`test_static_mode.py:257`) and buys no behaviour, so a surprise must
  be attributable to it.

What it says, kept here because the message file is gitignored:

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
  where 117,000 stored pages are. Cheap; **unblocked now that message 10 has
  gone** — it ships once MAS names the field.
- **A second source of 429 is coming, and they should hear it before it lands.**
  Shipped 2026-08-01: memory-pressure refusals arrive as **429 +
  `Retry-After`** instead of 500. Their client already backs off correctly on
  429, so nothing breaks — but the *shape* changes: on a cold first wave a single
  replica can answer a burst of them, which is right behaviour and still looks
  like a stall from their side. Send it with the scale-from-zero finding, since
  the two are the same event seen from either end, and say plainly that the 429
  makes the symptom cheap without removing the cause. **Corrected 2026-08-02:
  that message named `pool-residency-unbounded.md` as the cause; it is at most a
  contributor. The cause is unsettled, and a replica resize may remove it
  outright without any of this.** Nothing was sent to MAS naming a cause, so
  there is nothing to retract.
