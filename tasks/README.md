# Open tasks, in the order to do them

**Updated:** 2026-08-02 by the coordinator, after reading the first real
production traffic the current image has served.

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

**Production is `0.9.2-pool-cap`, revision `--0000033`**, 2 vCPU / 4 GiB,
`minReplicas: 0`, `maxReplicas: 30`, scale rule 2 concurrent/replica.
`main` and production are in sync.

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

## The open items, in order

**Old items 1 and 2 shipped together on 2026-08-02** as `0.9.2-collapse-recovery`
— collapse recovery and `unrenderable_content`. Both task files carry what the
implementing session found wrong; the short version is that **three load-bearing
claims across the two files did not survive**: recovery could not reuse static
mode's pipeline (only its converter), the obvious acceptance bar opened a new
silent-loss channel, and the download failure arrives as a failed *result*, not
an escaped exception. Details in `AITOSOFT_CHANGES.md` 2026-08-02.

| # | Task | Size | What to know |
|---|------|------|--------------|
| 1 | `cleaned-html-collapse-guard.md` — **price `content_source="raw_html"` before writing any repair** | ~1 h | The principle-7 question neither task file asked, found by the pre-deploy review. Upstream already has the seam; generating markdown from raw HTML would make the collapse **not happen** for the noscript and deep-nesting families rather than catching it, and probably for `unclosed-script` too. Two independent measurements say the quality cost is small (0.9988–1.0066 on 5 of 6 hosts; median 0.91× across 59 stored captures). Measurable offline against the 66 stored captures. If it holds, it deletes items 2 and 3 below. |
| 2 | `cleaned-html-collapse-guard.md` — **repair 1, scoped to `unclosed-script`** | M | Only if #1 does not dissolve it. Recovery closed repair 2 outright and covers `unclosed-noscript`, which leaves `unclosed-script` as the **one silent member** — `success: true`, zero markdown, guard structurally blind. That is the whole argument for repair 1, and it is still the strongest of our four upstream PRs. Recovery is now a live classifier, so the next sweep's log split (`COLLAPSE RECOVERED` vs `RENDER DEFECT … recovered 0 chars`) sizes this shape for free. |
| 3 | `flaky-fence-test-margin.md` | ~1 h | Our only pre-deploy gate is "the offline suite is green", and this test fails ~1 run in 3 for reasons unrelated to the code. **Diagnose before widening**: the same red can mean harness overhead *or* a fence that unwinds slowly under load, and the second is a finding about our 180 s fence against Azure's 240 s ingress limit. It did **not** bite across the three full runs on 2026-08-02, so the 1-in-3 figure may itself be stale. |

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
| `replica-memory-baseline-unexplained.md` | The 59 % may be an artefact of a metric that changed under it, and the 2026-08-01 run measured p95 **39.8 %** with zero refusals. There is no symptom left to explain | The guard firing again, on real traffic |
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

**Six consecutive implementing sessions found the previous session's task file
materially wrong about something load-bearing** — that is the separation of roles
working (CLAUDE.md principle 6), not a quality problem. Verify the diagnosis, not
just the plan, and **check the arithmetic**, not just the logic. The sharpest
case: the record said 8 browsers at 165 MB "is the whole 4 GiB budget". That is
~36 %. Four sessions read past it.

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

## Cross-repo state

MAS (`aitosoft-platform`) is our only consumer. The exchange is markdown files in
gitignored `tmp/mas-repo-messages/`, numbered and direction-labelled, relayed by
Tero both ways. Durable conclusions get copied into the forensics record; the
messages are the transcript, not the source of truth.

**The ball is with them.** Message 11 (sent 2026-08-02) asked for a cold-start
re-scrape of their 243 hosts and eight lettered reports. Since then they have run
~30 sites of real traffic instead, which answered some of it from our side.

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
  bytes are still welcome but no longer gating, because recovery (item 1)
  classifies the mechanism for free.
- **(h) the sweep's shape** — being handled by process instead: MAS will notify
  before heavier scraping so it can be watched live.

**Two agreed changes are unblocked and unshipped**, both additive, both waiting
only on a reason to open an image: the `fodbar.fi` "content was present despite
the origin status" field (MAS names it), and flipping envelope `success` to the
aggregate — which must ship **alone**, since it breaks a pinned contract
(`test_static_mode.py:257`) and buys no behaviour.

**To announce in the next relay** (shipped 2026-08-02, additive, no behaviour
change on their side — per this file's own rule, additive changes ship and get
announced):

- A new `failure_class` value, **`unrenderable_content`** — HTTP 200,
  non-retryable, for a URL that answers correctly with something that is not a
  web page (vCard exports, PDFs, any `Content-Disposition: attachment`). It used
  to reach them as `render_error` at 500 and cost them three retries.
- Worth telling them because it is *their* lever, not ours: **`render_mode:
  "static"` would fetch that vCard's body** and hand them the actual contact
  card, which is the data they were crawling the page for.
- Collapse recovery: some captures that used to arrive `render_defect` now
  arrive as ordinary successes with markdown. No field changed, no status
  changed. If they want a "this markdown came from the fallback" flag, the name
  is theirs to pick — same as the `fodbar.fi` field.

**How to run this exchange**, since it is easy to get wrong: the *channel* is
correspondence, but the *contract* has no home — MAS's model of our behaviour is
reconstructed from eleven messages, which is how `render_error` came to mean two
wire statuses for weeks without either side noticing. If a third party ever
joins, or if the taxonomy changes again, write the contract down as its own
versioned document rather than growing the message chain. And **never let a relay
block a deploy**: that coupling is what dropped the `fodbar.fi` field from a
finished image. Additive changes ship and get announced; behaviour changes wait
for the relay.
