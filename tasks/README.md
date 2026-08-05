# Open tasks, in the order to do them

**Updated:** 2026-08-05, after MAS's first deliberately-cold run and a
five-thread research pass over the whole open list. Three open items were closed
by *answering* them rather than building them; read "What the 2026-08-05 research
settled" before picking anything up.

**This file holds ordering, gating and current state — nothing else.** The
reasoning lives in each task file, the evidence in
`waa-eval-2026-07-30-forensics.md`, the shipped history in `AITOSOFT_CHANGES.md`.
It used to carry all three and had grown to 500 lines of duplicated changelog;
if you find yourself adding a narrative section here, it belongs in one of those.

**If a task file and this index disagree, the task file wins and this index is
stale** — fix it.

Read "Parked on purpose" before picking anything up: several files on disk are
parked deliberately, not waiting for a free session.

---

## Where we actually are

**Production is `0.9.2-collapse-recovery`, revision `--0000034`** (deployed
2026-08-02, Tier 1 4/4, zero guard fires on the four live pages), 2 vCPU / 4 GiB,
`minReplicas: 0`, `maxReplicas: 30`, scale rule 2 concurrent/replica.

**`main` is AHEAD of production as of 2026-08-05** — the egress-path work is
committed and undeployed. It carries one **wire-status change** (a dead domain
is now `origin_unreachable` at 200 instead of an SSRF 400), so by this repo's own
rule it waits for the MAS relay. Everything else in it is invisible to MAS.
Deploy = `./azure-deployment/deploy-image.sh <tag>` + Tier 1 4/4.

**MAS ran ~30 prospect sites on the evening of 2026-08-01 — the first real
workload this image has seen.** 336 renders, 328 distinct URLs, 38 hosts, read
out of Log Analytics with zero live requests of our own.

What that run settled:

| | |
|---|---|
| RenderGate 429 | **0** |
| Memory refusals | **0** (revision `--0000031` threw **36** on a comparable workload) |
| Wall-clock 504 | **0** |
| Janitor force-close | **0** |
| Anti-bot blocks / patchright retries | **0** |
| Latency | p50 4.7 s, p90 6.3 s, p99 7.3 s, max 14.9 s |
| Pool memory | p50 15.7 %, p95 39.8 %, max 56 %; resident peaked at the 6-browser cap |
| Queue | 14 of 335 waited, max 7.6 s, max depth 1 |

**The capacity and memory work is done and proven.** The cap, the shed-before-refuse
guard and `permanent_unused_ttl_sec: 120` between them took memory refusals from
36 to 0. Nothing in the memory family needs building.

What that run *found*:

1. **9 of 328 pages (2.7 %) returned zero markdown**, across 7 of 38 hosts. This
   is ours, it is the only thing costing MAS data, and **MAS reported the same
   run as clean** — a page with no contacts looks exactly like a page that has no
   contacts. Recovery shipped 2026-08-02; how much of this it actually returns
   on real traffic is **unmeasured** (fixtures say two of four mechanisms come
   back whole; which mechanism these 9 hit is unknown).
2. **One URL burned four renders and produced every 500 of the run.** A vCard
   endpoint; Chromium refuses to navigate to a download. Fixed 2026-08-02 —
   `unrenderable_content` at 200. The cost was worse than recorded: upstream
   retries on any exception, so at MAS's `max_retries: 2` those four requests
   were **8–12 page loads**, not 4.

Both were read out of Log Analytics again on 2026-08-02, which also settled the
one open question from the first read: the 12 guard firings over 9 URLs are 3
URLs MAS's agent revisited 15–52 s apart, not a retry path. Their gaps are
nothing like the 1/2/4 s backoff and their client does not retry a 2xx — **the
200 contract is holding as designed.**

**The untested axis is concurrency.** This run peaked at 2 concurrent with a
queue depth of 1. Heavier scraping is where 429s, eviction pressure and
scale-from-zero live, and none of it can be answered from here. MAS has agreed to
notify us before a heavier sweep so it can be watched live — that is the
instrument, not another task file.

---

## 2026-08-05: the first deliberately-cold run, and what it settled

MAS ran 10 companies at `--concurrency 2` against a scaled-to-zero service, on
purpose. **Their owner has ruled they will never pin a warm replica** — every
real campaign starts cold, so engineering around that would measure the wrong
thing. The larger cohort will run **in segments**, which *raises* cold-start
exposure rather than lowering it.

