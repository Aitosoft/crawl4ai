# Open tasks, in the order to do them

**Updated:** 2026-08-09 (third update that day), after **implementing item 10 and closing
items 6 and the parked `base-config` file without code**. Read "Corrections to the record,
2026-08-09" before picking anything up.

**Where this leaves us: one undeployed change, waiting only on a deploy window.**

- **Item 10 SHIPPED into `main`, undeployed.** The image `desc` cap:
  `MEDIA_DESCRIPTION_MAX_CHARS = 200` + upstream's own `truncate()` in
  `find_closest_parent_with_useful_text`. `media` **231,708,619 → 538,747 B (430×)**,
  `cleaned_html` and markdown **byte-identical (md5)**, all 1,160 entries kept. Offline
  suite **312 green** (306 + 6 new). **Tier 1 is the remaining gate, then Tero.** MAS's
  own instruction: it is invisible to them, do not bundle or hold anything for them, and
  **tell them the deploy timestamp — that is the only reply they want.**
- **Item 6 CLOSED UNFIXED.** MAS's corpus refutes it: `www.ktth.fi` returned **14,542
  chars on 2026-04-17** and the `laatutrio.fi` apex paths **21,234 and 14,564 on
  2026-08-08**, the day the file called them deterministic. Marking them permanently dead
  would have converted a recoverable miss into silent permanent loss. **Four findings
  inside it were rehomed rather than lost** — see the file's closing header for where each
  went. PDFs are settled too: MAS removes them at dispatch.
- **`base-config-boolean-defaults-never-applied.md` CLOSED.** Its "fix the merge rule"
  premise is obsolete — `CrawlerRunConfig.set_defaults()` sets booleans today and honours
  an explicit client `false`, which the proposed fix could not. `simulate_user: true` is
  **commented out** of `config.yml` (it never applied, and left in place it was a landmine
  for whoever "fixed" the merge rule).
- **Two upstream PR candidates gained, one lost.** Gained: the `desc` cap (seventh, and
  the cleanest we hold) and the `browser_manager.py` channel downgrade (eighth). Also a
  latent upstream *security* report, now tracked in `file-upstream-prs.md` instead of a
  corrections list. Lost: nothing — item 6's PR angle was always weak.

**Superseded:** the second 2026-08-09 update's claim that "nothing new is worth deploying
for on its own". The cap is worth a deploy on its own; it is the only thing that has cost
a customer's data outright since the consent JS.

**Previous update (2026-08-09, second):** after reading **batch 1** out of Log
Analytics and running a five-thread research pass plus a second-opinion review over the
whole open list. **The review found load-bearing errors in all three conclusions it was
given, including two of this file's own.**

**Batch 1 (2026-08-09 08:54–10:40 UTC, `--concurrency 5`, 200 companies, cold) is the
first known-resolving cohort, and that makes it the only run that resembles the real
sweep.** 1,364 `/crawl` at the ingress → 1,343 × 200, **18 × 500**, 3 × 429, 0 × 504.
1,358 RenderGate admissions + 3 pre-admission DNS refusals + 3 rejects = 1,364, exact.
True concurrency mean **1.49**, p95 2.69, max 4.99, on max **10 replicas of 45**. Latency
p50 5.32 s / p90 9.42 s / p99 31.4 s. **0 collapse fires, 0 render defects, 0 memory
refusals, 0 janitor force-closes.** 124 `CONSENT DECLINED`, **`structural=True`: zero** —
the exact inverse of segment 2, and **70 of 124 (56 %) matched a `<script>` or `<style>`
element**, which strengthens the upstream root-collision argument.

**Three things came out of it:**

- **Item 6 now has a file and it absorbed the PDF question.**
  `inference-tier-500s-are-not-retryable.md`. **16 of 18 of batch 1's 500s (89 %)** are one
  defect: the tier-3 structural inference calling a structurally-intact *non-page*
  "blocked", which at origin status 200 falls through to `render_error` → 500 → retried.
  PDFs are **12 %** of that class, not a separate problem.
- **Item 10's fix moved from "needs a deploy and a MAS workaround" to "~5 lines in files
  we own, and it is faster than what we do today."**
- **Nothing new is worth deploying for on its own.** The one genuinely new risk found
  (pool memory) is a **do-nothing** after measurement — see the corrections.

**Two process items, both for Tero, neither blocking code:**

- **Messages 34 and 37 are missing from `tmp/mas-repo-messages/`** (29 and 30 too).
  `37-…` is where MAS answered the six asks in `36-…` §8 — the 215 s client-timeout
  confirmation, the `exclude_all_images` decision, and **whether to bundle a deploy**.
  That last answer is currently unknowable from this repo. **Ask for a re-relay before any
  deploy decision.**
- **The correlation id is the largest untracked promise.** Committed twice (`33-…` §5,
  `36-…` §7) and tracked nowhere. It is minted only at `server.py:530` on a 500;
  `api.py:721`'s `request_id` never leaves the process. It closes three MAS asks at once
  and cannot regress anything.

**Segment 5 (2026-08-08, `--concurrency 4`, 318 companies, 3 h 14 m, cold on
purpose) is the largest workload either repo has run, by 6×, and the
infrastructure was never the constraint.** Our side: 1,987 `/crawl` requests →
1,914 × 200, 70 × 500, **3 × 429**; 1,902 render admissions + 84 pre-admission
DNS refusals reconcile to the request. **True concurrency (`sum(RequestDuration)
/ 60 s`, 1-minute bins) was mean 1.31, p95 2.96, max 5.25**, on **max 9 replicas
of 45**. Queue: 50 of 1,902 waited at all, max logged wait 7.7 s against the
15 s that rejects, max depth 3 of 4. Latency p50 5.12 s / p90 10.22 s / p99
38.65 s. **0 collapse-guard fires, 0 render defects, 0 memory refusals, 0
janitor force-closes, 0 × 504.** The consent guard declined **266** removals and
**103 of them were structural roots on 19 domains** — 103 pages that were
15-byte captures at HTTP 500 on the pre-2026-08-06 image.

**Item 9's acceptance run passed.** The trigger change held at 6× the load:
9 replicas for a ~1.3-concurrency workload, against 30 replicas for segment 3's
~1.2. No revert criterion was met.

**Two things came out of reading it, and one is new:**