| | |
|---|---|
| Renders (ours) | 62 — 57 success, 5 failure |
| Latency | p50 4.61 s, p90 7.36 s, longest 60.38 s |
| 429 / 504 / 500 | **0 / 0 / 0** |
| Memory refusals, janitor force-closes, collapse-guard fires | **0 / 0 / 0** |
| Pool memory | p50 11.4 %, p95 29.9 %, max 33.7 % (guard is 85 %) |
| KEDA | 0 → 15 replicas and back to 0, cleanly |
| Max render-queue wait | 8.9 s against the 15 s that produces a 429 |

**The two repos' accounting reconciles exactly**, which is worth keeping because
it validates both sides' instruments: their 51 stored + 11 failures = our 62, and
our 57 successes are exactly 6 more than their 51 stored — *those 6 are the
404s*. Nothing was lost or double-counted between us.

**Concurrency is no longer the untested axis it was.** 15 replicas, zero
refusals, memory at a third of the guard. What replaced it as the open question
is below.

### What the 2026-08-05 research settled

Five parallel research threads, zero live crawl requests. Three open items
closed by answering:

1. **`content_source="raw_html"` (old item 1) — priced, answer is NO.** It
   dissolves only the two shapes recovery already fixes and *structurally*
   cannot help `unclosed-script` (tokenizer-level loss, identical in both
   parsers). It therefore does **not** delete old item 2. Full measurement in
   `cleaned-html-collapse-guard.md`, which also records that one of the two
   measurements cited in favour of it was not about `content_source` at all.
2. **The cold-start 504 question — answered by one Azure setting, not code.**
   `ContainerAppHTTPLogs` was off; it is now on (below).
3. **The ACA ingress timeout — 240 s, and not configurable here.** Behind the
   *same* workload-profile migration as the 4 GiB ceiling, not a separate
   blocker. It is an *idle* timeout, which nothing in our docs said.

And it found one thing worth building, one thing already true, and one
correction that invalidates arithmetic in four files:

- **The egress-path work — written, reviewed, implemented and closed the same
  day** (`tasks/done/egress-proxy-blocks-the-event-loop.md`). It was proposed as
  "three changes in one file we own"; it turned out to be six files, the file was
  **upstream's**, and the call site that mattered was in `api.py`, not the proxy.
  It also found a defect nobody had looked for: a lapsed domain reached MAS as an
  SSRF 400 with no `failure_class`.
- **We have no outbound politeness at all**, and `config.yml:106` makes it look
  like we do (that limiter only runs on the `arun_many` path, which our
  single-URL contract never takes). Pacing 15,000 hosts from one shared SNAT
  address is entirely MAS's, and it is the only failure mode here that is
  irreversible.
- **`max_retries` is 1, not 2.** All 213 `Anti-bot retry` lines in 14 days read
  `1/1`. See "Corrections to the record" below.

### The number that actually matters for the sweep

**62 renders with zero collapse fires is not evidence the family is closed.** At
the measured 2026-08-01 rate of 9/328 = 2.74 %, P(0 fires in 62) ≈ **0.18**. An
18 % outcome is not a result. Extrapolated to MAS's ~120,000 fetches the same
rate is ~3,300 pages, and how many of those recovery returns is still unmeasured.

**It costs nothing to get.** The log split already ships as deliberately
non-overlapping tokens — `COLLAPSE RECOVERED` (`api.py:948`) vs
`RENDER DEFECT … html2text recovered %d chars` (`:965`). One Log Analytics query
after segment 1 sizes both the population and the recovery yield, with zero
traffic and zero code. **This is the highest-value activity around the sweep and
it is not a task file.** Run it after segment 1 alongside `RESULT FAILURE` by
`failure_class`, the 429/504/500 counts, and `origin_blocked` **per segment**
(see the block-rate note in `tasks/done/mas-reply-owed-message-16.md` — a rate that climbs
segment over segment is IP-reputation decay and should stop the sweep).

### Azure change made 2026-08-05

**`ContainerAppHTTPLogs` is now enabled** — diagnostic setting `aca-http-logs` on
the managed environment `aitosoft-aca`, **HTTP category only** (console and
system logs already arrive via `appLogsConfiguration`; adding them here would
double-ingest and double-bill). It is the only surface that can record a request
the ingress terminated before a container existed, which until now was a pure
absence. Environment-wide, so it also covers `aitosoft-edge`.

Cost: ~13,400 ingress requests/month across both apps today, PerGB2018, 30-day
retention → ~0.02 GB/month. Even adding MAS's projected ~120,000 sweep fetches it
stays near $0.50/month. **It has no history** — it answers from 2026-08-05
forward only, so MAS's first segment is the first thing it can describe.

---

## The open items, in order

**Nothing in this repo gates MAS's sweep.** Message 14 was delivered and read
(their ledger lost it for two days; they have fixed that), and its §3 released
their gate. `main` == production in code — every commit since the deployed image
is documentation. So "is our pre-deploy gate sound?" is currently a moot
question, which is what deflates items 3 and 4 below.

**The message is written and the ball is with Tero to relay it:**
`tmp/mas-repo-messages/16-to-mas-a-dead-domain-was-never-an-ssrf-refusal.md`.
Its source material — every citation and measurement behind it — is
`tasks/done/mas-reply-owed-message-16.md`; argue from that file, not the message,
if MAS pushes back. **Its §0 is the deploy gate.**

**Old items 1 and 2 shipped together on 2026-08-02** as `0.9.2-collapse-recovery`
— collapse recovery and `unrenderable_content`. Both task files carry what the
implementing session found wrong; the short version is that **three load-bearing
claims across the two files did not survive**: recovery could not reuse static
mode's pipeline (only its converter), the obvious acceptance bar opened a new
silent-loss channel, and the download failure arrives as a failed *result*, not
an escaped exception. Details in `AITOSOFT_CHANGES.md` 2026-08-02.

| # | Task | Size | What to know |
|---|------|------|--------------|
| 1 | **Deploy `0.9.2-egress-dns`** — not a task file | S | **Gated on one answer from MAS, and that is the only thing gating it.** `main` holds the egress-path work undeployed because it moves a class from HTTP 400 to 200. The message is written and awaiting relay: `tmp/mas-repo-messages/16-to-mas-a-dead-domain-was-never-an-ssrf-refusal.md`, §0. Sequence, and the post-deploy check that has no other signal, are in the **Deploy** section of `tasks/done/egress-proxy-blocks-the-event-loop.md`. |
| 2 | `fixture-origin-bypasses-the-pinning-proxy.md` | S | **New 2026-08-05.** `set_egress_proxy()` has one caller, `server.py:183`, so `ProductionPath` never starts the proxy and **all 54 fixture tests run on a network path production does not use**. A dead host is 134 s direct vs 30 s through the proxy — a test without it measures the wrong number by 4×. ~12 lines; expect some of the 54 to change behaviour, and treat that as the payoff. |
| 3 | `guard-corpus-is-not-in-the-repo.md` | S | **After the sweep.** Real and verified — `test-aitosoft/artifacts/*` is gitignored, three tests fail on a fresh clone at `assert checked >= 30`. But its load-bearing sentence is **wrong**: "our only pre-deploy gate is the offline suite" is false (see corrections below), and it fails *loud*, in the safe direction. If ever done: 4–6 files into `artifacts/keep/`, the mechanism `.gitignore:14-17` already provides. Do **not** open its four-option sizing table before the sweep. |
| 4 | `flaky-fence-test-margin.md` | S | **After the sweep.** The 1-in-3 figure is stale — it is **1 failure in 9** recorded full runs (0/3 on 08-02, 0/3 on 08-05). Its "this might be a product finding about the 240 s ingress limit" fear is **refuted from code**: the unwind is bounded at 10 s by our own `PAGE_CLOSE_TIMEOUT_S` (`async_crawler_strategy.py:49`), so worst case is 180 + ≤10 ≈ 190 s, ~50 s inside the limit. The test also moved — it is `test_fixture_origin.py:748`, not `:640`. Fix is to raise `stall` and the assertion together. |

**Old items 1 and 2 are gone.** Item 1 (`content_source="raw_html"`) was priced
2026-08-05 and the answer is no — it is recorded in
`cleaned-html-collapse-guard.md` and should not be re-opened. Item 2 (repair 1,
`unclosed-script`) survives that pricing intact but is now **explicitly parked**:
it is purely prospective, zero production instances have ever been attributed to
it, and it is *structurally uncountable* — which is precisely why the segment-1
log split, not a task file, is the right next step. Its remaining value is
upstream PR quality, not our data.