- **Item 10** — `www.thermokon.fi` returned a **232 MB** response four times at
  HTTP 200 `success: true` with **no log line anywhere**, and MAS's client
  timed out at 216 s on each. Deterministic data loss, invisible to every
  instrument either repo has, and 35 % of our 14-day egress. New file.
- **Item 6 is no longer a 12-event curiosity** — it is **78 % of segment 5's
  500s** (54 of 69, 7 hosts). Its row below carries the new evidence.

**The two capacity numbers worth carrying forward:** the pool touched **80.9 %
memory** against the 85 % guard (p50 46.9, p95 66.1) with 6/6 browsers resident
— the tightest we have run, though nothing refused; and **538 of 1,432
consecutive same-host request pairs (37.6 %) arrived within 1 second of each
other**, median gap 1.5 s. The second is the only *irreversible* risk in the
programme and it lives on MAS's dispatcher, not ours.

**Superseded below:** the 2026-08-08 note that opens with segment 3.

**Segment 3 (2026-08-08, `--concurrency 3`, 50 companies) was clean, and the
consent guard held.** 292 renders / 281 distinct URLs, **0 × 429**, 3.9 % retry
amplification, 0 collapse events, 0 render defects. 14 `CONSENT DECLINED`, all
`structural=False` on genuine banners or a stylesheet `<link>` at `chars=0` —
**zero content loss**. Three things came out of reading it, and only the first is
ours: (a) **item 9**, the autoscaler ratchet — we ran the whole segment at
`maxReplicas` on a ~1.2-concurrency load; (b) **our 404 count is not an
instrument** — `RESULT FAILURE` only fires for *failed* results, so a 404 that
renders a normal page logs nothing at all, and MAS's envelope-side `>= 400`
cross-check is the complete count (they saw 26, we saw 2, and **they are right**);
(c) MAS's agent constructs URLs it never saw — 12 distinct guessed Teboil paths
reached render admission, and 15 requests went to Ecolab for one Finnish company,
which is ~9 % of renders and **theirs to fix, already in progress**.

**Azure change, 2026-08-08: `maxReplicas` 30 → 45**, revision `--0000038`, for
MAS's ~18,000-company plan (~80 concurrent renders vs our previous 60 ceiling).
Verified read-only first: environment quota is **100 consumption cores** and MAS's
own app in the same environment is 0.25, so **50 replicas is the hard ceiling**.
Post-change invariants checked — image, `minReplicas`, scale rule, CPU/memory and
all five env vars unchanged; bad token still 401. It is *not* part of item 9's
fix, but it moves item 9's baseline.
MAS's segment 1 (25 companies) and a five-message exchange found a defect of ours
large enough to reorder the whole list; it is now fixed, deployed and **proved in
production on the host it was diagnosed from**.

**Read this first: segment 2 ran on 2026-08-06 and the counter has been read.**
`tasks/done/segment-2-counter-readout.md` is the result and it is the most
load-bearing thing in this file right now. Both relays landed, MAS ran 261
renders across 61 domains in 58 minutes, and **the consent guard was firing on
real prospect sites throughout** — 27 pages on 3 Enfold domains that would each
have been a 15-byte capture at HTTP 500 on the previous image.

**The silent inner-element channel is CLOSED, and MAS closed it, not us.** Our
counter could only bound it (0 of 261 renders, ≤~1.1 %). Because the fix lets those
elements survive into storage, MAS *read* them: **95 matched containers, 0
containing any contact information, across 34,533 characters**, checked with
several wider nets and against a flat control. So the generic selectors removed no
data even when they matched — **the only harm they ever did was the `<html>`
collision.** Both sides independently count **27 roots on 3 companies**. Named
selectors hit a root **zero** times; genuine click-navigations **zero**.

**Read `27-…` and the readout together — MAS's message corrects us twice and we
correct it twice**, which is the exchange working:

- **Ours to fix:** the readout's first draft undercounted `origin_unreachable` by
  **57 %** (9 of a true 21) because it keyed on the `RESULT FAILURE` *token*
  instead of the `failure_class=` *field* — and `OVERNIGHT_PLAYBOOK.md` actively
  told it to. Pre-admission DNS failures only ever emit `ORIGIN FAILURE`. Playbook
  fixed; **the rule is now: key on `failure_class=`, never on the token.**
- **Theirs to fix:** `kea.fi` is **not** blocking us — four successful pages, one
  403 path, no HTTPS. Us-specific blocking is **1 of 50, not 2**, and they
  pre-registered a segment-3 stop rule at ≥2 in 50. Also their §5a is our
  documented correct behaviour (the discriminator is `success`, not the host) and
  §5b is false as diagnosed (that result carries `status_code=None`, so no
  status branch can fire).

**And the premise both repos carried about load was wrong.** MAS's
`--concurrency 2` limits **companies**, not fetches; 74 % of companies fan out to
≥2 parallel pages and the run peaked at **7 in flight**, which is what produced the
single 429 on a cold replica. The good consequence: **that ceiling is set by their
flag, not by cohort size** — 50 companies or 15,000, the peak stays ~8. We have
~7–8× headroom before `maxReplicas: 30`.

**Verdict: ready to scale.** Nothing lost data, the capacity and memory families
are at zero across **four** workloads, and both repos reconcile request-by-request
(274 ingress = their 264 outcomes + 10 retries; four correlation ids match
byte-for-byte). Items 6–8 below are **cost hygiene worth doing first because they
are small** — together ~3.3 % of request volume — not blockers. The one genuine
unknown is measurable on MAS's side today: the near-empty-*success* population,
which neither our collapse guard nor our consent counter can see by construction
(readout §5c).

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