**One decision left behind by the pool deploy, deliberately not taken.** The boot
("permanent") browser is unreachable **by construction**: `server.py:199` builds
its `BrowserConfig` inline *without* `enforce_egress`, while
`get_default_browser_config():138` and every request path apply it, so the
signatures can never match — 0 hits in 224 production pool gets. The two fixes
point **opposite ways** — delete the `init_permanent` call, or route it through
`get_default_browser_config()` to make it reachable — which is why it should not
be bundled into someone else's image. The cost was mitigated by
`permanent_unused_ttl_sec: 120`, so this is a decision, not a defect.
`monitor_routes.py:273-284`'s self-deadlock (`init_permanent` called *inside*
`async with LOCK`, which it re-acquires) is in the same file and is the natural
thing to fix in the same change.

---

## Parked on purpose — do not pick these up unasked

| Task | Why parked | What would un-park it |
|---|---|---|
| `replica-memory-baseline-unexplained.md` | **CLOSE IT, do not leave it parked.** No symptom in two consecutive workloads (p95 39.8 % then **29.9 %**, max 33.7 %, against an 85 % guard), a fit its own author refuted, and the underlying data is not in the repo. A parked file with no symptom is an invitation | Nothing. If memory ever becomes a symptom again, that is a new file with new data |
| `cleaned-html-collapse-guard.md` — repair 1 (`unclosed-script`) | Purely prospective and **structurally uncountable**: zero production instances have ever been attributed to it, and the shape is invisible by construction. Its value is upstream PR quality, not our data | The segment-1 `COLLAPSE RECOVERED` / `RENDER DEFECT` split showing the shape actually occurs |
| `static-fallback-within-fence.md` | 0 × 504 in two workloads now; the hang it was sized against was fixed in `done/render-retry-unbounded-hang.md` | A real 504 population in a sweep |
| `blocked-host-retry-economy.md` | Cost optimisation, not a defect — and the 2026-08-01 run saw **0 blocks in 336 renders** | A sweep showing blocked-host cost actually hurts |
| `residential-egress-retry-path.md` | Population is floor 6 / ceiling 29, costs money, and 0 blocks were seen in the only recent traffic | A real count, then Tero |
| `static-mode-tls-impersonation.md` | Hardens a path nothing currently falls back to | `residential-egress-retry-path.md` |
| `base-config-boolean-defaults-never-applied.md` | `simulate_user` has never taken effect and nothing has missed it. "Delete the line" is the likely right answer | Someone wanting a boolean in `base_config` to work |
| `preflight-batch-endpoint.md` | **MAS said do not build speculatively.** Their words | MAS asks |
| `file-upstream-prs.md` | Standing tracker, four PRs open. Upstream `develop` is **one commit past v0.9.2** (a Docker IPv6 fix, checked 2026-08-02) — core behavioural changes sit for months and waiting for them is not a plan | Nothing — check occasionally |
| `waa-eval-2026-07-30-forensics.md` | **Reference, not a task.** Never close it | — |

**Do not re-expand this list without a reason that arrives from outside** — a MAS
message, a production failure, or a measurement. "There is a session free" is not
a reason.

---

## Settled, so it stops being re-litigated

**There is no replica resize to be had.** Tero approved it; Azure refused it.
`az containerapp update --cpu 2.0 --memory 8.0Gi` is rejected — the allowed list
**ends at 2 vCPU / 4 GiB**, because this is a legacy Consumption-only managed
environment (`properties.workloadProfiles: null`). The April note claiming
`--memory 8.0Gi` "doubles headroom at zero cost" was never a valid command. The
only path to more memory is converting the environment to workload profiles,
which is an infrastructure migration with a different billing model (dedicated
profiles bill continuously and would end `minReplicas: 0` economics) — and at
2× cost per replica-second with `render_capacity` fixed at 2 by the vCPU count,
**cost per fetch would double for zero throughput gain**. Not approved, and no
longer needed: memory refusals are at zero.

**`render_capacity` stays 2** — fixed by 2 vCPU. If it ever moves, change the ACA
scale rule *first*: `deploy-image.sh` verifies that invariant **after** updating
the image, so it is a post-hoc alarm, not a gate.

**Still Tero's, and cheap:** `minReplicas: 1` for a sweep window removes the
scale-from-zero burst behind every 500 we have ever seen. It is a scale setting,
**not** `--set-env-vars`, so it carries no token risk.

---

## Standing rules that have earned their place

**Live traffic is the last instrument, not the first** (TESTING.md golden rule 0).
Every failure class since 2026-04 was diagnosed against a customer's website, all
of it leaving from one shared Azure address that is not contractually ours — and
MAS's requests share that egress. `test-aitosoft/fixture_origin.py` is a local
origin driven through the real production path; **add a route before you add a
request**, and check `test-aitosoft/artifacts/` before you add a route. The
2026-08-01 image, the 2026-08-02 pool work and the 2026-08-02 production
forensics cost **zero live crawl requests** between them.

**Eight consecutive sessions have found the previous session's task file
materially wrong about something load-bearing** — that is the separation of roles
working (CLAUDE.md principle 6), not a quality problem. Verify the diagnosis, not
just the plan, and **check the arithmetic**, not just the logic. The sharpest
case: the record said 8 browsers at 165 MB "is the whole 4 GiB budget". That is
~36 %. Four sessions read past it.

The eighth (2026-08-05, the egress work) produced the largest count yet — ten
corrections — and the shape is worth naming: **every error was in the framing
and the sizing, none in the core diagnosis.** The mechanism was correctly read
from source; what was wrong was *which file*, *which call site*, *which
environment*, *how many literals*, and *how big the population*. A file can be
right about the bug and wrong about everything you need in order to fix it. Two
specifics worth carrying:

- **"A file we own outright" is a claim, not a fact.** `egress_proxy.py` and
  `egress_broker.py` were byte-identical to `upstream/develop`. One
  `git diff upstream/develop -- <file>` would have settled it before a line was
  written, and it changes the review surface, the merge cost and the CI gates
  that apply.
- **The dominant call site is rarely the one you read first.** The file named
  two `resolve_and_pin` calls in the proxy; the one that actually fires for a
  dead nameserver is in `api.py`, before render admission. `git grep` the
  primitive, not the file.

The seventh (2026-08-05) is the first where the wrong claims were found
**without implementing anything** — five parallel research threads against the
open list turned up six (see "Corrections to the record"), and two of them
deleted work rather than redirecting it. Two variants worth naming:

- **A measurement can be cited for something it does not measure.** The "median
  0.91×" figure was offered as one of two independent confirmations that
  `content_source="raw_html"` was cheap. It measures a different converter with
  a different flag, and the two "independent" measurements were one.
- **A documented contract value can be fiction for weeks and cost nothing
  visible.** `max_retries: 2` appeared in CLAUDE.md, this file and two tests;
  production has always sent 1. Nothing broke — it just made every per-host cost
  figure 1.5× too high, silently, including one that was used to size a task.
  **Contract values that only *we* record are exactly the ones to re-measure**,
  because no test fails when they drift.

The sixth (2026-08-02) added a variant worth naming: **a claim can be right about
the component and wrong about the thing that ships.** "Recovery reuses the
converter `aitosoft_static_mode` already ships" was true of `HTML2Text` and false
of the pipeline around it, which deletes the very pages recovery exists for. The
published measurement reproduced to the character; the *justification* under it
did not. Re-run the measurement — and then check that what ships is what was
measured.

**A consumer reporting "no problems" is not evidence of no data loss.** MAS
called the 2026-08-01 run clean; 9 of its pages came back with nothing in them.
They were not careless — the failure is invisible from their side by
construction. Record what we measured, not what we were told.

---

## Corrections to the record, 2026-08-05

Six things this repo asserted that are not true. They are collected here because
each was load-bearing somewhere, and because the pattern is the point: **all six
were found by checking a claim, none by a failure.**