**Shape:** 2 vCPU / 4 GiB, `minReplicas: 0`, `maxReplicas: 45` (raised from 30
on 2026-08-08), ACA scale trigger `http-renders` **6** (raised from 2 on
2026-08-08; ACA's own default is 10). **The trigger is NOT `render_capacity` and
must never be pinned to it again** — different quantities, different units; see
`tasks/autoscaler-ratchets-to-the-cap.md`. RenderGate still hard-caps renders at
2/replica and that is the safety mechanism.

**Production is `0.9.2-consent-guard`, revision `--trigger6`** (image unchanged
since 2026-08-06; the revision was minted 2026-08-08 by the scale-trigger change,
which is a template edit and therefore mints one). `main` and production are in
sync. Post-change smoke green: `/health` 200, bad token 401, `raw://` render
`success:true` / `failure_class:none` / markdown extracted.

**Note the revision-name break:** `--trigger6` came from
`az containerapp update --revision-suffix trigger6`, used to recover a revision
stranded in `ActivationFailed` (see item 9). Numbering resumes at `--0000041`
on the next ordinary deploy; do not read the name as a rollback target. It carries one **wire-status change**: a capture with no `<body>` is
`render_defect` at 200 (terminal), not `render_error` at 500 (retried 3x).
Pre-agreed with MAS; announced in `tmp/mas-repo-messages/22-…`, **which still
needs relaying**.

**`www.kubler.fi` is the proof and it is in production.** 15 bytes at HTTP 500
before this image; **55,545 chars of markdown and 5 contact emails after**, with
`av-cookies-no-cookie-consent` still on `<html>` and the guard's own log line
naming it (`node=html structural=True chars=2634 pagechars=2634`). The site did
not change; we did.

`--0000036` (`0.9.2-egress-dns-fix`, 2026-08-05) is the rollback target. It
carried its own wire-status change — a dead domain is `origin_unreachable` at
200, not an SSRF 400 (`16-…` §0).

**Revision `--0000035` is a burned tag** — it shipped a `NameError` and lasted
8 minutes. Do not roll back to it; `--0000034` is the last good prior image.

---

## 2026-08-06: segment 1, and the defect that gates segment 2

MAS ran **25 companies, 165 requests, 27 min 58 s**, and told us the window
afterwards. Two things came out of it, and they point in opposite directions.

**The infrastructure is not the problem and is not close to being the problem.**
0 × 429, 0 × 504, 0 memory refusals, 0 janitor force-closes, 0 `origin_blocked`,
0 collapse-guard fires, max render-queue wait 3.5 s against the 15 s that
produces a 429, max queue depth 0, p50 4.25 s / p90 6.32 s. **The accounting
reconciles with MAS's exactly** — their 165 requests are our 157 render
admissions plus 8 DNS failures refused before admission, and their 158 distinct
URLs are our 150 plus the same 8. Nothing was lost or double-counted between the
two repos.

**Our own JS deletes customer pages, and two of the three ways are silent.**
`remove_consent_popups.js` — which MAS sends on every request — removes any
element whose class or id merely *contains* `cookie-consent`, `cookie-notice` and
seven similar substrings, with no guard on what it matches. On the Enfold
WordPress theme that class sits on `<html>`, so we delete the document. Full
evidence, all four failure shapes and the design reasoning are in
`tasks/done/consent-scripts-delete-the-page.md`; the classification net is
`tasks/done/total-loss-is-permanent-not-transient.md`.

The three things worth carrying at index level:

1. **Two of the four shapes return a green result with data missing.** An inner
   element carrying the class comes back `success: true`, `failure_class: "none"`,
   HTTP 200, **99.5 % of the expected markdown**, and the contact block gone. A
   Phase-1 click that navigates returns *a different page*, in full, at 200.
   MAS confirmed from their side that nothing in their client or agent could
   flag either.
2. **Neither repo can size it retrospectively.** The matching element is deleted
   *before* the capture either side stores, so both archives are post-deletion by
   construction. MAS's "0 of 193 pages carry the trigger" is not weak evidence —
   it is the only possible result. This is why the fix has to ship with a
   counter at the point of removal, and why segment 2 is the measurement.
3. **Both JS files are byte-identical to `upstream/develop`.** Fifth and sixth
   upstream PR candidates, and the strongest we have — but file them *after*
   segment 2, when we can attach production counts.

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
traffic and zero code. Run it alongside `RESULT FAILURE` by `failure_class`, the
429/504/500 counts, and `origin_blocked` **per segment** (see the block-rate note
in `tasks/done/mas-reply-owed-message-16.md` — a rate that climbs segment over
segment is IP-reputation decay and should stop the sweep).

**Done for segment 1, 2026-08-06. Both tokens: zero.** 0 `COLLAPSE RECOVERED`,
0 `RENDER DEFECT`, in **147 successful renders**. `origin_blocked` was also 0, and
that is now the recorded per-segment baseline MAS will compare segment 2 against.

Read the zero carefully, because it is two facts and only one of them is good:

- At the 2026-08-01 rate of 2.74 %, P(0 fires in 147) ≈ **1.7 %**, so this is
  real evidence the `<noscript>` collapse family is smaller on this cohort than
  the original sample suggested. **Keep re-running it per segment** — it is one
  query and it is the only tracking this family gets.
- **It is not evidence that pages arrived intact.** The guard never saw the
  consent-deletion family at all: total loss had already failed (guard is
  successes-only) and partial loss is invisible to it by construction. A green
  guard counter and a lost contact block are entirely compatible, which is the
  whole reason `consent-scripts-delete-the-page.md` ships its own counter rather
  than leaning on this one.

MAS's archive supplies a floor for the empty-capture family from the other side:
of 41 companies where every stored page is byte-identical, **26 have every page
at 1 character** (`21-…` §2b, across 17,439 companies).

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

**Items 1 and 2 shipped; the current gate is item 9.** Segment 3 ran clean at
`--concurrency 3` (292 renders, 0 × 429), and MAS's next rung is 4, then a
~18,000-company run at roughly 20 companies in flight. Item 9 is the one thing
worth settling before that scale, and it is the only new task from segment 3.
**Everything else below was already parked or deflated and stays that way.**

`main` == production in code; every commit since the deployed image is
documentation. Message 16 was relayed and answered (MAS's 17), so nothing is
waiting on Tero except the relay of `20-…` and whatever we send next.

**Old items 1 and 2 shipped together on 2026-08-02** as `0.9.2-collapse-recovery`
— collapse recovery and `unrenderable_content`. Both task files carry what the
implementing session found wrong; the short version is that **three load-bearing
claims across the two files did not survive**: recovery could not reuse static
mode's pipeline (only its converter), the obvious acceptance bar opened a new
silent-loss channel, and the download failure arrives as a failed *result*, not
an escaped exception. Details in `AITOSOFT_CHANGES.md` 2026-08-02.

| # | Task | Size | What to know |
|---|------|------|--------------|
| ~~9~~ | ~~`autoscaler-ratchets-to-the-cap.md`~~ | M | **SHIPPED 2026-08-08, acceptance pending.** Trigger 2 → 6; `deploy-image.sh` drift check replaces the category-error invariant (it would have hard-failed every future deploy *after* the image landed); `batch-scale.sh` no longer silently reverts `maxReplicas` 45 → 30. **Five things in the original file did not survive**, and the sharpest is that a *controlled* run refuted the headline: uniform traffic at segment 3's exact arrival rate produced **1 replica and zero scale-up events**, so the scaler is correct on smooth load and the defect is specific to MAS's traffic *shape*. Also: "ratchet" is refuted (segment 2 ran longer and peaked lower, and both earlier runs scaled *down* mid-run); option B does not exist (no stabilization-window surface in ACA at all); the cost was **10× low, not high** (€3.00/run at list, €0 cash — Sponsored subscription); and the cost/429 trade is largely illusory because the ingress is **round-robin** and the 429 window is cold start, where there is 1 replica regardless. **The acceptance measurement is MAS's next run**, watched live — revert criteria pre-registered in the file. **`raw://` is now the load instrument** and should be reached for before any live host |
| ~~1~~ | ~~`consent-scripts-delete-the-page.md`~~ | M | **DONE 2026-08-06, undeployed.** `tasks/done/`. The diagnosis reproduced exactly; three things about the *fix* changed, and the first is the one to carry: dropping the 20 generic selectors would have deleted the measurement step 5 branches on, so they now **observe instead of removing** and log `chars`/`pagechars`. |
| ~~2~~ | ~~`total-loss-is-permanent-not-transient.md`~~ | S | **DONE 2026-08-06, undeployed.** `tasks/done/`. Keyed on the **capture shape** (no `<body>`), not the reason string — one test covers both production signatures, which two reason strings could not. Nothing pinned the old 500, so it was a bug fix and not a contract change. |
| 3 | `fixture-origin-bypasses-the-pinning-proxy.md` | S | `set_egress_proxy()` has one caller, `server.py:183`, so `ProductionPath` never starts the proxy and **all 66 fixture tests run on a network path production does not use**. A dead host is 134 s direct vs 30 s through the proxy — a test without it measures the wrong number by 4×. ~12 lines; expect some tests to change behaviour, and treat that as the payoff. The count moved from 54 to 66 with the `/consent/*` routes. |
| ~~10~~ | ~~`media-desc-duplicates-the-page-per-image.md`~~ | S | **SHIPPED into `main` 2026-08-09, undeployed — Tier 1 then Tero's deploy window is all that remains.** `MEDIA_DESCRIPTION_MAX_CHARS = 200` + upstream's own `truncate()` helper (`utils.py:3004`) in `find_closest_parent_with_useful_text`, `tasks/done/`. Measured: `media` **231,708,619 → 538,747 B (430×)**, `cleaned_html` and markdown **byte-identical by md5**, all **1,160** entries kept, offline suite **312 green**. **The diagnosis survived to the byte; eight peripheral things did not**, and three are worth carrying: the walk **never reaches `<html>`** in 78 real captures (lxml leaves `html.text` `None`); the pathological population was undercounted (**19 of 78** captures — 12 jpond *plus 7 accountor* — not 12 of 68); and "the cap is faster" was a single timing inside its own noise — `scrap()` gains ~8 %, **the 330× is `json.dumps` (0.655 s → 0.002 s)**. Also **`grumblo.com` is confirmed the same mechanism**, which the file listed as its largest uncertainty: one plain GET shows 272 images carrying **1,524,174 chars of `desc`, 88 % of its media payload**. **Do not read this as "response size is now bounded"** — the cap bounds `desc` only; `alt` is copied per variant, and **`media.tables` multiplies cell text by an unvalidated `colspan`** (a 4,624-byte page reaches 4,504,226 B of media; `colspan="2000000"` costs +91 MB RSS from 905 bytes of HTML). Neither is built; both need pathological markup and neither has ever been seen in production. That is what turns §3c from *unnecessary* into *parked* |
| ~~6~~ | ~~`inference-tier-500s-are-not-retryable.md`~~ | S | **CLOSED UNFIXED 2026-08-09, `tasks/done/`. Do not re-open without a page MAS can show has never succeeded.** The measurement was sound — 89 % of batch 1's 500s, 84 % of 14 days' `render_error` — but the *fix* is refuted by the only corpus that could refute it: `www.ktth.fi` returned **14,542 chars on 2026-04-17**, and the `laatutrio.fi` apex paths **21,234 and 14,564 chars on 2026-08-08**, the day this file called them deterministic. Marking them permanently dead converts a recoverable miss into **silent permanent loss on live sites** — the exact direction the taxonomy exists to prevent. MAS asked us not to build it and priced the cost as theirs and small (~1.5 % of a batch's wall clock). **PDFs are settled too:** MAS removes them at dispatch, and their April corpus shows PDF text extraction is a **regression, not a limitation** — though *what* produced that text is **not established** and their attribution to us is inference. **Four findings were rehomed, not lost:** the `browser_manager.py` channel downgrade + the CI gap (CLAUDE.md row, TESTING.md, two test comments), `response_headers` is the first redirect hop with **no final-hop field** (CLAUDE.md row beside `redirected_status_code`), `unrenderable_content` has fired **zero times ever** (the corrected download row + `aitosoft_failure_class.py`), and the untrusted-reachable `PDFContentScrapingStrategy` (`file-upstream-prs.md`). The fixture work its §7 argued for **survives on its own** — it is test work and never needed the classification change |
| 8 | **Two `failure_class` log holes + a `render_mode` mislabel** — no file yet | XS | **New, from segment 2.** (a) `render_mode: "static"` failed fetches log at INFO with **no `failure_class` field** (`aitosoft_static_mode.py:301,307`) while `_static_error_result` defaults the class to `origin_unreachable` (`:164-179`) — so **no `failure_class` query can ever count them**, and the hole opens exactly when a host has already misbehaved enough for MAS to pivot it to static. ~6 lines mirroring `api.py:1033-1039`; no double-count risk (static returns at `api.py:770`, never traversing the full-mode loop). (b) `api.py:1198`'s `failed_result(...)` omits `render_mode`, which defaults to `"full"` (`aitosoft_failure_class.py:507`) — and because the seed check (`:760`) precedes the static short-circuit (`:764`), a **static** request to a dead domain is reported to MAS as `"full"`. One word, in a field they parse |
| 7 | **The patchright tier retries classes already known permanent** — no file yet | S | **Re-justify it before starting: item 6 is closed, and item 7's saving can no longer be counted against it.** `render_error` is **not** in `NON_RETRYABLE_CLASSES` (`aitosoft_failure_class.py:129-133`), so item 7 as written would have saved **zero** of batch 1's 18 events — the two were listed as independent and were coupled. What remains is the `render_defect` leg alone, whose production population is small. The cost model, if it is worth having: one URL in this class measured `admits=8 fetches=32 completes=16 patchright=8`, i.e. 4 wire attempts × ~29.5 s = **32 navigations for one URL**. Original text follows. **New, from segment 2.** `_is_blocked` (`aitosoft_patchright_fallback.py:163`) gates the retry on the block-marker **string**, not on classified permanence, so `render_defect` — which is in `NON_RETRYABLE_CLASSES` — still gets an internal retry leg. That leg then dies on upstream's `wait_for_selector("body", timeout=30000)` (`async_crawler_strategy.py:898`), i.e. it waits 30 s for **exactly the element whose absence defined the failure** and can never succeed. ~a few lines; saves 2 navigations + ~60 s per URL. Fold in the fragment-strip for `CONSENT NAVIGATION` (§2 of the same file). Also open and *not* answered: **why `delotec.fi` has no `<body>` at 2015 bytes** — two engines agree, it is not our JS, and MAS holds the bytes |
| 4 | `guard-corpus-is-not-in-the-repo.md` | S | **After the sweep.** Real and verified — `test-aitosoft/artifacts/*` is gitignored, three tests fail on a fresh clone at `assert checked >= 30`. But its load-bearing sentence is **wrong**: "our only pre-deploy gate is the offline suite" is false (see corrections below), and it fails *loud*, in the safe direction. If ever done: 4–6 files into `artifacts/keep/`, the mechanism `.gitignore:14-17` already provides. Do **not** open its four-option sizing table before the sweep. **Item 1 raised its value slightly**: the 7-host corpus is load-bearing for a claim about consent selectors, and 2 of 2 CMP measurements is thin — though the `CONSENT DECLINED` counter now answers that from production instead. |
| ~~5~~ | ~~`flaky-fence-test-margin.md`~~ | S | **DONE 2026-08-06.** `tasks/done/`. Diagnosed before it was fixed, as the file demanded: the fence unwinds in **0.05 s**, so the product-finding reading is refuted; the variance is a cold browser launch *outside* the fence (healthy control median 1.33 s, max 4.05 s). Fixed by `FENCE_STALL_S = 8`, which widens the gap rather than the assertion's meaning, and costs the suite nothing. |

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

## The plan across both repos, and why it is in this order

Both repos are ours, both deploy into the same Azure, and MAS is our only
consumer. The steps below are sequenced by **what each measurement unblocks**,
not by convenience — so if a result comes back unexpected, the thing to re-read
is the reasoning attached to that step rather than the whole list. Each step
names who runs it, because the split follows **what each side can physically
see** (agreed in `tmp/mas-repo-messages/20-…` §6, accepted in `21-…` §4).

| # | who | what | why here and not elsewhere |
|---|---|---|---|
| ~~1~~ | **us** | **DONE 2026-08-06** — `0.9.2-consent-guard`, `--0000037`. Tier 1 4/4, prod smoke green, `kubler.fi` proved in production | It was the only thing that stopped data loss, and a 50-company run was held on it |
| ~~2~~ | **us, same image** | **DONE.** `CONSENT DECLINED` / `CONSENT STRUCTURAL` / `CONSENT NAVIGATION`, each carrying the requested URL beside the current one — verified firing in production | **A segment runs once.** Neither archive can hold this population — the element is deleted before capture — so segment 2 is the measurement, and a counter that missed this image would have waited for segment 3 |
| ~~relay~~ | ~~Tero~~ | **DONE** — `22-…` and `24-…` landed; MAS ran the `raw://` consent probe at 13:27 on 2026-08-06, which is arm-check traffic and proves they had 24 | — |
| ~~3~~ | **them** | The `remove_consent_popups` A/B — **arm-check probe seen in our logs 2026-08-06 13:27**, full result not yet relayed | A two-arm result answers "is the flag worth keeping", which does not change what we build. The third arm answers "does narrowing the selectors cost consent-wall coverage", which is the one thing our 7-host corpus cannot settle |
| ~~4~~ | ~~them~~ | **DONE 2026-08-06 13:38–14:36 UTC.** 261 renders, 61 domains, 58 min | 50 rather than 25 because our own measurement says the *activation count* costs, not the companies |
| **now** | **Tero** | **Relay `tmp/mas-repo-messages/28-…`** — the full segment-2 recap plus four corrections. **One is time-sensitive:** MAS pre-registered a "stop the sweep at ≥2 in 50 us-specific blocks" rule, and `kea.fi` is not one of them (it served us four pages, 403'd one path, has no HTTPS), so the real figure is **1 in 50** and the threshold must be re-derived *before* segment 3 or the sweep stops on an artefact | Nothing else is gating. 28 also hands them the scaling numbers: **`--concurrency` up to ~15 needs nothing from us**, above that our `maxReplicas` is the lever |
| — | note | **`25-…` and `26-…` were never files** — that exchange happened as pasted markdown in a chat. Both are now reconstructed on disk and **flagged as possibly-inexact**; every checkable detail was verified against our logs and holds (the 13:47:16Z 429 with `2/2 rendering, 4 queued`, `c6d1302332b8`, delotec's two timestamps, the gatelesis window). **Prefer files over chat** — this is the second numbering/delivery gap in this thread |
| ~~5~~ | ~~us~~ | **DONE — `tasks/done/segment-2-counter-readout.md`.** The loud channel is 3 domains of 61 (4.9 %) / 27 renders of 261 (10.3 %), all `node=html structural=True`; the silent channel is **0 of 261**; genuine click-navigations **0** (all 4 `CONSENT NAVIGATION` lines are a fragment-only false positive). Created two new items, 6 and 7 below | Branches below — it did reorder what follows, but *downward*: the consent family is closed pending one more segment, and the new work is cost, not data loss |
| 6 | **us** | Upstream PR for both JS files | "Here are N occurrences in a production sweep" is a far stronger submission than a synthetic repro, and upstream `develop` moves slowly enough that waiting costs nothing |

**Running in parallel on their side, blocking nothing:** persisting the final URL
and failure reason on every capture (the gap behind two questions neither of us
could answer this week), the trailing-slash double fetch, and turning the
sub-page queueing condition from a prompt line into a real gate.

**Optional, theirs, and the only retrospective handle on the silent channel:**
contact-shaped URL paths (`yhteystiedot`, `contact`, …) that returned
substantial markdown and **zero** emails and zero phones. It cannot attribute
cause — but measured before our image and again on the same cohort after, the
delta is the attribution.

### What step 5 branches on

- **Declined-removal counter fires often** → the silent inner-element channel was
  real and possibly large. Ask whether dropping the generic selectors was enough,
  or whether the *named* ones need the structural guard too.
- **Counter fires ~never** → the loud channel was the whole thing. Say so in the
  upstream PR, and stop treating the silent channel as an open risk.
- **URL-change counter fires** → decide whether to build re-navigation after a
  self-inflicted click. Below some rate, logging is the whole answer; MAS's
  measured ceiling is 0.046 % of companies, so the prior is "logging".
- **`render_defect` (item 2) fires at all after the JS fix** → something we have
  not identified is still deleting documents. That is a new investigation, not a
  tuning exercise.

### What would invalidate this plan

- **MAS's A/B showing the generic selectors do carry coverage.** Then item 1's
  "drop them" becomes "gate them", and the gate should be *positional* (a real
  banner is fixed or sticky; a footer is not) rather than text-proportion, which
  a 43.3 % measurement already killed.
- **A further message changing the diagnosis.** MAS runs several agents on this
  and their read has moved between messages — twice they corrected a claim of
  their own, and once we corrected a mechanism of theirs that reached the right
  answer by a route that does not exist. **Verify before adopting**, in both
  directions; that habit has paid out every time it was used this week.
- **Segment 2 finding a failure class we have not seen.** The capacity and memory
  families are settled to zero across three workloads; a new class would most
  likely be another content-fidelity defect, which is where our blind spots have
  consistently been.

---

## Parked on purpose — do not pick these up unasked

| Task | Why parked | What would un-park it |
|---|---|---|
| ~~`replica-memory-baseline-unexplained.md`~~ | **CLOSED and moved to `tasks/done/` 2026-08-06.** It had been marked closed in its own header since 2026-08-05 but was still sitting in the open directory, which is the same invitation the row warned about. Now **four** consecutive workloads with no symptom (p95 39.8 % → 29.9 % → 43.6 %, peak 63.8 %, against an 85 % guard; zero memory refusals throughout) | Nothing. If memory ever becomes a symptom again, that is a new file with new data |
| `cleaned-html-collapse-guard.md` — repair 1 (`unclosed-script`) | Purely prospective and **structurally uncountable**: zero production instances have ever been attributed to it, and the shape is invisible by construction. Its value is upstream PR quality, not our data | The segment-1 `COLLAPSE RECOVERED` / `RENDER DEFECT` split showing the shape actually occurs |
| `static-fallback-within-fence.md` | 0 × 504 in two workloads now; the hang it was sized against was fixed in `done/render-retry-unbounded-hang.md` | A real 504 population in a sweep |
| `blocked-host-retry-economy.md` | Cost optimisation, not a defect — and the 2026-08-01 run saw **0 blocks in 336 renders** | A sweep showing blocked-host cost actually hurts |
| `residential-egress-retry-path.md` | Population is floor 6 / ceiling 29, costs money, and 0 blocks were seen in the only recent traffic | A real count, then Tero |
| `static-mode-tls-impersonation.md` | Hardens a path nothing currently falls back to | `residential-egress-retry-path.md` |
| ~~`base-config-boolean-defaults-never-applied.md`~~ | **CLOSED 2026-08-09, `tasks/done/`.** Its un-park trigger is moot: `CrawlerRunConfig.set_defaults()` sets booleans today *and* honours an explicit client `false`, which the file's proposed merge-rule fix explicitly could not. The `config.yml` line is commented out with the reason inline — left in place it was a landmine, since fixing the merge rule would have turned user simulation on for every request | Someone wanting user simulation on, which is a **measurement**, not a merge-rule change |
| `preflight-batch-endpoint.md` | **MAS said do not build speculatively.** Their words | MAS asks |
| `file-upstream-prs.md` | Standing tracker, four PRs open and **a fifth written but deliberately unfiled** (the consent snippet — file it after segment 2, when it can carry production counts). Upstream `develop` is **one commit past v0.9.2** (a Docker IPv6 fix, checked 2026-08-02) — core behavioural changes sit for months and waiting for them is not a plan | Nothing — check occasionally |
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

**Count headline numbers twice, from two instruments, on purpose.** MAS proposed
this (`21-…` §4) after our two repos reconciled segment 1 independently and
agreed to the request — that validated *both* instruments and cost nothing,
because both sides had already counted. It earned itself twice in the same week:
**three of MAS's four flagged segment-1 findings turned out to be artefacts of
their own measuring tools**, and **our "two hosts in 30 days" figure came from
asking the logs one question instead of two** (`Near-empty content` is gated on
HTTP 200, so the same 15-byte capture at any other status lands under
`Structural: no <body> tag`; the real count is 2 + 11 hosts). Neither was caught
by review. Both would have been caught by a second count. This is cheap
specifically for numbers that decide something — do not turn it into ceremony
for every figure.

**Nine consecutive sessions have found the previous session's task file
materially wrong about something load-bearing** — that is the separation of roles
working (CLAUDE.md principle 6), not a quality problem. Verify the diagnosis, not
just the plan, and **check the arithmetic**, not just the logic. The sharpest
case: the record said 8 browsers at 165 MB "is the whole 4 GiB budget". That is
~36 %. Four sessions read past it.

The ninth (2026-08-06, the consent JS) is the first where **the diagnosis
survived intact** — every shape, every number and the branch trace reproduced
through the browser on the first attempt. What did not survive was the *design*,
in a way worth naming because it is new here:

- **A fix can delete the measurement the plan depends on.** The file said "drop
  the generic selectors", and dropping them is correct as a fix — but step 5
  of the plan above branches on how often the declined-removal counter fires,
  and a deleted selector cannot decline anything. They are kept and *evaluated*
  instead. **When a plan's next step is a measurement, check that the current
  step leaves the instrument attached.**
- **Two fixes covering one symptom need a fixture only one of them can pass.**
  With the generics gone, the Enfold class matches nothing, so every
  `<html>`/`<body>` consent test would have stayed green with the structural
  guard reverted — the suite would have asserted one fix twice and called it
  two. `/consent/named-root` is the shape that separates them.
- **A fixture shaped like the measurement can still be wrong.** The overlay
  measurement describes a full-width hero; a full-width element is removed by
  that script's *legitimate* size rule, which survives the fix. The route serves
  a 280×160 box, which only the degenerate clause could ever have removed. Same
  family as `/block/padded-403` — third time now.
- **Print the log line and read it.** The counters nearly shipped on
  `AsyncLogger`, which prints only when `verbose` is set (and `verbose` is
  *client-settable*), wraps at the console width so a 190-character line becomes
  two Log Analytics records, and eats `[` — deleting the CSS selector, the most
  diagnostic field in the line. Two minutes of looking; a segment's worth of
  measurement. Tests asserted the *data* and were green throughout.

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

## Corrections to the record, 2026-08-09

Found by a five-thread research pass and a second-opinion review, none by a failure. **The
review was given three conclusions and found load-bearing errors in all three** — which is
the tenth and eleventh consecutive time this has happened, and it happened here *before*
any code was written rather than during implementation.

> **Resolution pass, 2026-08-09 (third update):** 1 is acted on (CLAUDE.md Key Findings
> row + `base-config-…` closed + `config.yml` line commented out). 2 is **fixed in four
> places** and turned out to be sharper than stated — 4 of 5 download kinds are identical
> and only `pdf-inline` diverges, re-measured on both browser arms. 3 stands as written,
> unchanged, still do-nothing. 7 has moved from this list to `file-upstream-prs.md`,
> because a corrections section is a changelog and not a backlog. 4, 5, 6, 8, 9 and 10 are
> untouched and still apply.
>
> **The twelfth consecutive session found the previous file materially wrong**, and this
> time the implementing session found errors in **its own** work too: the code comment
> quoted the pre-marker figure (535,435 instead of 538,747), one test's threshold moved
> with the constant it was testing so it could not fail when the fix was removed, and a
> brand-new CLAUDE.md row asserting `media.tables` is "linear in the document" was refuted
> by the second-opinion pass within the hour. **All three were caught by review, none by a
> test** — which is the argument for running the review *after* writing, not only before.

1. **`CrawlerRunConfig.set_defaults()` exists, and this repo has been reasoning as though
   it does not.** `async_configs.py:1329-1330` decorates it `@_with_defaults` — the same
   upstream mechanism `aitosoft_entry.py:40` already uses for `BrowserConfig` and that
   CLAUDE.md calls our key technique. The **`base_config`** merge at `api.py:876-880`
   genuinely cannot set a non-`None`/non-`""` default (the `max_retries` trap), but that
   is *one route*. Consequences: item 10's fix needs no MAS coordination, and
   **`base-config-boolean-defaults-never-applied.md` is un-parked by the same one-liner**
   (`simulate_user` would start working). Worth a CLAUDE.md row next to the `BrowserConfig`
   one.
2. **CLAUDE.md's "inline `application/pdf` behaves exactly like `Content-Disposition:
   attachment`" is false in production**, and the task file that shipped the class said so
   at the time (`done/download-navigation-is-not-a-render-error.md:27-30`) — the caveat was
   written, published, and then dropped by every downstream reader including that row.
   Real Chrome ships a PDF viewer; bundled headless does not. **Fix the row.**
3. **The pool memory guard is NOT unreachable, and the upward trend is our own scale
   change.** Both claims were mine and both are wrong. The guard
   (`crawler_pool.py:410-411`) is a **new-browser admission check by design** and it *has*
   run — 441 creates on 08-09 — it has simply **never read ≥85.0** since 2026-08-01 (max
   at-guard **84.8**, missed by 0.2). On 2026-07-31 it read up to 95.6 and **fired 9
   times**. The "7 minutes above the guard" is ~**140 s** interval-weighted (2.2 % of that
   replica's life), and the 63.8 → 80.9 → 86.7 % trend across segment 2 / segment 5 /
   batch 1 tracks **admits per replica: 9.1 → 95 → 97** — i.e. our own ACA scale-trigger
   change 2 → 6, not cohort size. **Cohort size cannot be the driver**; per-replica load is
   bounded by MAS's fan-out, which this file already records as independent of cohort size.
   Also: `get_container_memory_percent` subtracts only `inactive_file` (16 MB at the peak)
   while ~566 MB of *active*, reclaimable file cache stays charged, so nominal headroom of
   545 MiB is really ~1.1 GB; and the janitor's adaptive interval (10 s >80 %, 30 s >60 %,
   60 s otherwise) **self-selects dense sampling in high-memory states**, overstating "time
   above 85 %" by **5.3×** (1.38 % of samples vs 0.26 % interval-weighted). **Max is
   unbiased; p50/p95 and time-above-X are not.** 14 days: no `OOMKilled`, no exit 137, no
   `Evicted`. **Verdict: do nothing to behaviour. Fix the instrument** (move the janitor's
   memory read after the sleep; interval-weight the readout). **Re-open only if the
   guard's own `Creating new browser … mem=` reading crosses 85, or an OOM appears** — and
   do **not** make the guard fire on pool-hit paths, which would 429 requests that need no
   allocation.
4. **`ContainerAppHTTPLogs` has no `_CL` suffix.** The `_CL` name errors. It also retains
   ~5 days against the console table's longer window, so date-bound any query against it.
5. **A naive `countif` on a log substring overcounts events.** `DNS: host does not resolve`
   emits **four** lines per refusal (the `Crawl error:` line, two traceback lines, the
   `ORIGIN FAILURE` line): 12 lines for **3 events** in batch 1, 336 lines for **84 events**
   in segment 5. Same family as the `failure_class=`-not-the-token rule already recorded —
   **count events, not lines.**
6. **The `[ANTIBOT]` log line truncates the URL and drops the extension.** A query
   filtering `.pdf` finds `admits=8, fetches=32` but `antibot=0`. Never filter anti-bot
   lines on anything at the end of a URL. Same family as the known `AsyncLogger` defects.
7. **`PDFContentScrapingStrategy` is reachable from an untrusted request body.** It is in
   `UNTRUSTED_ALLOWED_TYPES` and `scraping_strategy` is in
   `UNTRUSTED_FIELD_ALLOWLIST["CrawlerRunConfig"]` (`async_configs.py:194`, `:238`), and its
   `_get_pdf_path` does a blocking `requests.get(url, stream=True, timeout=(20, 600))`
   **on the event loop**, bypassing `validate_url_destination` and the pinning egress
   proxy. Latent, not live — our only client is trusted and token-gated — but it is a real
   hole in upstream's own boundary. Upstream report + a one-line tightening in
   `aitosoft_trust.py`.
8. **`www.wtwco.com` returned HTTP 429 to us in batch 1** after MAS's intra-company fan-out
   hit it three times within 2 seconds. That is the **first direct evidence for the
   per-host spacer** we have been asking for, and it is invisible from MAS's side because
   the pages eventually succeeded. Their spacer is built and lands in batch 2 — **verify
   from our logs that it actually landed**, which is one query.
9. **MAS's batch-1 500 count (14) is 4 low** — two of our instruments say **18**. Every
   repeated URL got a fourth attempt they did not list.
10. **MAS's dispatch-side PDF gate had not shipped as of batch 1.** Their `aitosoft-edge`
    has been on `v0970-dispatch-egress-guards` since 2026-08-08 09:36, and at 10:34 on
    08-09 both PDF URLs were still dispatched and retried 4× each. Treat "they are fixing
    it" as an intention, not an observed fact.

---

## Corrections to the record, 2026-08-06

1. **"Nothing in this repo gates MAS's sweep" is no longer true.** It was true on
   2026-08-05 and is false now. Fixed at the top of this file.
2. **The `norex.com` class was never a detector problem.** Five tracked files
   (`AITOSOFT_CHANGES.md:423`, `aitosoft_failure_class.py:191`,
   `tasks/done/antibot-minimal-text-false-positive.md:6`,
   `tasks/done/detector-round3-evidence-vs-inference.md:148`,
   `test_failure_classification.py:535`) say the body "was our own
   `Crawl4AI Error:` placeholder in 15 bytes of HTML". That conflates two fields:
   `html` is 15 bytes of bare doctype, and the placeholder is what our *scraper
   generated from* those 15 bytes. Both statements were individually true, and
   reading them as one sent four sessions looking at the anti-bot tier instead of
   at our own DOM cleanup. Worth fixing in those files when someone is next in
   them.
3. **Our 30-day population count was an undercount, in the reassuring
   direction.** See the standing rule above. Query both reason strings.

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

**`22-to-mas-the-image-is-out-and-here-is-how-to-read-the-counter.md` is written
and needs relaying.** It announces the image and the one wire-status change
(`render_defect` at 200 for a deleted root), delivers their `21-…` §6 ask (the
requested URL beside the current one in every counter line), and asks for two
things: the **three-arm** A/B (off / on-today / on-with-this-image — arm 3 is
the only one that answers anything we cannot) and segment 2 with the window
announced first. Its §3 corrects our own plan: the `chars`/`pagechars` **ratio
does not separate** a wrapper holding contacts (9.4 %) from a genuine cookie bar
(7.3 %) — read `node` and `class` first, absolute `chars` second, the ratio
last. Its §5 table says in advance what each counter outcome would make us do,
so nobody has to guess when the numbers land.

**The 2026-08-05/06 exchange (`17-…` through `21-…`) is the densest we have had
and most of it is settled.** Read `20-…` if you read one — it is ours, it carries
every measurement behind `done/consent-scripts-delete-the-page.md`, and its §6 is
the division of labour both sides then agreed to. What closed:

- **`16-…` §0 landed and works.** Three genuinely dead domains came back
  `origin_unreachable` and MAS's agent filed them as *"this company has no
  website"* rather than as our refusal. One of them (Provesta) then found the
  company's real site and captured it fully. `SSRF` appears zero times in the run.
- **`failure_class: null` on our 500s was never ours.** Their `parseErrorBody`
  returned a display string and never lifted the field onto the result object.
  `server.py:529-539` was correct throughout. They have fixed it, and have
  withdrawn the ask that was built on it.
- **`failure_class: "none"` on 404 / 400 / 522 is one mechanism, not three.**
  Those pages genuinely rendered; the status codes are the *origin's* own, and
  the 522 proves it since we cannot emit a Cloudflare status. Complaint withdrawn.
- **Raw Unicode hostnames work end to end.** Our offline test (`getaddrinfo`
  IDNA-encodes; Chromium sends the punycode `Host`) and their live production
  probe agree byte-for-byte. Their probe went through the pinning proxy, so this
  is measured and not inferred. **Closed, nothing to build.**
- **Their `max_retries` is 1**, confirmed from their config, and **their sub-page
  queueing "condition" was agent judgment, not code** (`19-…` §2) — so revert to
  worst-case sizing for dead-but-resolving hosts until they tell us it shipped.

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
| (g) | count of interstitials carrying no marker, no prose and no notice | We deliberately do not catch this class and cannot count it. A number lets us stop wondering |

**(c) is answered and the answer reframes it.** The `render_error`-at-500
population is **2 hosts in 30 days** (`kubler.fi`, `norex.com`) — and *both were
this bug*. The class we created to stop mislabelling `norex.com` was treating a
symptom of a defect we had not yet found. So the old advice ("if the population
is large, make the inference tier less eager") is moot: the right change is the
JS, not the tier.

**(f) has a partial answer from MAS's own archive** (`21-…` §2b): of 41 companies
where every stored page is byte-identical, **26 have every page at 1 character**
— the known empty-capture class, our `<noscript>` family. That is a floor for the
population, measured across 17,439 companies, and it is a different bug from the
consent one.

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