1. **`max_retries` is 1, not 2.** All **213** `Anti-bot retry` lines in the last
   14 days read `1/1` — including the 113 in the 2026-07-31 forensics window our
   cost arithmetic was derived from. `config.yml`'s `base_config` does not set
   it, so the value is MAS's. `async_webcrawler.py:405` is
   `_max_attempts = 1 + max_retries`; `:442` prints the config value verbatim.
   Consequences: **CLAUDE.md:93** (the request-shape example) and **:140** ("one
   request at `max_retries: 2` is *three* navigations") are wrong; this file's
   own "8–12 page loads" for the vCard URL was **8**, and 12 was never reachable;
   and `test_fixture_origin.py` pins `MAS_MAX_RETRIES = 2` into two tests, so
   **two fixture tests model a request shape production has never sent** — the
   same "unfaithful on exactly the load-bearing axis" failure this file already
   records for `/block/padded-403`. Fixed in CLAUDE.md and here; the test
   constant is left for whoever touches those tests, with this note as the
   reason.
2. **"Our only pre-deploy gate is 'the offline suite is green'"** — false, and it
   is the load-bearing sentence of `guard-corpus-is-not-in-the-repo.md`.
   `TESTING.md:231` and CLAUDE.md principle 4 both make **Tier 1, 4/4, live** a
   gate — and Tier 1 re-fetches *exactly* the hosts the corpus is made of, which
   `AITOSOFT_CHANGES.md:30` already says outright. The corpus gap costs us
   offline threshold *re-derivation*, not false-positive protection.
3. **The fence test's flake rate is 1 in 9, not 1 in 3** (0/3 on 08-02, 0/3 on
   08-05). And its "possible product finding" is refuted from code: the unwind is
   bounded at 10 s by `PAGE_CLOSE_TIMEOUT_S` (`async_crawler_strategy.py:49`), so
   180 + ≤10 ≈ 190 s, ~50 s inside the 240 s ingress limit.
4. **One of the two measurements cited for `content_source="raw_html"` was not
   about `content_source`.** "Median 0.91× across 59 stored captures" measures
   the *recovery converter* with `ignore_images=True`; the gap is dropped images.
   The real figure is 1.002. Two "independent" measurements were one.
5. **The stored corpus is narrower than claimed.** `test-aitosoft/artifacts/`
   holds 140 files but only **61 distinct captures across 7 URLs on 6 hosts**,
   five of which are the Tier 1 set. "66 stored captures" overstated the breadth,
   and anything sized against it inherits that.
6. **`AITOSOFT_CHANGES.md:1342`'s ingress budget assumes a warm replica.**
   "15 s queue + browser get + 180 s fence ≈ 200 s < 240 s" omits the
   scale-from-zero leg, and the ingress clock starts when the request hits the
   ingress. Worst observed cold start 65 s + 15 s + 184 s = **264 s**. Never
   observed, needs three worst cases at once, and MAS's 210 s client timeout
   fires first regardless — so a stale budget line, not a live risk. But as
   written it invites the reader to believe the margin is 40 s when on a cold
   replica it can be negative.

---

## Cross-repo state

MAS (`aitosoft-platform`) is our only consumer. The exchange is markdown files in
gitignored `tmp/mas-repo-messages/`, numbered and direction-labelled, relayed by
Tero both ways. Durable conclusions get copied into the forensics record; the
messages are the transcript, not the source of truth.

**Cite filenames, never integers.** MAS asked for this in their 2026-08-05
message and it is worth honouring: their ledger numbers diverged from ours (our
"13" is their "11"; they have no 12 or 13), and the mismatch is part of why our
14 sat unread for two days.

**The ball is with Tero: relay
`tmp/mas-repo-messages/16-to-mas-a-dead-domain-was-never-an-ssrf-refusal.md`.**
Their message it answers is
`tmp/mas-repo-messages/15-from-us-your-answer-sat-here-two-days-and-the-run-went-cold.md`.
Ours asks for one blocking answer (§0, the 400 → 200 wire-status change) and
five non-blocking ones.

**Message 14 was delivered and read** (2026-08-05, after sitting unread in their
repo since 08-03 — their thread ledger had no row for it; they have fixed that
and recorded the cause). Its §3 released their sweep gate two days before they
knew it. Its core finding held: `result.html` is in every response, and they now
**store** `html` and `cleaned_html` on every page as of 2026-08-04.

**Message 14's §7 offer is dead as written and must not be re-sent.** It offered
a projection parameter to *stop* shipping `result.html` on the grounds that they
discard it. They now depend on it — holding `html` and `cleaned_html` side by
side is what distinguishes "their cleaner dropped this" from "our capture never
got it", and it is the reason their Unit C exists. Our measured `html` field
(253,859 B) matches their observed average (247 kB) to the byte. **What they will
accept is dropping `fit_html` only — 101,117 B of a 634 KB result, ~16 %** — and
they explicitly asked that `crawl_stats` not be projected away. Do not build any
of it unasked; their words were "if you build one".

The other three offers in 14 stand unchanged and unbuilt, each waiting on a
one-word answer: tag which leg answered a patchright retry; promote `hreflang` +
`<html lang>` into `links`/`metadata`; a sitemap endpoint or XML-aware static
path.

Two measurements in it are worth keeping wherever they land, because they are
about us, not about the answer: `normalize_url` **drops fragments before dedup**,
so a fragment-anchored roster collapses to one link (12.3 % of distinct URLs
across our 5 stored captures, 34 % on the worst page); and the 10 s patchright
retry wait — **which has now fired, once, and did not rescue the page.**
`www.lundbeck.com/fi`, 2026-08-04 12:05: genuine HTTP 403 / 923 bytes, patchright
singleton booted on first use, retried at `capture wait 10.0s`, **still blocked**.
Cost 4 navigations / 22.55 s / one gate slot. It also emits a **second
`[COMPLETE]` with no second `RenderGate ADMIT`**, which is why COMPLETE can
exceed ADMIT in a window — worth knowing before anyone reconciles those counts.
(That observation comes from a MAS task-implementation run, not a clean baseline,
but the event itself is ours and factual.)

Message 11 (sent 2026-08-02) asked for a cold-start re-scrape of their 243 hosts
and eight lettered reports. They ran ~30 sites of real traffic instead, which
answered four of the eight from our own logs.

Still genuinely open, and only their corpus can answer:

| | question | why it still matters |
|---|---|---|
| (b) | do the four padded-403 hosts now come back `origin_blocked`? | If they still return content, the new block-notice tier does not fire on the real page — a real defect, and the fixture was already unfaithful once on exactly this axis |
| (c) | how many hosts moved to `render_error` at 500 (the `norex.com` class)? | If it is a large population, **do not change the wire status** — make the *inference tier* less eager instead |
| (f) | residual empty-capture count | Sizes the population our own 2.7 % only samples |
| (g) | count of interstitials carrying no marker, no prose and no notice | We deliberately do not catch this class and cannot count it. A number lets us stop wondering |

Answered from our side on 2026-08-01/02, so do not re-ask:

- **(a) wire statuses on a cold service** — the run started against a
  scaled-to-zero app and produced **0 × 429 and 0 × memory refusals**. The cap
  worked. `minReplicas: 1` is now optional rather than needed.
- **(d) blocked hosts** — 0 blocks and 0 patchright retries in 336 renders. Weak
  evidence, but it points away from the residential-egress spend.
- **(e) `render_defect` sightings** — we have our own now: 9 URLs, 7 hosts. Their
  bytes are still welcome but no longer gating: recovery shipped 2026-08-02 and
  classifies the mechanism for free, from the `COLLAPSE RECOVERED` /
  `RENDER DEFECT … recovered 0 chars` split in our own logs.
- **(h) the sweep's shape** — being handled by process instead: MAS will notify
  before heavier scraping so it can be watched live.

**Two agreed changes are unblocked and unshipped**, both additive, both waiting
only on a reason to open an image: the `fodbar.fi` "content was present despite
the origin status" field (MAS names it), and flipping envelope `success` to the
aggregate — which must ship **alone**, since it breaks a pinned contract
(`test_static_mode.py:257`) and buys no behaviour.

**Announced and delivered** in message 12 (relayed): `unrenderable_content`, the
static-mode lever for vCard-shaped URLs, and collapse recovery. Nothing from the
2026-08-02 image is still waiting to be told. If MAS wants a "this markdown came
from the fallback" flag, the name is theirs to pick — same as the `fodbar.fi`
field, and same as the retry-leg tag offered in message 14.

**How to run this exchange**, since it is easy to get wrong: the *channel* is
correspondence, but the *contract* has no home — MAS's model of our behaviour is
reconstructed from eleven messages, which is how `render_error` came to mean two
wire statuses for weeks without either side noticing. If a third party ever
joins, or if the taxonomy changes again, write the contract down as its own
versioned document rather than growing the message chain. And **never let a relay
block a deploy**: that coupling is what dropped the `fodbar.fi` field from a
finished image. Additive changes ship and get announced; behaviour changes wait
for the relay.
