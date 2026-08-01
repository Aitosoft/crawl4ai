# Aitosoft Changes Log

This file tracks all modifications made to the crawl4ai fork for Aitosoft's internal use.
Keeping this log helps when syncing with upstream updates.

---

## Current State

**Last Updated**: 2026-08-02

> **`main` is ahead of production.** The `pool.max_browsers` cap (`8e69c3a`,
> merged 2026-08-02) is on `main`, offline-green, and **not deployed** — it needs
> two small fixes first (`tasks/pool-residency-unbounded.md` §"Before this
> deploys"). Read the deployed image tag below, not `git log`, when you need to
> know what is running.

### Version
- **Local**: v0.9.2 (upstream/develop 2026-07-16) + Aitosoft patches (see entries below)
- **Production**: the above + collapse guard + one wire status per failure class + detector round 3 (padded blocks caught, inferred blocks no longer reported as the origin's) + patchright retry capture wait + memory guard 429 (deployed 2026-08-01)
- **Docker Image**: `aitosoftacr.azurecr.io/crawl4ai-service:0.9.2-detector-round3` (revision `crawl4ai-service--0000032`, digest `sha256:41ffd880d2f3a1e28136f2e03b53bf4a83c8ce994b6447d2c90096d70ace67a9`)
- **Previous**: `0.9.2-failure-class` (revision `--0000031`, deployed 2026-07-30)
- **Prod smoke 2026-08-01 (detector-round3)**: health ✅, unauthenticated POST /crawl → 401 ✅, render-capacity invariant `render_capacity=2` == `http-renders` rule ✅, revision `--0000032` Running at 100 % traffic with `--0000031` deprovisioning (checked **before** the crawl — the 2026-07-30 smoke was taken mid-cutover and reported pre-fix output) ✅. `caverna.fi` → HTTP 200 / `success:true` / `failure_class:"none"` / 1210 B markdown / 4.8 s ✅ — byte-identical markdown to the pre-deploy Tier 1 run, i.e. the widened detector and the collapse guard both stayed silent on a healthy page in production.
  **Not smoke-tested in prod, deliberately:** the four padded-403 hosts. Confirming defect A against `talpa.fi` would be a live request to a host MAS has already burned, to verify a pure-Python status/body rule that 232 offline tests exercise through the real production path. MAS re-scrapes those hosts naturally, so their next sweep is the production confirmation at zero marginal traffic.
- **Prod smoke 2026-07-30 (failure-class)**: health ✅, unauthenticated POST /crawl → 401 ✅, render-capacity invariant `render_capacity=2` == `http-renders` rule ✅. `caverna.fi` → 200 / `success:true` / `failure_class:"none"` / 1210 B markdown (2.8 s) ✅. **`konecranes.com` — the reported incident — → HTTP 200, `success:false`, `status_code:403` (was `301`), `redirected_status_code:403`, `failure_class:"origin_blocked"`, real `error_message`** ✅ — previously `success:true` with the Varnish block page as content, and before that an opaque retried 500. Both fixes visible in one response, which is what this image was assembled for. Caveat: the first smoke run hit revision 0000030 mid-cutover and showed pre-fix output; re-run after traffic reached 100% on 0000031.
- **Prod smoke 2026-07-17 (fence-obs)**: health ✅, authenticated render 200 (1.1s, new revision) ✅, "RenderGate ADMIT url=… waited=0.0s in_use=1/2" visible in container logs ✅ (Tier 1 4/4 was run pre-deploy vs local server, `--version fence-obs-local`)
- **Prod smoke 2026-07-17 (single-url)**: health ✅, 2-URL request → 400 w/ contract message ✅, single-URL caverna.fi crawl ✅, Tier 1 regression 4/4 ✅
- **Prod smoke 2026-07-17 (static-hardening)**: health ✅, static spot check caverna.fi ✅, Tier 1 regression 4/4 ✅, live SSRF probe (static redirect→10.0.0.1 blocked, opaque error, 200 envelope) ✅
- **Prod smoke 2026-07-17 (render-gate)**: health ✅, auth 401 ✅, MAS-shaped crawl (render_mode:full, 4.0s) ✅, static mode ✅, js_code rejected 400 ✅, 8-way burst → 6×200 + 2×429@0.85s w/ Retry-After ✅, http-scaler scaled 1→2→4 during burst ✅, probes green ✅
- **Prod smoke 2026-07-17 (pool-cleanup)**: health ✅, single-URL caverna.fi crawl ✅ (full render 3.9s), Tier 1 regression 4/4 ✅, replica logs clean (permanent browser init, cold→hot promotion at count=3, RenderGate capacity 2, no janitor/force-close warnings) ✅

### Production Deployment
- **Endpoint**: `https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io`
- **Location**: West Europe (co-located with MAS)
- **Resource Group**: `aitosoft-prod`
- **Authentication**: ✅ Enabled — upstream `AuthGateMiddleware` (static Bearer token, fail-closed, constant-time; only `/health` public) since v0.9.2
- **Status**: ✅ Running

### Environment
- **Host**: Windows 11 (Snapdragon X Elite, 32GB RAM)
- **Local Path**: `c:\src\crawl4ai-aitosoft` → `/workspaces/crawl4ai-aitosoft`
- **Dev Container**: Python 3.11 on Debian Bookworm
- **Key Tools**: Node.js 20, Azure CLI, GitHub CLI, Claude Code

### Tests
- Offline suites green: test_mas_contract.py (11), test_admission.py (10), test_static_mode.py (10), test_crawler_pool.py (4), test_patchright_fallback.py (4), test_redirect_block_detection.py (11), test_render_bounds.py (17), test_failure_classification.py (34), test_noscript_body_collapse.py (11), test_antibot_challenge_detection.py (18) — **130 pure-function tests, ~8 s**
- Plus test_fixture_origin.py (23) — browser-driven against a local fixture origin, ~50 s. **`pytest test-aitosoft/` = 153 tests, ~60 s, all offline** (the four live CLI scripts are no longer collected; see `test-aitosoft/conftest.py`)

---

## Detector round 3, phase-2 capture wait, memory-guard 429 (2026-08-01)

Four items in one image, deliberately: **the two detector defects pull in
opposite directions and their net effect is only measurable in a single deploy.**
Shipping either alone spends the measurement for nothing.

### Defect A — an 80 KB body whose entire content is "403 - Forbidden" passed

Four hosts (`talpa.fi`, `dining.fi`, `cisa.fi`, `jjsteel.fi`) returned 80,671
bytes rendering to `# 403 - Forbidden / Access to this page is forbidden.` at
origin status **202**, `success: true`, `failure_class: "none"`. The identical
bytes at status **403** were classified correctly on four other hosts. Every
size gate in `antibot_detector` read `len(html)`, and this vendor pads its block
page to 80 KB.

Fixed by two changes that are only useful together:

1. **The evidence gates moved off `len(html)` onto visible text.** The challenge
   tier's `html_len < 10000` is gone; the gate is now
   `_CHALLENGE_MAX_VISIBLE_TEXT` alone, and prose is matched against a
   script/style-stripped snippet so 80 KB of inline CSS cannot hide two lines.
2. **A new block-notice tier**, at any status and any size: a page whose whole
   visible text is a refusal *is* a refusal.

**Correction to the task file, which specified this work.** It stated that "the
four caught hosts prove the pattern side already works", so moving the gates
would be enough. Measured 2026-08-01: **no tier-1, tier-2 or challenge pattern
matches that body at all** — the four caught hosts were caught by the 403/503
branch's fallthrough, a status rule. A gate change alone closes nothing. Half
the fix was missing from the specification.

**Two false-positive hazards the tier is shaped around, both from measurement:**

- MAS's corpus scan found ~15 of 22 `Access Denied` hits were healthy Shopify
  storefronts carrying an `/pages/access-denied` navigation link, and our own
  fixture for that family measures **247** characters of visible text — *under*
  the new 500-character gate. "The words appear on a low-text page" would have
  re-opened it verbatim. A notice therefore counts only when the origin put it
  in the `<title>`/`<h1>`-`<h3>` (the idiom the tier-2 pattern already uses) or
  the matched text is ≥50 % of everything the page says.
- The 500-character gate is measured, not picked: the smallest healthy content
  page in our 58 stored real captures carries **739** characters, and everything
  below is a cookie wall (0) or an interstitial (58). It is also
  `aitosoft_collapse_guard.MIN_VISIBLE_TEXT_CHARS`, so the detector and the
  guard meet on one boundary instead of overlapping or leaving a gap.

**A second instance found in our own artifacts directory.** `monidor.com` — a
real stored capture, returned to MAS at `success: true` — is an 11,515-byte
interstitial with **58** characters of text and the title `One moment,
please...`. It sat over the old 10 KB challenge gate. Two patterns were added
from its body; the gate change alone would not have caught it either.

### Defect B — four `origin_blocked` verdicts that were not blocks

`is_blocked` returns one verdict for two kinds of finding, and
`aitosoft_failure_class` mapped both to `origin_blocked`:

| evidence | example reason | what it establishes |
|---|---|---|
| the origin said so | `HTTP 403 with HTML content`, a vendor marker | the origin blocked us |
| we inferred it from shape | `Structural: minimal_text…`, `Near-empty content…` | *we* came back with nothing |

The second is `render_error`'s definition. 4 of MAS's 33 `origin_blocked`
verdicts were this, and the expensive one was **`norex.com`**, where the body
was **our own** `Crawl4AI Error: This page is not fully supported` placeholder
in 15 bytes of HTML — our pipeline's failure reported to the customer as the
origin blocking them. This module's documented bias ("unrecognised failures are
`render_error` and never an origin class, precisely so that a healthy site is
never reported permanently broken") was running backwards.

`_INFERRED_BLOCK_RE` now recognises the inference reasons and lets them fall
through. **Discarding the reason does not discard the status**: 403/503 still
mean blocked (Incapsula and Varnish serve blocks with 503), any other 4xx/5xx
becomes `origin_http_error` — which is where `snuup.fi`'s ordinary 404 lands —
and a result with no origin status at all reaches `RENDER_ERROR`. That last
branch was added after an existing test caught the first version throwing the
status away with the reason.

`fodbar.fi` is **unchanged by decision** (MAS message 09 §5): the origin said
403, so we report 403. Overruling a status because the body looks like content
is the same shape as the `norex.com` invention pointed the other way.

**The cost, stated because it is not free:** `norex.com` and
`jarvenkylamaatila.fi` move from `origin_blocked` (200, terminal) to
`render_error` (500, retried 3×), so we buy back three renders per occurrence.
That is the correct direction for a transient failure of ours, and `snuup.fi`
gets strictly cheaper.

### How A and B compose, which is the reason for one image

The same block page under the 50 KB gate used to be caught by **tier 3** —
`Structural: minimal_text, no_content_elements`, an inference. Defect B stops
that meaning `origin_blocked`. Without defect A it would now report
`render_error`: a real block, reported as our own bug. The block-notice tier
catches it first, as evidence, so it stays `origin_blocked`.
`test_the_padding_is_no_longer_the_difference` is that assertion.

### The fixture was wrong on the axis that decides the fix

`/block/padded-403` served its notice in a bare `<div>` — **zero** content
elements, so tier 3 scored two structural signals and needed only the size gate
to move. The page MAS actually measured has an `<h1>` and a `<p>`: **two**
content elements, one signal, still undetected after a gate change. A fix
validated against the old fixture would have looked complete and closed none of
the four hosts. Both shapes are now served (`?shape=heading` default, `?shape=bare`)
and both are parameterised into the tests, because they exercise the two
discriminators separately.

### Phase 2: the patchright retry gets its own capture wait

`maybe_retry_blocked` had always handed patchright **the same
`CrawlerRunConfig`** — hence the same `delay_before_return_html` — so the second
attempt differed only in engine and could not, by construction, resolve a
challenge the first attempt had already outlasted. It now gets
`crawler.retry_capture_wait_s` (10.0), clamped to never lower a client's own
higher value.

Measured offline over an 84-cell grid: a capture wait `W` gets any challenge
resolving within **`W + 1.22 s`**. MAS's production 2.0 covers ≤ 3.2 s; 10.0
covers ≤ 11.2 s. Zero extra page loads (that second fetch already happens for
every detected block), zero cost on the happy path, and it runs inside the
existing wall-clock fence.

**Do not get the same effect by raising the global `delay_before_return_html`:**
at MAS's ~120,000-fetch sweep that is ~267 render-hours, and blocked hosts pay
it twice. Targeted, it is 8–36.

**The measurement phase 1's footnote asked for.** Phase 1 modelled a wall as
`2 × (W + 1.22)` and found W=10 misfitting by 2.78 s, warning that the retry leg
had to be measured rather than assumed. Measured through the real path: the
retry's fetch takes **11.26 s** at W=10, i.e. `W + 1.22` to within 0.04 s. The
retry leg is not where the extra cost lives; patchright singleton startup is the
remaining candidate and is a one-off per process.

**What it cannot do:** rescue an interstitial we never detected. The trigger is
the detector, which is why defect A ships in the same image — detection is the
ceiling on this recovery.

### Memory pressure answers 429, not 500

All nine HTTP 500s in MAS's 2026-07-31 probe were `crawler_pool.py`'s memory
guard raising `MemoryError`, which `api.py`'s generic `except Exception` turned
into a **500** with `failure_class: render_error`. MAS retries 500 three times
with 1s/2s/4s backoff, so the service answered memory pressure by **quadrupling
its own load**, on a single cold replica carrying the whole opening burst alone.

"We are full" already had a correct shape here — RenderGate's 429 +
`Retry-After` — so the guard now raises `RenderCapacityExceeded` and both paths
map through one helper. Same defect shape as the `render_error` split above: one
condition, two wire statuses, and the expensive one was not chosen deliberately.

**This is a symptom fix and is labelled as one.** The cause it named — nothing
bounds how many browsers the pool holds — is real, but **it is not what made the
guard fire**; see the 2026-08-02 entry below, which measured it and corrected
this paragraph.

---

## 2026-08-02 — a cap on live browsers, and the diagnosis it was built on

### `pool.max_browsers` + LRU eviction of idle browsers (`crawler_pool.py`)

`render_capacity` bounded concurrent renders and `max_pages` bounded pages per
browser; **nothing bounded live browsers**, so residency tracked *distinct
configs seen in the last TTL window* rather than concurrency. Now capped at
`pool.max_browsers` (6), enforced in `get_crawler` by evicting the
least-recently-used **idle** browser.

Verified end to end through `ProductionPath` with real Chromium, 12 crawls with
distinct `browser_config`s: browsers 1–6 grow the pool, and from #7 every create
evicts one and the cgroup **flatlines** — +15 MB over six more browsers, against
+168 MB each before the cap.

**The design rule is "never wait", and it is the whole safety argument.**
`release_crawler` takes the same `LOCK` to decrement `active_requests`, so any
wait inside `get_crawler` while holding it waits on code that needs the lock the
waiter holds — a total pool deadlock with no 504, no 429, and no janitor
recovery. `get_crawler` therefore evicts or refuses, never blocks; the refusal is
`RenderCapacityExceeded`, the only type `api.py` maps to 429 + `Retry-After`.
Evicted browsers are closed in a **detached, timeout-bounded task** because
`close()` carries no timeout of its own and a wedged Chromium closed inline would
hold the pool lock forever. Unreachable in MAS's traffic anyway: the gate admits
2 concurrent renders against a cap of 6.

Also removed: the janitor's **memory-adaptive TTL collapse** (`cold_ttl` → 30 s
above 80 %). It closed browsers exactly when memory was tight so the next request
had to launch a fresh one — 136 launches for a working set of 10–12 signatures.
The poll *interval* stays adaptive. The `📊 Pool:` line is now logged
unconditionally and carries `resident=N/cap`; its old `mem_pct > 60` gate meant
pool composition was only observable where it was already high, which is what
made the measurement below cost a Log Analytics regression.

### What the measurements corrected, and this is the important part

- **Peak residency was 9–10 browsers per replica, not 8.** The 8 came from one
  post-cleanup janitor line plus an inferred permanent browser; counted properly
  (cumulative create/close over 276 log events) the peak is 9 on `btv4v` and 10
  on `5hbkd`.
- **Browsers are not where the memory was.** Regressing all 68 pool-stats lines
  of the 2026-07-31 probe: `mem% = 59.3 + 2.65 × browsers` (n=68, r² = 0.22).
  A resident browser costs ~109 MB of a 4096 MB replica, and **~59 % of the
  replica is baseline no eviction can reach** and nobody has explained. 9 × 165
  MB is ~36 % of the replica — the record's "that is the whole 4 GiB budget"
  never closed arithmetically. **So this cap would not have prevented the nine
  500s and will not prevent the next ones.**
- **The realistic-page worry was real but small.** A new `/heavy` fixture route
  (median of 62 stored captures: 236 KB, 17 images, ~900 tags) costs +170.0 MB
  cgroup per browser against `/ok`'s +142.8 MB — **+19 %**. A pooled browser's
  cost is the Chromium process, not the page.
- **`pool-browser-retains-last-page.md` is closed as refuted.** Every pool
  browser really does keep its last page open (now reported directly by the
  experiment). But navigating it to `about:blank` returns **0.5 MB of anon per
  browser even when the page holds a fully-committed 100 MB JS heap** — and the
  same run proves the instrument is not blind, since loading that heap raised the
  per-browser cost by exactly +100.5 MB. Per-browser cost is a **ratchet** set by
  the heaviest page a browser ever loaded, and only closing the browser resets
  it. That makes eviction the only reclamation mechanism the pool has.
- **The permanent browser is unreachable by construction, not by contract.**
  `server.py` builds its config without `enforce_egress`, which every request
  path applies and which flips `ignore_https_errors` True → False, so the
  signatures differ in a field no client controls (boot `5e3e8048e7be` vs request
  `b318c5753575`). The previously recorded reason ("MAS always sends a
  `browser_config`") is wrong; a request sending `{}` would miss too.
- **Signature cardinality is *observed* small, not *bounded* small.** The
  "10–12 per replica, so the 15,000 worry is unfounded" refutation used a
  `dcount` **per replica** across ~5 replicas, which cannot bound the global
  count. And `user_agent_mode: "random"` is in `UNTRUSTED_FIELD_ALLOWLIST` and
  regenerates the UA per construction — one signature per request, a write-only
  pool — and our own shipped client doc recommends it. The cap is correct under
  both models, which is now its main justification.

**Not fixed, found in passing:** `monitor_routes.py:273-284` calls
`init_permanent` inside `async with LOCK`, and `init_permanent` acquires the same
non-reentrant lock — a self-deadlock that kills the replica permanently.
Admin-gated, off the traffic path, and it deserves its own attributable change.

Config: `crawler.pool.max_browsers: 6`, `crawler.pool.evict_close_timeout_sec: 30`.
Tests: `test_crawler_pool.py` 4 → 24, including four that exist specifically to
turn a deadlock into a failing test rather than a hung suite.

Two smaller items ride along:

- **`get_container_memory_percent()` reports the working set**, subtracting
  `inactive_file` (reclaimable page cache). Correct on its own terms and worth
  most on a cold replica, but a bounded offset — 1 % of pool growth warm, 16 %
  cold — not the explanation for that incident. Shipped because it is right. A
  bogus `inactive_file` larger than usage is ignored, so a bad stat read can
  never *hide* pressure.
- **The permanent browser is closed when nothing has ever used it.** `Using
  permanent browser` fired **0 times in 224 pool gets**: MAS always sends a
  `browser_config`, so `_sig` never equals `DEFAULT_CONFIG_SIG` and the boot
  browser held ~139–165 MB for the replica's whole life. `get_crawler` already
  re-creates it lazily.

### Deliberately NOT in this image

- **Flipping envelope `success` to the aggregate.** Agreed with MAS, but their
  message 09 says the envelope `success` is **never read** on 2xx — they take
  `results[0]` — so the flip buys no behaviour while breaking a pinned contract
  (`test_static_mode.py:257`) in an image that already changes static mode's
  wire-status mapping. Coordinator decision 2026-08-01.
- **The `fodbar.fi` "content was present despite the origin status" field.**
  Conditional on message 10 describing it first; message 10 has not gone out
  (`tmp/mas-repo-messages/` ends at 09), so per that condition the field is
  dropped rather than delaying the image. It is additive and can follow.
- **The unmarked interstitial.** The task file asked for it in this pass. It
  carries **no evidence** — no marker, no interstitial prose, no refusal notice
  — so the only rule that could catch it is "a page with little text is a
  block", which is inference, and this image exists partly to stop inference
  claiming `origin_blocked`. Inventing that rule here would re-create defect B
  aimed at every small real page in a 117,000-page corpus. Recorded in
  `test_an_unmarked_interstitial_is_stored_as_content`, not papered over.
  (The received diagnosis was also incomplete: the page misses `minimal_text`
  by one character — 50 visible, signal needs `< 50` — so it scores *zero*
  signals, not one, and no content-element adjustment would have caught it.)

---

## Collapse guard + one wire status per failure class (2026-08-01)

Part 1 of `tasks/cleaned-html-collapse-guard.md`. **Landed, not deployed** — it
ships in one image with `detector-round3-evidence-vs-inference.md`.

New: `deploy/docker/aitosoft_collapse_guard.py`,
`test-aitosoft/test_collapse_guard.py` (22 offline tests).
Modified: `aitosoft_failure_class.py`, `api.py`, `server.py`,
`test-aitosoft/fixture_origin.py`, `test-aitosoft/test_fixture_origin.py`.

### The guard

Twice a markup shape has reduced a whole page to nothing while every signal we
report stayed green — the `<noscript>` case ran **3.5 months across 406 pages and
70 hosts** at HTTP 200 / `success: true` / one character of markdown, and we
learned about it only because MAS eventually noticed. The causes are unbounded
(every WordPress plugin can mint another), so the guard detects the
**consequence**.

**It is not the `html` → `cleaned_html` ratio the task file proposed**, and both
reasons are measurements:

- That ratio fires on healthy pages. `len(html)` is dominated by inline CSS/JS,
  which cleaning strips by design. The fixture's *healthy* control padded to
  73 KB gives 261 bytes of `cleaned_html` — ratio 0.0036, **byte-identical to the
  collapsed page's**. Real captures agree: `accountor.com`'s cookie wall is
  99,649 → 230 → 125 and is not a defect.
- It is blind to a whole mechanism. `/collapse/unterminated-comment` returns
  **74,523 bytes of `cleaned_html` containing the contact details** and still
  produces zero markdown.

So the guard compares **visible text characters in the rendered HTML** against
**markdown characters out** — text on both sides, the same unit MAS's
`DEGENERATE_CAPTURE_CHARS = 500` is written in. The unit hazard that runs through
this whole area (HTML *bytes* vs markdown *characters*) is handled by never
crossing it. Whitespace is normalised first: `monidor.com`'s interstitial
measures 506 raw "visible" characters and 58 collapsed, and counting raw would
have fired on a challenge screen.

Thresholds measured against **37 distinct real captures** stored under
`test-aitosoft/artifacts/` — zero live requests:

| population | n | visible chars | markdown/visible |
|---|---:|---:|---:|
| healthy content pages | 31 | 739–34,172 | **1.311–2.400** |
| cookie-wall / JS shells | 5 | 0 | *nothing to lose* |
| challenge interstitial | 1 | 58 | 1.000 |
| collapsed (fixture, 4 shapes) | 4 | 1,135–1,138 | **0.000** |

`MIN_VISIBLE_TEXT_CHARS = 500`, `MAX_MARKDOWN_CHARS = 500` (MAS's own floor — the
guard can only fire on captures they already discard), and
`MAX_MARKDOWN_TO_VISIBLE_RATIO = 0.10`, which is 13× below the lowest healthy
page ever measured. `test_thresholds_clear_every_real_capture` re-derives the
corpus on every run so the constants cannot drift from the evidence. The markdown
test runs first and screens out every healthy page, so the 9 ms visible-text pass
never runs on the path that matters.

A detected collapse is **HTTP 200 + result-level `success: false` +
`failure_class: render_defect`**, content still attached.

### The root cause is NOT solved, and the file said it probably was

That was an inference from one fixture. Enumerated through the browser at
`?bytes=73000`, twice each: **four shapes lose the body, by three mechanisms**,
all deterministic. `unclosed-noscript` and `unclosed-script` (Chromium
re-serializes the document inside the unclosed raw-text element), `deep-nesting`
(libxml2's depth limit — **harmless at 1.5 KB, fatal at 73 KB**, so an unpadded
enumeration would have missed it), and `unterminated-comment` (loss is in
markdown generation, `cleaned_html` intact). `apteam.fi`'s fingerprint is
consistent with at least two of them, so which one it is remains unknown.
Recorded in `fixture_origin.BODY_SWALLOWING_SHAPES`.

`unclosed-script` is a **known blind spot**: it puts the document inside a
`<script>`, and the guard's visible-text measure strips script blocks (it must —
real pages carry hundreds of KB of inline JS). Pinned by
`test_a_body_swallowed_into_a_script_is_still_silent` rather than forgotten.

### One class, one wire status

MAS found that `render_error` was served at two statuses: static mode returned it
inside an unconditional 200 while full mode mapped it to 500, decided by
`render_mode` and documented nowhere. `server.py` now routes **both** modes
through one `_crawl_response`, so `http_status_for` is the single mapping site.
Static mode's actual contract is unchanged — network failures still never raise,
because they classify as origin classes and origin classes map to 200.

The taxonomy was missing **permanence, not ownership**: `render_defect` is
entirely our fault and still must not be retried. Hence `NON_RETRYABLE_CLASSES`
alongside `ORIGIN_CLASSES`.

**A defect this fix would otherwise have shipped:** static mode attaches
`bad_request` to a *result* when the egress broker refuses a redirect hop, and
that call site's own comment says "MAS must never retry it". Routing it through
`http_status_for` turns it into a **500, retried 3×** — its old unconditional 200
had been making the comment true by accident. `bad_request` is now in
`NON_RETRYABLE_CLASSES`, pinned by `test_an_ssrf_refusal_is_not_retryable`. Found
by reading every class static mode can emit, not by the 151 tests that passed.

### Instrument fix (test-only, and load-bearing)

`fixture_origin.CONTENT_HTML` — the healthy control every route serves as its
success case — rendered to ~140 markdown characters, *below* MAS's
`DEGENERATE_CAPTURE_CHARS = 500`. A capture that succeeds completely while
tripping the customer's own floor is not a control, and this task's whole output
is a threshold. Grown to **1,227 markdown characters over 1,135 of visible
text**; pinned by `test_the_healthy_control_is_not_degenerate`.

### Tests

192 total, zero live requests: 152 offline (`pytest test-aitosoft/`
minus the browser suite) + 40 browser-driven `test_fixture_origin.py`.
`test_an_unclosed_noscript_still_swallows_the_body` **inverted** into
`test_a_swallowed_body_is_reported_as_a_defect`. Tier 1 regression is **not** run
— it needs a live server and four live requests, and belongs to the shared
image's deploy, not to this landing.

---

## Local fixture origin (2026-07-31)

Closes `tasks/done/fixture-origin.md`. **Test-only — no production file
touched.** New: `test-aitosoft/fixture_origin.py`,
`test-aitosoft/test_fixture_origin.py`, `test-aitosoft/conftest.py`.

Every failure class diagnosed since 2026-04 was diagnosed against a customer's
website — 8 hits on `maitokolmio.fi`, 4 on `kiertopakkaus.fi`, 3 on
`konecranes.com`, `talgraf.fi` permanently Cloudflare-blocked by our own
over-scraping. All of it egresses from one Azure SNAT address that is not
contractually ours (`vnetConfiguration: null`) and that MAS's production fetches
share, so "this host blocks datacentre IPs" and "this host blocked us because of
what we did" were not distinguishable. That is an epistemics problem, not a
politeness one.

The 130 pure-function tests cover `strip_noscript`, `is_blocked` and
`classify_result` fed synthetic strings. Nothing covered **time, navigation or
the browser** — which is exactly the set of classes that kept costing live
traffic. `fixture_origin.py` is a threaded `HTTPServer` (upstream's own idiom,
`tests/async/test_redirect_url_resolution.py`) with a route per failure class,
driven through `aitosoft_entry` → `api.handle_crawl_request` → a real pool
browser, so `failure_class`, `render_mode`, the final-hop `status_code` rewrite,
the patchright retry and the wall-clock fence are genuinely exercised. Delay,
body size, visible-text length, status code and markup shape are arguments;
`?stall=` and `?status=` work on every route. A new failure class is a new
parameter, not a new website.

`egress_broker` is **not** weakened. `loopback_allowed()` flips the two flags
`CRAWL4AI_ALLOW_INTERNAL_URLS` sets, scoped to a `with` block around each crawl
rather than set as an environment variable, and the same suite asserts that the
production configuration still refuses the fixture's own URL — including the
opaque `reason`. Setting the env var instead would silently disarm
test_static_mode.py's per-hop SSRF assertions in the same pytest process.

Three tests pin defects **on purpose**, so the tasks that fix them have a red
test to turn green (invert, don't delete):

| Pinned | Owner |
|---|---|
| ~80 KB padded block page at HTTP 202 → `success:true`, `failure_class:none` — every size gate is on `len(html)` (10 KB tier 2, 50 KB tier 3) | `detector-round3-evidence-vs-inference.md` |
| Interstitial with no vendor marker and no "Just a moment" title → stored as content; 53 chars of prose clears every tier | same |
| **Unclosed `<noscript>` still swallows the whole body — found by this fixture** | `cleaned-html-collapse-guard.md` |

That last one is the fixture paying for itself on day one. `strip_noscript()`
fixed the *nested* shape, and test_noscript_body_collapse.py reports the
unclosed shape fixed too — but it feeds the raw string to libxml2, which
auto-closes the element. Chromium does the opposite: an unclosed `<noscript>`
puts the parser into raw-text mode, so the rest of the document (`</body></html>`
included) is serialized *inside* the element, and `strip_noscript()` then
correctly removes the element and takes the page with it. `cleaned_html` =
`<html><head><title>…</title></head></html>`, markdown = one newline, at HTTP
200 `success: true`. Byte for byte the silent whole-body loss that ran 3½
months, surviving its own fix through a parser difference that only a browser in
the loop can show.

Also here: `test-aitosoft/conftest.py` stops pytest collecting the four live CLI
scripts (`test_regression.py`, `test_site.py`, `test_fingerprint.py`,
`test_soak.py`). Three of their helpers are named `test_*`, so `pytest
test-aitosoft/` reported three errors on every clean run — a permanently red bar
trains you to ignore the bar. They are unchanged as command-line tools.

Local-run note: config.yml pins `chrome_channel: chrome` for the deployed amd64
image; no such build exists for the arm64 devcontainer, so `_resolve_channel()`
falls back to bundled Chromium when no Chrome binary is on PATH. That replaces
the old advice to hand-edit config.yml (TESTING.md), which has been committed by
accident before. Override with `CRAWL4AI_FIXTURE_CHANNEL`.

---

## Failure classification + noscript body loss + challenge detection (2026-07-30, round 2)

Closes `tasks/done/origin-vs-crawler-failure-classification.md`,
`tasks/done/noscript-collapses-body-to-empty-markdown.md`,
`tasks/done/antibot-detector-challenge-blindspot.md`. Evidence base:
`tasks/waa-eval-2026-07-30-forensics.md` §2a, §3, §8b, §8c and MAS's answers in §7.

Ships together with the two fixes from round 1 (below), which were held for this.

### 1. `failure_class` — origin failures stop being our 5xx (the deploy gate)

**New file:** `deploy/docker/aitosoft_failure_class.py`. The vocabulary, all
error-text matching and the transport mapping live there and nowhere else — no
call site matches on `net::ERR_*` or the ACS-GOTO wrapper text itself.

The problem was a composition, not a single line:

```python
# server.py — upstream's all-failed rule
if all(not result["success"] for result in results["results"]):
    raise HTTPException(500, ...)
# server.py — our security handler, added 2026-04-14
if exc.status_code == 500:
    return JSONResponse({"error": "Internal server error", "correlation_id": cid}, 500)
```

Under the single-URL contract these compose into: **every full-mode failure,
whatever its cause, reached MAS as an opaque HTTP 500** with `status_code`,
`redirected_status_code`, `error_message` and `crawl_stats` all discarded. MAS
retries 500 three times, so a permanently blocked or broken origin cost four
browser renders to learn nothing. This is why the redirect fix in round 1 could
not ship alone: it *moves hosts into that population*.

MAS answered Q2 with option (a) unreservedly. Implemented as specified:

| Reality | Now |
|---|---|
| origin 4xx/5xx, edge block, DNS/TCP/TLS failure | HTTP **200**, result `success:false`, `failure_class` = `origin_http_error` / `origin_blocked` / `origin_unreachable` |
| our render broke | HTTP 500, envelope `failure_class: render_error` |
| our fence fired | HTTP 504, envelope `failure_class: render_timeout` |
| replica at capacity | HTTP 429 + Retry-After, envelope `failure_class: capacity` (unchanged) |

`failure_class` is on **every** result including successes (as `"none"`), so a
missing field means an old build rather than a success — MAS's requirement.
Envelope level only where no result exists to carry it (`capacity`, `auth`,
`bad_request`, plus our two 5xx classes), which is their division of labour, not
duplication.

Two channels needed fixing, not one. Besides `server.py`'s all-failed branch,
`api.py`'s `except Exception` is where `anitamakela.com`'s zero-byte Apache 500
landed: upstream re-raises a navigation failure when there is a single proxy and
`max_retries <= 1`, so the origin's own error never became a result at all. That
path now classifies the exception and returns the same envelope shape a failed
result would have.

**`status_code` in the API response is now the origin's FINAL status** (last
redirect hop). Note this reverses the round-1 decision below, deliberately and
at a different layer: `CrawlResult.status_code` keeps upstream's first-hop
semantics and `tests/test_pr_1435_redirected_status_code.py` still passes — the
rewrite happens in `api.py` when the result is serialised. Reasons: MAS asked
for exactly this in their Q2 answer; static mode has *always* reported the final
hop under that name, so the two render modes disagreed on a shared field; and a
redirect-to-block host was labelled `301`. `redirected_status_code` is untouched
and is now documented, as MAS requested — it was absent from their
`CrawlResult` interface entirely.

> **`status_code` may be 202, and 202 is not a success signal.** Added
> 2026-08-01. In MAS's 243-host re-scrape, **36 of 243** responses carried
> origin status 202, 100 % of them from the challenge families — and the *same*
> 202 served interstitials, block pages, real content and empty bodies. It is an
> anti-bot layer's code, not a page status.
>
> Neither side may branch on `status == 200` meaning success, or on
> `status_code >= 400` meaning failure. The fields that carry the outcome are
> the result-level `success` and `failure_class`; `status_code` reports what the
> origin said and nothing more. Two consequences we have already paid for: the
> detector's status branches (403/503, `>= 400`) can never fire on this family,
> which is why the block-notice and challenge tiers are status-independent; and
> a block page served at 202 looked exactly like a healthy page until 2026-08-01.
> See `tasks/challenge-interstitial-resolve.md` for what we think the layer is.

**Classification bias is deliberate:** anything unrecognised is `render_error`
(ours, 500, retryable), never an origin class, and an unknown `net::ERR_*` logs
a breadcrumb so the table grows from evidence. Wrong in that direction costs
wasted renders and is loud; wrong the other way tells MAS a healthy company site
is permanently broken, silently.

**Also fixed here (side finding):** `api.py` recorded
`track_request_end(success=True, status_code=200)` unconditionally once results
were processed — including for the all-failed case that became a 500. The
monitor read green while the client got an error, which would have hidden the
entire new failure population exactly when it needs watching. It now records the
outcome the client will actually see, using the same mapping `server.py` uses.

Static mode carries `failure_class` too, so both render modes parse identically.

### 2. Nested `<noscript>` discarded the entire page body

`crawl4ai/content_scraping_strategy.py` — new `strip_noscript()`, called at the
top of `_scrap()` immediately before `lhtml.document_fromstring()`.

`<noscript>` may not nest: with scripting enabled its content is raw text, so a
parser never sees an inner `<noscript>` as an element and the **outer** one is
left unclosed — everything after it is swallowed. A WordPress lazy-load plugin
wrapping the GTM block in a second `<noscript>` therefore cost the whole page:
`https://www.kiertopakkaus.fi/` produced 312,628 B of rendered HTML → **97 B**
of `cleaned_html` → **1 B** of markdown, at HTTP 200 with `success: true`.
**406 pages across 70 hosts** in MAS's corpus, reproducing identically 3½ months
apart. Static mode was never affected — `_strip_hidden_decoys` already
decomposes `noscript`, which is why the two modes disagreed by four orders of
magnitude on the same URL.

Removal rather than unwrapping, because we render with JavaScript enabled: by
definition `<noscript>` content is not what the page showed, and its scripted
equivalent is already in the DOM. Two passes — well-formed elements, then any
unpaired tag — so a truncated `<noscript>` cannot swallow a body either. Pages
without the substring return unchanged and unparsed.

### 3. `antibot_detector` — the challenge family, and a false positive

MAS scanned all 117,323 stored pages with our pattern list: **22 hits, 2
genuine**. The dominant signature (371 pages) was not in the list at all; ~15 of
the hits were healthy Shopify storefronts condemned by their own
`/pages/access-denied` navigation link.

- **Tier 1 +2 patterns:** `robot-suspicion`, `d1rozh26tys225.cloudfront.net`.
  Tier 1 because a hyphenated asset filename is not prose. No vendor guessed —
  the literals MAS measured are matched as literals.
- **New challenge tier.** Found while wiring the above: the tier-2 list is only
  ever evaluated on 4xx/5xx, and challenge interstitials are served with **HTTP
  200** — so `Checking your browser` had never once been consulted for the pages
  it was written for. That, not `_TIER2_MAX_SIZE`, silenced MAS's 29-page family.
  `_CHALLENGE_PATTERNS` is checked at any status, with two gates: HTML under
  10 KB *and* visible text under 1500 chars. The second gate exists because the
  test suite caught the first one failing — a 40-paragraph Finnish article about
  bot protection, quoting every phrase in the list, is 8.2 KB and passes the size
  gate.
- **`Access Denied` tightened** to `<title>`/`<h1..h3>` context. Keeps the
  genuine Akamai page; drops link text. Real 403s lose nothing — the 403/503
  branch already flags any non-data HTML body without this pattern.

Built against fixtures, not live hosts — verification against a live challenged
host is impossible by construction and MAS confirmed why: from a Finnish
consumer IP the same hosts return 200 with full content, so the challenge is
keyed on our Azure egress at capture time. MAS's reply-4 (arrived
mid-implementation) supplied one verbatim stored sample of the 371-family, which
the fixtures are now reconstructed from, and **corrected our size-gate
hypothesis**: the 29 `Checking your browser` pages are 61 B and 99 B, far under
the gate. Their correction points at exactly the defect found here — the pattern
existed, the page was tiny, and it still was not caught, because tier 2 is only
reachable on 4xx/5xx. Confirmed against the pre-fix detector (commit `2a9daa1`):
both families return `(False, "")` at HTTP 200, and both are detected after.

### Tests

Offline gate **130/130** (was 64). New: `test_failure_classification.py` (34),
`test_noscript_body_collapse.py` (11), `test_antibot_challenge_detection.py`
(15). `test_mas_contract.py` gained two tests that drive the **real app**
through `TestClient`, security exception handler included.

**Live pre-deploy verification** (local server, threaded fixture origin on
127.0.0.1:8099, `CRAWL4AI_ALLOW_INTERNAL_URLS=true`):

| Fixture | HTTP | `status_code` | `failure_class` |
|---|---|---|---|
| healthy page | 200 | 200 | `none` |
| 500 + zero body (anitamakela shape) | **200** (was opaque 500) | **500** | `origin_http_error` |
| direct 403 block page | **200** (was opaque 500) | 403 | `origin_blocked` |
| 301 → 403 block (konecranes shape) | **200** | **403** (was `301`) | `origin_blocked` |

That last row is the redirect fix and the final-hop rewrite working together —
the case this whole deploy exists for.

The 500-with-empty-body run is why `classify_error_text` special-cases 5xx: the
block detector judges the *body*, and an empty 5xx body trips its structural
check, so a site that is simply broken came back labelled `origin_blocked`. Both
verdicts are origin-caused and both map to HTTP 200, but only `origin_blocked`
is what a residential-egress retry would target. 503 stays a block — Incapsula
and Varnish really do serve blocks with it.

Tier 1 regression **4/4** (`--version waa-round2-local`). Caveat: run against
bundled Chromium, not real Chrome — this dev container is ARM64 and
`playwright install chrome` is unsupported there, so `chrome_channel` was
switched to `chromium` for the run and reverted immediately after
(`git checkout deploy/docker/config.yml`, verified). Tier 1 exercises markdown,
consent-popup removal and contact extraction, none of which depend on the
channel; the stealth first tier is the part not covered locally.

### Open with MAS

- Envelope `success` stays `true` when the single result failed, matching static
  mode. Our own monitor already treats an all-failed batch as a failure, so the
  envelope is the last place still reading green. Not flipped unilaterally:
  static mode is the shape they are adopting *right now* as a pre-delete gate.
  Asked whether they want it to become the aggregate.
- Re-scrape the 70 `empty_*` hosts and report the recovery rate, so the noscript
  fix is measured rather than trusted.
- Still waiting on one full stored challenge HTML (§8e) to identify the vendor.

---

## Block detection behind redirects + bounded render calls (2026-07-30)

Closes `tasks/redirect-status-blinds-block-detection.md` and
`tasks/render-retry-unbounded-hang.md`. Evidence base:
`tasks/waa-eval-2026-07-30-forensics.md` §1 and §2b.
Both are upstream defects; both filed as PRs (see "Upstream PRs" below).

### 1. Block detection judged the wrong hop of a redirect chain

`AsyncCrawlResponse.status_code` deliberately carries the **first** hop of a
redirect chain (upstream design, issue #660 → PR #1435), while the HTML always
comes from the **last** hop, kept separately as `redirected_status_code`.
`async_webcrawler.py` fed the *first* hop to `antibot_detector.is_blocked()` at
all three call sites, so a 301 was judged instead of the 403 it led to — and no
status rule in `is_blocked` can fire on a 3xx.

Effect: **every site that redirects (apex→www, http→https) and then serves a
4xx/5xx block page was returned as `success: true` with the block page as its
content.** Finnish company sites redirect almost universally, so this silently
poisoned the corpus at scale. Live proof (prod, 2026-07-30): `konecranes.com`
returned `success:true, status_code:301, redirected_status_code:403` with
"Error 403 Forbidden … Varnish cache server" as its markdown.

Fix: `antibot_detector.effective_status(status_code, redirected_status_code)`
— one helper, used at the three `is_blocked` call sites. `status_code` itself is
untouched: it is upstream semantics, `tests/test_pr_1435_redirected_status_code.py`
pins it, and MAS may branch on it.

Why the consumer and not the producer: the HTTP (non-browser) strategy already
sets `status_code` to the post-redirect final status, so the same URL used to
yield *different* block verdicts depending on which crawler strategy ran. The
fix makes them agree.

**Blast radius, measured end-to-end against a local fixture origin:**

| Case | Before | After |
|---|---|---|
| 301 → 200 benign | HTTP 200, success | HTTP 200, success (3.7 s) — no false positive |
| 301 → 403 block | HTTP 200, `success:true`, block page as content | **HTTP 500** (13.5 s) |
| direct 403 block | HTTP 500 | HTTP 500 (12.7 s) — unchanged |

The change is **strictly additive**: redirect hops are 3xx by construction, and
no status rule in `is_blocked` matches a 3xx, so it can only add blocked
verdicts, never remove one. A no-redirect request has
`status_code == redirected_status_code`, so it is a literal no-op there.

⚠ **The HTTP mapping is the important part, and it is NOT what the task file
assumed.** `server.py:940` raises `HTTPException(500)` when every result is
unsuccessful, and our security handler (`server.py:517-528`) then genericizes
any 500 to `{"error": "Internal server error", "correlation_id": …}`. So a
redirect-to-block host moves from a wrong-but-parseable 200 to an **opaque 500
with `redirected_status_code` stripped** — the exact field the forensics record
told MAS to key on client-side. Consequences, all verified in code and live:

- MAS retries 500s (3×, 1/2/4 s), so per-company cost rises further on top of
  the extra first-tier attempt and the now-armed patchright tier.
- Under the single-URL contract, **every** full-mode failure is already an
  opaque 500 today — this change enlarges that population, it does not create
  it. `www.konecranes.com` (no redirect) has always landed there.
- **This is also the true mechanism behind the "konecranes HTTP 500" MAS
  reported**, not (only) the ACS-GOTO laundering described in forensics §3:
  block detected → `success:false` → `all(not success)` → 500 → genericized.

The HTTP mapping is Q2 to MAS (`tasks/origin-vs-crawler-failure-classification.md`)
and is deliberately **not** changed here — it is an outward-facing contract with
an answer pending. Recorded in that task file as new evidence.

### 2. Render calls that no timeout covered

Root cause, isolated by reproduction rather than inference (local fixture
server + async await-chain dump; the exact blocking frame was
`async_crawler_strategy.py` `adapter.evaluate(update_image_dimensions_js)`):

**Playwright's `page.content()` and `page.evaluate()` are sent to the driver
with no `timeout` field, so the driver arms no timer at all.** They wait on the
frame's execution-context promise, and every navigation *replaces* that promise
with a fresh unresolved one. A page that keeps committing navigations therefore
wedges them forever. `page_timeout` reaches only `page.goto` and the `wait_*`
family, which is why the forensics matrix saw 80 s → 30 s change nothing. Both
call sites sit inside swallow-all `try/except`, so nothing was logged either —
matching the 172 s of total silence before the fence fired.
`page.close()` is unbounded for the same reason, which matters during cleanup.

Three bounds, outermost last:

| Bound | Where | Value |
|---|---|---|
| `bounded_evaluate` | `browser_adapter.py`, all three adapters | 30 s default, per-call override |
| optional DOM steps | image dimensions, consent + overlay removal | 10 s (they already degrade gracefully) |
| `_capture_html` | `page.content()` with settle-and-retry | 15 s/attempt, 25 s total, 3 attempts |
| `page.close()` | `_crawl_web` finally block | 10 s |
| `total_timeout` | new `CrawlerRunConfig` field, shared by every attempt in `arun()` | `config.yml` → 100 s |

`_capture_html` is the one that turns failures into successes: on the
"page is navigating and changing the content" error it waits for the next
document to reach `domcontentloaded` and captures again, which is the documented
remedy — static mode had already proved the content was right there. It bails
out early if the page cannot even reach `domcontentloaded`, so a genuinely stuck
page pays one bounded cost instead of one per attempt.

`total_timeout` is server-side only: it is absent from
`UNTRUSTED_FIELD_ALLOWLIST`, so a client-sent value is dropped, and it is
injected by api.py's existing `crawler.base_config` pass. Sized at ~fence/2:
the patchright tier runs a second `arun()` inside the same 180 s fence, and it
must stay above the largest `page_timeout` a client may send (MAS V14 sends
80 s) so one slow navigation still fits in a single attempt.

**Measured, same fixture origin, MAS V14-shaped request:**

| Case | Before | After |
|---|---|---|
| navigation race (the `maitokolmio.fi` shape) | 504 @ 180 s, no diagnostic | **HTTP 200, full content, 5.0 s** |
| permanently wedged page | 504 @ 180 s, no diagnostic | HTTP 500 @ 94 s, exact reason in the log |
| `arun()` with a 0.4 s budget, 4 attempts | unbounded | ≤ 2 attempts, bounded |

Residual (stated, not fixed here): a host that is *both* slow and blocked can
still reach the fence, because the patchright tier gets its own `total_timeout`.
`tasks/blocked-host-retry-economy.md` removes that by not running patchright for
reputation blocks.

### Files touched

| File | Change |
|---|---|
| `crawl4ai/antibot_detector.py` | +`effective_status()` helper |
| `crawl4ai/async_webcrawler.py` | 3 × `is_blocked` call sites use the final hop; `total_timeout` deadline shared across attempts |
| `crawl4ai/browser_adapter.py` | `bounded_evaluate()` + `timeout` kwarg on all three adapters |
| `crawl4ai/async_crawler_strategy.py` | `_capture_html()` settle-and-retry; bounds on optional DOM steps, `page.close()`, virtual scroll; capture constants |
| `crawl4ai/async_configs.py` | `CrawlerRunConfig.total_timeout` (default None) |
| `deploy/docker/config.yml` | `crawler.base_config.total_timeout: 100000` |
| `test-aitosoft/test_redirect_block_detection.py` | new, 11 tests |
| `test-aitosoft/test_render_bounds.py` | new, 17 tests |

Both new suites were verified to **fail without the fix** (3 of 11 redirect
tests fail on the unpatched tree; the 8 others are regression guards that must
pass both ways).

### Pre-deploy verification (2026-07-30, local server)

- Offline gate: **64/64** across seven suites.
- Upstream `tests/proxy/test_antibot_detector.py`: 47/47; PR #1435 model tests 4/4.
- **Tier 1 regression 4/4** against a local server, `--version
  2026-07-30-redirect-bounds-local`: caverna.fi 302 tok, accountor.com 8516 tok
  (1/1 contacts — the Cookiebot wall still clears inside the new 10 s bound on
  consent-popup removal), solwers.com 13173 tok (1/1), jpond.fi 1685 tok (1/1).
  `jpond.fi` is itself a 301 → 200 redirect and stayed a success — the
  false-positive tripwire, live.
- **Zero** bound-firing log lines across the whole Tier 1 run: the new ceilings
  are invisible on healthy pages, which is the intended shape.
- Local server ran on bundled Chromium, not real Chrome — this dev container is
  arm64 and `playwright install chrome` is unsupported there. Stealth
  fingerprint therefore differs from prod; everything else is the deployed path.

### Side findings (recorded, not fixed)

- `config.yml`'s `crawler.base_config.simulate_user: true` **never takes
  effect**: api.py applies base_config only when the current value
  `is None or == ""`, and `CrawlerRunConfig.simulate_user` defaults to `False`,
  which is neither. Latent since the base_config mechanism was adopted.
- `_crawl_web`'s cleanup skips `page.close()` when the browser has ≤1 page and
  is headless, so the first page of each pool browser is never closed. Benign at
  steady state (one leaked tab per browser) but it means a wedged tab is never
  disposed, and disposing it is what aborts the orphaned driver operation.
- `api.py`'s full-mode branch calls `track_request_end(success=True, status_code=200)`
  unconditionally, so monitor metrics record a success even when the client
  receives a 500. This will hide the new failure population.

---

## Fence-504 Observability (2026-07-17)

Closed `tasks/504-fence-observability.md`. Image: `0.9.2-fence-obs`.
Logging only — zero behavior change, nothing contract-visible to MAS.
Motivation: the 2026-07-17 WAA eval had 3 requests burn the full 180s fence
and 504 with ZERO server-side log lines (located only via queue-wait timing
coincidences). Every future 504 is now attributable.

### The two new log lines (grep for these verbatim)

1. **Fence fire** — `api.py`, the `except asyncio.TimeoutError` branch
   (WARNING, logger `api`):

   `WALL-CLOCK FENCE 504: url=%s deadline_s=%s elapsed_s=%.1f gate=%s`

   e.g. `WALL-CLOCK FENCE 504: url=https://example.com deadline_s=2.0
   elapsed_s=2.8 gate={'capacity': 2, 'in_use': 1, 'queued': 0, 'max_queue':
   4, 'max_wait_s': 15.0}` — the snapshot still counts the fenced request
   itself (logged before the `finally` releases the slot). `_deadline` is
   initialized to `None` at handler top so the except-branch can't NameError
   if a TimeoutError ever arrives before the fence is armed.

2. **Admission grant** — `aitosoft_admission.py` (INFO, logger
   `aitosoft_admission`), one line per grant, immediate or queued:

   `RenderGate ADMIT url=%s waited=%.1fs in_use=%d/%d queued=%d`

   `RenderGate.acquire()` gained an optional `label` keyword (backward
   compatible; `url=-` when absent); `api.py` passes `urls[0]`. This
   REPLACES the old `RenderGate admitted after %.1fs queue wait` line
   (which only fired for queued admits and never carried the URL). The
   `RenderGate REJECT` warnings are byte-identical (playbook greps them).
   Pinned by 2 new tests in `test-aitosoft/test_admission.py` (8 → 10).

### Item 3 (silent nav-retries): investigated, NO patch — premise was wrong

The task assumed upstream's retry loop (`async_webcrawler.py` `arun`,
`_max_attempts = 1 + max_retries`) swallows page timeouts invisibly in
server context. Code reading shows it already logs every retry attempt
(`Anti-bot retry {n}/{max} for {url}` WARNING, line ~425) and every
exception (`error_status` "Proxy direct failed: …", line ~534 — a goto
timeout surfaces as `RuntimeError("Failed on navigating ACS-GOTO…")`).
These go through crawl4ai's `AsyncLogger`, console-gated ONLY on per-request
`config.verbose` (`arun` sets `self.logger.verbose = config.verbose`),
which defaults to True and MAS never overrides. Proof it reaches stdout in
prod: the eval's `[FETCH]`/`[COMPLETE]` pairs come from this same logger.

**Forensic consequence:** the eval's three zero-log wedges CANNOT have been
the "80s×2 silent retry arithmetic" — a goto-timeout retry would have
logged `[ANTIBOT]` lines. Zero lines between browser acquisition and fence
means `crawler_strategy.crawl` neither returned nor raised for 180s → a
single indefinite hang. Candidate unbounded awaits (noted, not chased):
context/page creation CDP roundtrips on a busy Chromium during ramp churn,
the redirect-chain walk (`await prev_req.response()`, no timeout), hooks.
Next occurrence will be greppable via the fence line; escalation path in
the done-file.

---

## Pool Cleanup + Patchright Tidy (2026-07-17)

Closed `tasks/crawler-pool-cleanup.md` and `tasks/patchright-fallback-tidy.md`.
Image: `0.9.2-pool-cleanup`.

### crawler_pool.py de-noise (zero behavior change)

Rebuilt the file from exact upstream bytes + only the real changes. Diff vs
`upstream/develop` shrank **+258/−49 → +210/−36** (net of the re-init feature
below); every remaining hunk is nameable: MAX_PAGES enforcement, overflow
keys, BUSY_SINCE stuck-slot janitor, PERMANENT lazy re-init. Also removed the
dead overflow scan over HOT_POOL (`_ovf_` keys are only created in COLD_POOL
and promotion only moves plain-sig keys — the branch could never match).

### crawler_pool.py: PERMANENT lazy re-init (behavior fix)

After `_force_close_stuck` closed the permanent browser it set
`PERMANENT = None` and nothing re-created it — one stuck slot degraded ALL
default-config traffic to overflow cold browsers until container restart.
Now `get_crawler` lazily rebuilds it on the next default-sig request
(assigns only after `start()` succeeds; can't fire before `init_permanent`
because `DEFAULT_CONFIG_SIG` is unset until then). Ride-along: `OVERFLOW_SEQ`
reset in `close_all` (parked secondary finding, trivial). NOT taken:
BUSY_SINCE id()-rekeying (stays parked — see tasks/done archive).
Pinned by `test-aitosoft/test_crawler_pool.py` (4 tests, mocked browsers).

### aitosoft_patchright_fallback.py tidy

1. Explicit `_UNDETECTED_IN_FLIGHT` counter replaces `_UNDETECTED_SEM._value`
   peeking (private asyncio internals) in the recycle gate.
2. **Recycle race closed**: singleton now dereferenced INSIDE the semaphore
   with the counter already raised; `_recycle_undetected` only swaps at
   in_flight == 0. Previously a recycle between the early deref and the
   semaphore acquire closed the crawler mid-flight (retry silently lost).
3. Frozen first persona documented as ACCEPTED (coordination decision
   2026-07-17): patchright's value is its own stealth fingerprint;
   per-company personas deliberately don't apply to the fallback path.
4. GLOBAL_SEM interplay comment at the arun call site: upstream's class-wide
   `capped_arun` means retries also consume GLOBAL_SEM permits — safe while
   render_capacity (2) < pool.max_pages (5).
Pinned by `test-aitosoft/test_patchright_fallback.py` (4 tests).

---

## Contract Addendum: Single-URL /crawl Requests, Server-Enforced (2026-07-17)

### The contract

**One URL per /crawl request.** `len(urls) > 1` → HTTP **400** with detail
`"multi-URL requests not supported: MAS contract is single-URL per request
(AITOSOFT_CHANGES.md, 2026-07-17)"`. Enforced in `api.py
handle_crawl_request` at the top of the request path — before seed
validation, before the static-mode branch, before render admission — so it
covers both full and static modes and the `/crawl/job` path (which reuses
`handle_crawl_request`). `/crawl/stream` is not guarded (MAS doesn't use it;
no second hunk in an upstream file for a path nobody calls).

### MAS ack (relayed via Tero, 2026-07-17)

> We commit to single-URL /crawl requests long-term — enforce it at the
> boundary (400 on multi-URL) and document it in the contract; no change
> needed on our side.

Their client (`src/lib/crawl4ai-client.ts`) always sends `urls: [url]` and
reads only `results[0]`; WAA agents are sequential ReAct loops; parallelism
is many agents × single-URL requests, governed by the render-admission
429/Retry-After contract.

### Why

Closes the last latent capacity-invariant gap: `RenderGate.acquire` clamps
weight to capacity, so a multi-URL request admitted at weight ≤2 could have
rendered at up to GLOBAL_SEM(5) concurrency, violating the 2-renders-per-
replica invariant. Now structurally unreachable. (Weight-coherence
implementation options preserved in tasks/render-gate-batch-coherence.md
git history, pre-rescope, if batching ever returns.)

### Tests

- `test_mas_contract.py::test_multi_url_request_rejected_with_400` — 2-URL
  request through `api.handle_crawl_request` → HTTPException 400, detail
  names the contract. Existing single-URL contract payloads unchanged.
- `aitosoft_admission.py` `acquire()` docstring updated: multi-URL rejected
  upstream of the gate; weight-clamp note retained for context.

## Static-Mode Hardening: SSRF Redirect Validation + Robustness Bundle (2026-07-17)

### Why

The 2026-07-17 repo audit found one real security gap: static mode's httpx
client used `follow_redirects=True` with no per-hop validation, while full
mode re-validates every redirect through the pinning egress proxy
(`egress_broker.check_redirect`). A crawled public page 302-ing to
`http://169.254.169.254/` (Azure IMDS) or an internal service would have
been fetched and returned to the caller. Six smaller robustness issues rode
along (tasks/done/static-mode-hardening-2026-07-17.md items 2–7).

### What

1. **`aitosoft_static_mode.py`** — client is now `follow_redirects=False`;
   `_fetch_static_one` follows redirects manually (≤5 hops), resolving each
   `Location` against the current URL and validating it with
   `egress_broker.check_redirect` (same rule as full mode). Refused redirect
   → inner `success:false`, opaque `error_message: "static-fetch: redirect
   blocked (SSRF protection)"`, HTTP 200 envelope (one bad URL never fails
   the batch). Also: per-batch fan-out bounded by `asyncio.Semaphore(10)`;
   `HTML2Text`/egress imports at module scope (fail once, not per-request
   through gather); dead `config` param dropped; `verify=False` comment
   rewritten (matches full mode, where upstream hardcodes
   `--ignore-certificate-errors` — deliberate for broken-cert SME sites).
2. **`api.py` (static branch finally, ~6 lines)** — monitor now records the
   real aggregate outcome: 200 only if ≥1 URL succeeded, else 502 + error
   note (was: unconditional 200, skewing dashboards — 2026-04-15 review C1).
3. **`config.yml`** — `crawler.static_fetch_timeout_s: 15` (was a hardcoded
   module constant), read once per process like the admission knobs.

### Tests

- New OFFLINE suite `test-aitosoft/test_static_mode.py` (10 tests,
  httpx.MockTransport + IP-literal hosts — zero network/DNS): public→private
  and IMDS redirects refused AND never fetched, public→public + relative
  Location followed, >5 hops refused, semaphore bound observed (peak ≤10
  over a 30-URL batch), all-fail → monitor 502 / partial success → 200,
  client pinned `follow_redirects=False`, timeout knob wired to config.yml.
- Offline gates 25/25 (mas_contract 7 + admission 8 + static_mode 10).

### Deploy + live verification (2026-07-17)

- Image `0.9.2-static-hardening` (digest `sha256:f9f6c7b7...`, revision
  `crawl4ai-service--0000027`) via deploy-image.sh — env vars untouched,
  render-capacity invariant OK (config 2 == ACA rule 2).
- Post-deploy: /health OK; static spot check caverna.fi 200/899 chars;
  Tier 1 regression 4/4 (`--version static-hardening`); live SSRF probe
  `https://nghttp2.org/httpbin/redirect-to?url=http://10.0.0.1/` in static
  mode → inner `success:false`, `error_message: "static-fetch: redirect
  blocked (SSRF protection)"`, envelope 200 — exactly the offline-test
  contract. (httpbin.org itself was 503-ing and httpbingo.org 403s
  datacenter IPs; the nghttp2.org mirror issues a real 302.)

---

## Render Admission Control + Capacity-Matched Scaling (2026-07-17)

### Why

2026-07-16 ~17:39–17:43 UTC incident: `kynnos.fi/yritys/` 504'd after exactly
180s under only 4–6 concurrent renders, while sibling pages rendered in 3–4s.
Forensics (Log Analytics): a single replica served the whole burst (ACA
`rules: null` = default 10-concurrent/replica scale rule, never triggered);
that replica launched 7 Chromium browsers in 10 min (per-persona configs +
overflow browsers after `5/5` capacity warnings) on 2 vCPU; a whole-replica
stall 17:39:24→17:42:28 starved the render until the wall-clock fence cut it.
Memory was NOT a factor (67% peak, no MemoryError). Historic mitigation was
pinning 3–5 warm replicas before batches — retired by this change.

### What

1. **`deploy/docker/aitosoft_admission.py` (new)** — `RenderGate`: hard cap of
   `render_capacity` (2) concurrent full renders per replica, bounded queue
   (4 waiters / 15s max wait), overflow → `RenderCapacityExceeded`. Weighted
   acquire (`min(len(urls), capacity)` slots), so it can't deadlock — but note
   the weight clamp means a multi-URL request can still render at dispatcher
   concurrency above its granted weight; latent while MAS sends single URLs
   (see `tasks/render-gate-batch-coherence.md`).
2. **`api.py` (~15 lines)** — `handle_crawl_request` acquires the gate after
   config validation, BEFORE browser get/launch and BEFORE
   `asyncio.wait_for(wall_clock_s)` — the 180s fence now starts at DEQUEUE,
   so queue wait can never eat the render budget. Rejection maps to
   **HTTP 429 + `Retry-After: 5`**. Static mode bypasses the gate entirely.
   Budget: 15s queue + browser get + 180s fence ≈ 200s < 240s ACA ingress.
3. **`config.yml`** — `crawler.pool.render_capacity: 2`, `admission_queue: 4`,
   `admission_max_wait_s: 15`.
4. **ACA config (az CLI, not in repo)** — explicit HTTP scale rule
   `concurrentRequests: 2` (replaces default 10), `maxReplicas: 30`,
   HTTP startup/readiness probes on `/health` (lifespan pre-warms the
   permanent browser, so serving /health == browser-ready).

### Capacity number (benchmarked 2026-07-17)

2-CPU-pinned Chromium render benchmark (synthetic SME page, fixed CPU work,
MAS V13-like config): N=2 costs +7% p50 vs N=1; N=3 +13%; N=4 +22%
(p95 +43%); N=6 +44% (p95 2×, 2.1 GB Chromium RSS). Prod degrades steeper
(multi-browser personas + launch storms), so capacity = 2.

### Tests

- `test-aitosoft/test_admission.py` — 8 offline tests (gate semantics + 429
  mapping in `handle_crawl_request`).
- E2E local: 10 concurrent renders → 6×200 (2 immediate, 4 queued ≤14s),
  4×429 in 0.5s with Retry-After; /health instant under load; static mode
  unaffected. Tier 1 regression 4/4
  (`reports/render-gate-local-regression-tier1.md`).

---

## Upstream v0.9.2 Upgrade (2026-07-16)

### What

Merged 117 upstream commits (v0.8.6 → v0.9.2, releases 0.8.7/0.8.8/0.8.9/0.9.0/0.9.1/0.9.2).
Branch `upgrade/v0.9.2`. The dominant upstream theme is a **secure-by-default
Docker server** (0.9.0): fail-closed auth, untrusted-config trust boundary,
SSRF egress pinning, declarative-only hooks, resource governance.

### Merge strategy (important for future syncs)

The 2026-04 "normalize whitespace" commit (`055d4ce`) had reformatted ~90
upstream files, creating an 11.5k-line phantom diff. This merge **took
upstream's tree wholesale** (`merge -s ours` + `checkout upstream/develop -- .`)
and re-applied only our real patches, so upstream files are now byte-identical
to upstream again. `.pre-commit-config.yaml` now scopes ALL hooks to
Aitosoft-owned files (top-level `files:` pattern) so drift cannot recur.
Future syncs: `git fetch upstream && git merge upstream/develop` should be
near-clean; our entire delta is listed below.

### Patches DROPPED (upstream superseded them)

| Old patch | Upstream replacement |
|-----------|---------------------|
| `crawl4ai/browser_adapter.py` playwright-stealth 2.x port | Fixed upstream (PR #1960, 0.8.7) — functionally identical |
| `deploy/docker/api.py` 180s `asyncio.wait_for` + 504 | Upstream `limits.wall_clock_s` mechanism (governor.py); we set `wall_clock_s: 180` in config.yml |
| `deploy/docker/simple_token_auth.py` + middleware in wrapper (DELETED) | Upstream `AuthGateMiddleware`: same `Authorization: Bearer $CRAWL4AI_API_TOKEN` contract, constant-time compare, fail-closed startup, covers all routes/mounts/WebSockets. `/health` stays public. |

### Patches RE-APPLIED (adapted to 0.9.2)

| File | Change |
|------|--------|
| `crawl4ai/browser_manager.py` | `_build_browser_args` GPU flags gated on `enable_stealth` (still hardcoded upstream; keeps WebGL alive in stealth mode — PR-worthy) |
| `deploy/docker/crawler_pool.py` | Unchanged upstream since 0.8.6 → our MAX_PAGES enforcement + BUSY_SINCE stuck-slot janitor re-applied verbatim |
| `deploy/docker/api.py` | render_mode param + static short-circuit (after SSRF validation); patchright retry wrapped INSIDE upstream's wall-clock deadline; `render_mode: "full"` tagging |
| `deploy/docker/server.py` | static branch in `/crawl` (before stream check + all-failures→500 rewrite); lifespan closes static httpx client + patchright singleton |
| `deploy/docker/schemas.py` | `CrawlRequest.render_mode: Literal["full","static"]` |
| `deploy/docker/supervisord.conf` | gunicorn target `aitosoft_entry:app` (upstream line now uses `%(ENV_GUNICORN_BIND)s` — kept) |
| `Dockerfile` | `RUN playwright install chrome` + copy `chrome-*` cache to appuser |
| `deploy/docker/config.yml` | stealth kwargs; `wall_clock_s: 180`; `pool.max_pages: 5` + `stuck_busy_timeout_sec: 600`; `memory_threshold_percent: 85`; UA bumped Chrome/133 → Chrome/138 |

### New Aitosoft file

- `deploy/docker/aitosoft_static_mode.py` — static-mode implementation moved
  out of api.py into its own module (api.py now carries only a ~25-line hook).

### Trusted-client boundary relaxations (aitosoft_entry.py)

Upstream 0.9.0 rejects/clamps "power fields" on network request bodies. Two
defaults broke MAS's existing contract; we relax exactly those at import time:
1. `browser_config.headers` allowed again (MAS persona headers; forbidden
   upstream). Everything else stays forbidden (js_code, proxies, extra_args…).
2. `page_timeout` clamp raised 60s → 180s (MAS sends 90s; capped by the
   wall-clock deadline anyway).

**Behavior changes MAS must know about** (see cross-repo message 2026-07-16):
- `magic`, `simulate_user`, `override_navigator`, `js_code`, proxy fields,
  `session_id`, `shared_data` etc. in `crawler_config` now → HTTP 400
  **on presence, even with a falsy value** (`"magic": false` is rejected!).
- Unknown/unlisted fields are silently dropped (forward-compatible).
- Unresolvable/dead domains now → HTTP 400 `URL blocked (SSRF protection)`
  from seed validation (both full and static mode) instead of the old
  500/inner-failure shapes.
- `/docs`, `/metrics`, `/playground` now require the bearer token (only
  `/health` is public).
- The 504 wall-clock timeout body is now plain `"Crawl exceeded the time
  limit"` (upstream shape), not our old JSON with memory stats.

### Not affected

- `BrowserConfig.set_defaults()` mechanism intact — wrapper approach unchanged.
- `antibot_detector.py` unchanged → patchright fallback trigger identical.
- MAS-sent fields verified allowed: `user_agent`, `viewport_*`, `locale`,
  `timezone_id`, `geolocation`, `remove_consent_popups`, `wait_until`,
  `max_retries`, `delay_before_return_html`, `scan_full_page`.
- Broken-cert sites still crawl in full mode — **RESOLVED 2026-07-17,
  verified live.** Right behavior, but both earlier explanations were wrong.
  The original note credited the context-level `ignore_https_errors` default
  (true); a first CORRECTION then claimed a regression because upstream's
  `enforce_egress` (egress_broker.py) forces `ignore_https_errors=False`
  unless `CRAWL4AI_ALLOW_INSECURE_TLS=true` (unset on the Container App).
  Both miss the real mechanism: upstream hardcodes
  `--ignore-certificate-errors` into every Chromium launch
  (`browser_manager.py` `build_browser_flags` + `_build_browser_args`),
  disabling cert validation process-wide — the context-level setting, and
  therefore `enforce_egress`'s forcing of it, is moot. (`enforce_egress`
  scrubs that flag only from caller `extra_args`, not from these generated
  launch flags.) Live proof: full-mode crawl of expired.badssl.com downloads
  the page — its 500 is an unrelated antibot `minimal_text` false positive
  on the tiny page; static mode returns it fine (httpx `verify=False`).
  `CRAWL4AI_ALLOW_INSECURE_TLS` deliberately left unset — it would change
  nothing. Re-check the flags on every upstream sync. Full record:
  `tasks/tls-broken-cert-regression.md`.

### Upstream infra changes that affect deployment

- Image `CMD` is now `bash entrypoint.sh` → resolves `REDIS_PASSWORD`
  (generates ephemeral if unset), `GUNICORN_BIND` (defaults `[::]:11235` when
  a token is set). **Set `GUNICORN_BIND=0.0.0.0:11235` in the Container App
  env** to avoid IPv6-bind surprises.
- `/app` is root-owned read-only at runtime; new artifact store at
  `/var/lib/crawl4ai/outputs` (override locally: `CRAWL4AI_ARTIFACT_DIR`).
- Redis is loopback + password-protected inside the container.
- New per-replica global page semaphore: upstream `server.py` caps concurrent
  `arun` at `pool.max_pages` (5) per replica — complements our pool patches.

### Verification (2026-07-16, local arm64 devcontainer)

- Server boots via `aitosoft_entry:app`; `/health` → 0.9.2.
- Auth: no token → 401, bad token → 401, good token → 200.
- Full-mode crawl with MAS-shaped body (persona headers, page_timeout 90000,
  locale/timezone) → success (validates boundary relaxations).
- Static mode → success, `render_mode: "static"`, 0.07s.
- **Tier 1 regression 4/4 PASS** (caverna, accountor, solwers, jpond) against
  local server (`reports/v0.9.2-local2-regression-tier1.md`).
- Local-only quirks (not prod-relevant): arm64 has no real Chrome, so
  `channel: chrome` was temporarily stripped for the local run; stale `jwt`
  1.4.0 package shadowed PyJWT locally (fixed by uninstall; image installs
  fresh from requirements.txt which pins PyJWT only).

---

## Static-Mode Fallback (`render_mode: "static"`) — 2026-04-15

### Why

During the 2026-04-15 WAA batch, `https://www.roadscanners.com/*` caused
Playwright to hang at the C-level DevTools protocol: every request produced
a pool `Using hot pool browser` log, then nothing for 180s until the Fix-1
`asyncio.wait_for` fired. Zero `[FETCH]` / `[SCRAPE]` / `[ANTIBOT]` banners
— the hang happened before our Python instrumentation could log. This is a
Playwright capability gap, not a crawl4ai bug: the site's HTML is
reachable over plain HTTP (MAS's Gemini-grounded search proved it).

Rather than deepen surgery on Playwright's internal wait-state machinery,
we added an **opt-in alternate rendering path** that bypasses the browser
entirely. MAS auto-pivots to static mode on its side after 2 consecutive
504s per host per session, capping the worst-case per-company cost at
2 × 180s = 360s before the host is blacklisted for the session.

### What

New optional top-level field on `POST /crawl`:

```json
{
  "urls": ["https://www.roadscanners.com/contact/offices/"],
  "render_mode": "static"
}
```

When `render_mode: "static"` (default `"full"`):

- Browser pool / Playwright / patchright retry are **not touched**.
- Each URL is fetched via a module-scope `httpx.AsyncClient`
  (`STATIC_FETCH_TIMEOUT_S = 15s` per URL, `verify=False`, follows
  redirects, UA mirrored from `config.yml`).
- Before conversion, `_strip_hidden_decoys()` removes CSS-hidden nodes with
  BeautifulSoup: `<script>/<style>/<noscript>/<template>`, inline
  `display:none`/`visibility:hidden`, and the class allowlist
  `oe_displaynone` (Odoo), `d-none` (Bootstrap), `is-hidden` (Bulma).
  Motivation: Odoo sites inject a hidden `<span class="oe_displaynone">null
  </span>` inside emails; html2text has no CSS model and would emit
  `name@nulldomain.fi`. Deliberately does NOT strip `sr-only` /
  `visually-hidden` (legitimate screen-reader content — a site putting
  contact data there would lose it). If a site ever reports missing
  contacts in static mode, check this pass first.
- The cleaned body is converted to markdown via the vendored
  `crawl4ai.html2text.HTML2Text` (`body_width=0`, `ignore_images=True`).
- Response envelope matches full-mode exactly; each inner result has
  `render_mode: "static"` so MAS can weight confidence downstream.
- Full-mode responses now also carry `render_mode: "full"` on every result
  for symmetry.

### Error semantics

- httpx timeout / connection error → HTTP **200** with inner
  `success: false`, `status_code: 0`,
  `error_message: "static-fetch: timeout after 15s"`. **Not** HTTP 504 —
  504 stays reserved for Fix-1's "we tried to render and failed".
- 4xx/5xx from the target site → HTTP 200, inner `success: false`,
  upstream `status_code` preserved, (usually error-page) body wrapped as
  markdown.
- `html2text` parser failure → raw HTML returned as `raw_markdown`
  (never fails the request). MAS can strip tags on its end.

### Out of scope (intentional)

- No hookability, extraction strategy, or content-filtering for static
  mode — it's deliberately minimal.
- `/crawl/stream` is unchanged; static is non-streaming by definition.
- `/crawl/job` is unchanged; `render_mode` defaults to `"full"` when not
  threaded through.
- No `links.internal` / `links.external` extraction — MAS has its own
  link extractor and doesn't need it here.

### Files touched

| File | Change |
|------|--------|
| `deploy/docker/schemas.py` | `CrawlRequest` gets `render_mode: Literal["full", "static"] = "full"` |
| `deploy/docker/api.py` | New `handle_static_crawl_request` + module-scope `_static_http_client`; `handle_crawl_request` short-circuits when `render_mode == "static"` and tags full-mode results with `render_mode: "full"` |
| `deploy/docker/server.py` | `/crawl` endpoint branches on `render_mode == "static"` before the stream check and before the all-failures → 500 rewrite; lifespan shutdown calls `close_static_http_client` |
| `test-aitosoft/test_site.py` | New `--render-mode {full,static}` CLI flag |
| `AITOSOFT_CHANGES.md` | This entry |

### Verification (2026-04-15, against live service)

- Tier 1 regression (`test_regression.py --tier 1 --version static-mode`):
  **4/4 PASS** — caverna.fi, accountor.com/fi/finland, solwers.com/...,
  jpond.fi. Default `full` path intact.
- Live roadscanners `/contact/offices/` with `render_mode:static`: top-level
  200, inner success=true, all four acceptance strings present
  (`annele.matintupa@roadscanners.com`, `virpi.halttu@roadscanners.com`,
  `+358 40 1544 011`, `+358 50 353 4268`), no `@null` decoy, md 9654B
  returned in 0.16s.
- Timeout path via columbia-road.com: HTTP 200 + inner `success:false` +
  `error_message:"static-fetch: timeout after 15s"`. Contract honoured.
- Second success-path SPA (caverna.fi/yhteystiedot/): 200/200, render_mode
  static, 758B markdown in 0.19s.

### Deploy

- **Image**: `aitosoftacr.azurecr.io/crawl4ai-service:0.8.6-static-mode`
  (digest `sha256:7cf6e3419c581b967185c1c3279c92375cc67a4f45abcab223b1767c1bb9bc68`).
- **Revision**: `crawl4ai-service--0000011`, 3 replicas healthy, 100% traffic.
- **Command used**: `az acr build ...` → `az containerapp update ...` (MAS bearer
  token preserved — NOT via `deploy-aitosoft-prod.sh --update-only`).

---

## Request-Timeout + Stuck-Slot Leak Fixes (2026-04-14, late)

### Incident

Second WAA batch after the max_pages fix ran healthy for 25 companies then
degraded over 90 min on 2 bot-protected sites (ahlmanedu.fi, diabetes.fi).
Memory climbed 68 → 82% on the surviving replica, all subsequent requests
504'd at Azure's 240s ingress timeout. User killed batch at 14:24 UTC.

### Root Cause

`asyncio.wait_for` wasn't wrapping `crawler.arun` in `api.py`, so when a
bot-protected URL triggered the full retry chain (antibot × 2 + patchright)
beyond 240s:
1. Azure ingress 504'd to MAS, but **FastAPI did NOT cancel the backend
   coroutine** on client disconnect
2. `await crawler.arun(url)` kept running indefinitely
3. `release_crawler` in the finally block never fired
4. `active_requests` counter leaked → pool slot wedged
5. Janitor skipped the stuck browser (`active_requests > 0` check)
6. Pool spawned overflow browsers for new requests → memory climbed

Same mechanism as the max_pages incident but slower-onset because overflow
browsers distributed the leak across multiple Chromium processes.

### Fixes

**Fix 1 — Request timeout** (`deploy/docker/api.py`)
- Wrap `arun + patchright_retry` in `asyncio.wait_for(..., timeout=180s)`
- On TimeoutError: return HTTP 504 with same error-shape as 500 path so WAA
  retry logic matches
- Added `except HTTPException: raise` before generic handler so 504 isn't
  rewrapped as 500
- 180s < 240s Azure ingress timeout with margin for cleanup + JSON encode

**Fix 2 — Janitor force-close** (`deploy/docker/crawler_pool.py`)
- Added `BUSY_SINCE[id(crawler)]` tracking: stamped on 0→1 transition in
  `_incr_active()`, cleared on release when counter reaches 0
- Added `STUCK_BUSY_TIMEOUT_S=600s` (configurable via
  `crawler.pool.stuck_busy_timeout_sec` in config.yml)
- New `_force_close_stuck()` pass in `janitor()` closes any browser busy
  for > 600s, logs WARNING so ops notice if Fix 1 ever regresses
- Covers permanent + hot + cold pools

**Fix 3 — Batch-scale runbook** (`azure-deployment/batch-scale.sh`)
- `./batch-scale.sh up [N]` sets `minReplicas=N` before a WAA batch
- `./batch-scale.sh down` returns to `minReplicas=0` after
- Prevents KEDA http-scaler from scaling 2→1 mid-batch (seen at 12:51 UTC
  in the 2026-04-14 incident)

**Fix 4 — Patchright singleton bounds** (`deploy/docker/aitosoft_patchright_fallback.py`)
- `asyncio.Semaphore(5)` caps concurrent `arun` calls on the shared
  undetected crawler
- Recycle singleton every 100 uses to bound long-run Chromium memory growth
- Defense-in-depth for the same leak class, important for 10+ parallel agents

### Files Modified

| File | Change |
|------|--------|
| `deploy/docker/api.py` | `CRAWL_REQUEST_TIMEOUT_S=180`, `asyncio.wait_for` wrapper, `except HTTPException: raise` |
| `deploy/docker/crawler_pool.py` | `BUSY_SINCE` dict, `_incr_active()` helper, `_force_close_stuck()`, updated `release_crawler`/`close_all` |
| `deploy/docker/aitosoft_patchright_fallback.py` | `_UNDETECTED_SEM` semaphore, `_UNDETECTED_USES` counter, `_recycle_undetected()` |

### Files Added

| File | Purpose |
|------|---------|
| `azure-deployment/batch-scale.sh` | Toggle minReplicas around WAA batch |
| `azure-deployment/setup-memory-alert.sh` | Azure alert: memory > 85% for 5 min |
| `test-aitosoft/test_soak.py` | 30-min / 3h soak test with mixed healthy+hard URLs |
| `tasks/scale-audit-2026-04-14.md` | Scale concerns audit for 10+ parallel agents |

### Deployed As
`aitosoftacr.azurecr.io/crawl4ai-service:0.8.6-leak-fix`

---

## Crawler Pool max_pages Enforcement (2026-04-14)

### Incident
WAA batch run caused cascading page starvation: crawls hung after ~09:43,
active_requests climbed to 44 on a single browser (2 vCPU / 4 GiB), CPU
starvation prevented any page from completing, MAS retries made it worse.

### Root Cause
`crawler_pool.py` had no per-browser concurrency limit. The `max_pages: 5`
setting in config.yml was never enforced — the pool kept handing out the same
browser regardless of active page count.

### Fix
- Added `MAX_PAGES` enforcement in `get_crawler()`: when a browser reaches
  the limit, the pool creates an overflow browser with a unique key instead
  of piling more pages onto the same Chromium process
- Overflow browsers use `sig_ovf_N` keys to avoid overwriting existing pool
  entries; the janitor cleans them up normally when idle
- Deployed as `0.8.6-maxpages-fix`

### Files Modified
- `deploy/docker/crawler_pool.py` — `_active()` helper, MAX_PAGES cap in
  `get_crawler()`, overflow key logic (`OVERFLOW_SEQ`)

---

## Wrapper Architecture + Security Merge (2026-04-14)

### What Changed
Restructured how our fork integrates with upstream to make future merges
near-conflict-free, then merged upstream/develop which had 2 CVSS 9.8
security fixes.

### Architecture: Wrapper Entry Point
Created `deploy/docker/aitosoft_entry.py` — loaded by gunicorn instead of
`server:app`. This wrapper:
1. Calls `BrowserConfig.set_defaults(**config_yml_kwargs)` at import time,
   using upstream's own `@_with_defaults` mechanism (`async_configs.py`).
   Every `BrowserConfig.load({})` now inherits config.yml stealth/chrome/UA/viewport.
2. Imports `app` from upstream `server.py` (unmodified).
3. Adds `SimpleTokenAuthMiddleware` when `CRAWL4AI_API_TOKEN` env var is set.

This replaces the old `aitosoft_browser_merge.py` module (deleted) and the
3-line auth middleware patch in `server.py` (reverted).

### Files Modified
- `deploy/docker/supervisord.conf` — `server:app` → `aitosoft_entry:app`
- `deploy/docker/server.py` — REVERTED to upstream (auth middleware removed)
- `deploy/docker/api.py` — removed `merge_browser_config` calls; only 4
  patchright retry lines remain as our modification

### Files Created
- `deploy/docker/aitosoft_entry.py` — wrapper entry point (25 lines)

### Files Deleted
- `deploy/docker/aitosoft_browser_merge.py` — replaced by `BrowserConfig.set_defaults()`

### Upstream Merge
Merged 8 commits from `upstream/develop`:
- `e326da9` fix(security): complete AST sandbox escape remediation (CVSS 9.8)
- `2fc39cb` fix(security): remove eval() from computed fields, harden config deserializer
- `8995c1b` feat: expose arun_many config-list support in Docker API
- `ec560f1` fix: default LLMExtractionStrategy extraction_type to schema
- `7e7533e` fix: validate markdown_generator type in CrawlerRunConfig
- Plus docs/merge commits

Security hardening adds `_SAFE_CONFIG_ALLOWED_NAMES` / `_SAFE_CONFIG_ALLOWED_ATTRS`
allowlists to `_safe_eval_config()` in server.py, blocking AST sandbox escapes.

### Upstream Modification Inventory (after restructure)
| File | Lines changed | Notes |
|------|--------------|-------|
| `deploy/docker/api.py` | 4 lines | Patchright retry only |
| `deploy/docker/supervisord.conf` | 1 word | Entry point |
| `crawl4ai/browser_adapter.py` | ~20 lines | Stealth 2.x port (upstream bug) |
| `crawl4ai/browser_manager.py` | ~5 lines | GPU flag gating (upstream bug) |
| `Dockerfile` | 1 line | `RUN playwright install chrome` |
| `deploy/docker/config.yml` | deployment config | Stealth settings |
| `.pre-commit-config.yaml` | exclude patterns | Pre-existing upstream lint issues |

**Not modified**: `server.py` (was 3 lines, now 0)

---

## Stealth Package (2026-04-11)

### What Changed
Full stealth overhaul of the Docker image and runtime browser configuration,
driven by MAS observing consistent HTTP 500s on 4 Cloudflare/AEM/WP.one-fronted
sites (baxter.fi, lundbeck.com/fi, pedelux.fi, rederiabeckero.ax) while the
same sites responded 200 to plain `curl`. Fingerprint diagnostic against bot
detection pages (sannysoft, areyouheadless, creepjs, browserleaks) confirmed
multiple fingerprint leaks: stale UA, no WebGL, wrong locale/timezone, missing
stealth patches.

### Files Modified (Upstream)

**`Dockerfile`** — added one RUN step to install real Google Chrome:
```
RUN playwright install chrome
```
Playwright's bundled Chromium has a distinct TLS/JA3 handshake that Cloudflare's
bot-management rulesets flag. Real Chrome matches ~65% of desktop web traffic
and is the cheapest single fingerprint fix. The `chrome-*` cache copy into
`appuser` home is conditional (falls back cleanly if Playwright bundles Chrome
system-wide via apt instead of cache-local).

**`deploy/docker/api.py`** — two 2-line edits in `handle_crawl_request` (line
~567) and `handle_stream_crawl_request` (line ~740). Both call the new
`merge_browser_config()` helper instead of `BrowserConfig.load()` directly.
Root cause: upstream `api.py` loaded the user's `browser_config` dict into a
BrowserConfig with class defaults, so config.yml.browser.kwargs only affected
the PERMANENT pool browser (which is never hit by real requests — its
signature differs from the all-defaults signature of a bare request). Our
stealth/channel/UA/viewport settings were dead code for API traffic until
this fix.

**`crawl4ai/browser_adapter.py`** — `StealthAdapter._check_stealth_availability`
and `apply_stealth` ported to the `playwright-stealth` 2.x class-based API
(`from playwright_stealth import Stealth; Stealth().apply_stealth_async(page)`).
Upstream v0.8.6 pins `playwright-stealth>=2.0.0` in pyproject.toml but still
imports the old 1.x names (`stealth_async` / `stealth_sync`), which no longer
exist. Imports failed silently and `apply_stealth` became a no-op — so
`enable_stealth=True` had zero effect, even when set correctly. Confirmed in
the v2 deploy where `navigator.webdriver` remained `false` and `chrome.runtime`
remained absent on sannysoft/creepjs. Worth filing a PR upstream.

**`crawl4ai/browser_manager.py`** — `BrowserManager._build_browser_args` (line
~1057) hardcoded `--disable-gpu`, `--disable-gpu-compositing`, and
`--disable-software-rasterizer` at the top of its arg list. The sibling
`ManagedBrowser.build_browser_flags` (line ~69) gates those same flags on
`if not config.enable_stealth:`. The two flag builders had drifted out of
sync. Moved the GPU flags into the same conditional block so stealth-enabled
crawls keep WebGL (via SwiftShader), which is one of the loudest anti-bot
signals Cloudflare scores against. Also worth a PR upstream.

**`deploy/docker/config.yml`** — browser kwargs overhaul:
```yaml
browser:
  kwargs:
    headless: true
    text_mode: false                 # was true — real browsers load images/fonts
    enable_stealth: true             # NEW — playwright-stealth patches
    channel: chrome                  # NEW — use installed real Chrome
    viewport_width: 1920             # NEW — was default 1080
    viewport_height: 1080            # NEW — was default 600
    user_agent: "Mozilla/5.0 (X11; Linux x86_64) ... Chrome/133.0.0.0 ..."
  extra_args:
    - "--no-sandbox"
    - "--disable-dev-shm-usage"
    - "--allow-insecure-localhost"
    - "--ignore-certificate-errors"
    # REMOVED: --disable-gpu, --disable-software-rasterizer (killed WebGL)
    # REMOVED: --disable-web-security (Cloudflare bot rules match on this)
```

### Files Modified (Aitosoft-only)

- `test-aitosoft/test_regression.py` — refreshed `TIER_1_SITES` list to match
  CLAUDE.md (caverna, accountor, solwers, jpond). Retired sites removed:
  talgraf (CF block), tilitoimistovahtivuori (404), monidor (restructure).
  Default config swapped from `fast` (magic=true) → `optimal` (matches MAS).
- `test-aitosoft/test_site.py` — `optimal` config now includes
  `remove_consent_popups: true`. `CRAWL4AI_URL` reads from `CRAWL4AI_API_URL`
  env var so tests can target localhost/staging.

### New Files

- `deploy/docker/aitosoft_browser_merge.py` — 50-line helper that merges
  config.yml browser kwargs under a user's request `browser_config`. Called
  from `api.py` at the two `BrowserConfig.load()` sites. Defensive: if the
  user sends a fully serialized BrowserConfig (`{type, params}` shape), the
  merge is skipped and the object is respected as-is.
- `test-aitosoft/test_fingerprint.py` — before/after fingerprint diagnostic.
  Hits sannysoft, areyouheadless, creepjs, browserleaks through crawl4ai's
  own `/crawl` API, runs a JS probe inside the page (navigator.webdriver,
  UA, platform, timezone, locale, plugins, cores, screen, viewport, WebGL
  vendor/renderer, chrome.runtime, canvasFp, audioContext), and saves the
  full HTML + screenshot + probe JSON + summary under `stealth-<label>/`.
- `test-aitosoft/stealth-baseline/` — fingerprint capture with OLD config
  (for before/after comparison). Key baseline signals:
  - `webdriver: false` (tells: real Chrome is `undefined`)
  - UA `Chrome/116.0.0.0` (2 years stale)
  - viewport `1080x600` (unusual, signals narrow bot)
  - `timezone: UTC, locale: en-US` (wrong for Finnish sites)
  - `webgl: no-webgl` (HUGE tell: `--disable-gpu` flag)
- `test-aitosoft/stealth-after/` — fingerprint capture with NEW config
  (post-deploy). See file for comparison.
- `test-aitosoft/reference/persona_generator.ts` — reference TypeScript for
  the MAS team. Deterministic persona (UA/viewport/Accept-Language/sec-ch-ua)
  from `master_company_id` via SHA-256(salt + id). Pool is Chromium-family
  only (Chrome + Edge) to match crawl4ai's engine. Weighted by EMEA desktop
  share. Rotatable via `PERSONA_SALT` constant.

### Rationale (the "why")

See the brainstorm dialogue between crawl4ai-Claude and aitosoft-platform-Claude
preceding this change (conversation thread in the Claude Code session).
Short version: every change moves the request one step closer to a real
browser visit. None of the changes add new behavior to sites that already
worked — they only REMOVE the hostile flags / outdated defaults / missing
stealth patches that were leaking automation signals to bot detectors.

### Per-Request Customization (for MAS)

Locale, timezone, and geolocation are already forwarded by crawl4ai via
`CrawlerRunConfig` → Playwright `new_context()` (see `browser_manager.py`
lines ~1351-1366). No code change was needed for those. MAS can send them
on every request under `crawler_config`:
```json
{
  "urls": ["https://example.fi"],
  "browser_config": {
    "user_agent": "<from persona>",
    "viewport_width": 1920,
    "viewport_height": 1080,
    "headers": {"Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8"}
  },
  "crawler_config": {
    "locale": "fi-FI",
    "timezone_id": "Europe/Helsinki",
    "wait_until": "domcontentloaded",
    "remove_consent_popups": true,
    "page_timeout": 90000,
    "max_retries": 2
  }
}
```

### Deployment

Built via `az acr build` (remote ACR build — no local Docker needed in the
devcontainer) and deployed via `az containerapp update --image ...`. Four
iterations landed as revisions `stealth-v1` → `stealth-v4`; each revealed
an additional layer of the same root cause (config.yml wasn't reaching the
request path, then the stealth library's API had changed, then a duplicate
flag list had drifted out of sync, then the webdriver patch was gated on a
condition that never fired, then platform and UA were mismatched). Final
deployed image: `aitosoftacr.azurecr.io/crawl4ai-service:0.8.6-stealth-v4`.

### Results

**Fingerprint diagnostic — baseline vs v4:**

| Signal                  | Baseline                 | v4                                   |
|-------------------------|--------------------------|--------------------------------------|
| `navigator.webdriver`   | `false` (automation tell)| `undefined` (matches real Chrome)    |
| User-Agent              | Chrome 116 / X11 Linux   | Chrome 133 / Windows NT 10.0         |
| `navigator.platform`    | `Linux x86_64`           | `Win32` (matches UA)                 |
| Viewport                | 1080 × 600               | 1920 × 1080                          |
| WebGL vendor            | `no-webgl`               | `Intel Inc.`                         |
| WebGL renderer          | `no-webgl`               | `Intel Iris OpenGL Engine`           |
| `chrome.runtime`        | `false` (Chromium)       | `false` (matches real Chrome w/o ext)|

Full artifacts: `test-aitosoft/stealth-baseline/` vs `test-aitosoft/stealth-v4/`
(HTML + screenshots + probe JSON per target site).

**Tier 1 regression (Caverna, Accountor, Solwers, JPond):** 4/4 PASS. Report
at `test-aitosoft/reports/stealth-v4-regression-tier1.md`.

**Previously-blocked sites — still blocked, but with clear diagnostics:**

| Site                   | Baseline   | v4 Result                                                    |
|------------------------|------------|--------------------------------------------------------------|
| baxter.fi              | HTTP 500   | Blocked: "Access Denied on short page (HTTP 403, 6264 bytes)" (Akamai) |
| lundbeck.com/fi        | HTTP 500   | Blocked: "HTTP 403 with HTML content (923 bytes)" (WAF)     |
| pedelux.fi             | HTTP 500   | Blocked: "Cloudflare JS challenge" (never resolves)         |
| rederiabeckero.ax      | HTTP 500   | Blocked: "Structural: no <body> tag (15 bytes)" (proxy?)    |

v4 fingerprint work did NOT unblock these four. The nature of the blocks
(static 403 pages from Akamai/WAFs, a Cloudflare challenge that never
resolves, a 15-byte near-empty response) points at **IP-based or network-path
detection** rather than fingerprint detection. The Azure Container Apps
egress IP is almost certainly flagged by these specific gatekeepers — which
stealth improvements cannot fix.

**What v4 DID fix:** the fingerprint side of the equation for the ~380 sites
that already work. Those sites now get a request that's substantially harder
to flag as automation: real Chrome binary, current Chrome version, stealth
patches active, WebGL present, platform/UA matched, viewport realistic. This
is protective insurance against future fingerprint-based detections — a
site that passes today shouldn't start failing in 6–12 months because our
fingerprint got stale.

**Follow-up — patchright fallback retry (shipped as v5):**

After discussing with MAS Claude, we chose to implement option 2 (patchright
fallback) and skip residential proxies unless production data shows >3% blocks.

New file: `deploy/docker/aitosoft_patchright_fallback.py`
- Lazy singleton `AsyncWebCrawler` with `UndetectedAdapter`
- `maybe_retry_blocked(results, urls, crawler_config, base_browser_config)`
  scans for results marked blocked by antibot_detector and retries those
  specific URLs through patchright
- On retry success, replaces the blocked entry; on retry failure, keeps the
  first-tier diagnostic so MAS can branch on the original block reason
- Stealth is stripped from the BrowserConfig before patchright (the two
  conflict — see `browser_manager.py:787`)

Wired into `api.py` `handle_crawl_request` right after the first-tier crawl
completes and before the memory/response bookkeeping. Wrapped in a
try/except so a broken retry never fails the request — worst case, caller
gets the first-tier result unchanged.

Expected impact on the 4 blocked sites:
- **pedelux.fi** (Cloudflare JS challenge): high likelihood of unblock.
  Patchright is specifically good at Cloudflare challenges.
- **baxter.fi / lundbeck.com** (Akamai/WAF 403): moderate likelihood.
  Depends whether Akamai's detection is JA3/fingerprint-based (patchright
  has different TLS fingerprint than regular Playwright-Chromium).
- **rederiabeckero.ax** (15-byte response): low likelihood. Smells like an
  IP-level block rather than fingerprint.

If patchright still doesn't get through, MAS's WebsiteAnalysisAgent has a
`research_web` fallback path that finds 3–5 contacts per company without
the direct scrape, so the graceful-degradation story holds even for the
blocked minority.

---

**Residential proxy option (deferred):**
Available if MAS production shows >3% blocks — can be added per-site via
`crawler_config.proxy_config`. Not implemented in this round.

### Per-Request Customization (for MAS)

---

## Resource Scaling Fix (2026-04-04)

### What Changed
Investigation of 500s+ request latency incidents revealed severe resource starvation.
Azure logs showed requests waiting 8+ minutes in queue for CPU/memory, while actual crawls
completed in <10 seconds. Root cause: 1 CPU / 2 GiB running 40 concurrent Playwright pages.

### Config Changes
- `deploy/docker/config.yml`: `max_pages` 40→5, `memory_threshold_percent` 95→85%
- `azure-deployment/deploy-aitosoft-prod.sh`: Updated defaults to 2 CPU / 4 GiB / 20 replicas

### Azure Changes (Applied Live)
| Setting | Before | After |
|---------|--------|-------|
| CPU | 1.0 | 2.0 |
| Memory | 2.0 GiB | 4.0 GiB |
| minReplicas | 0 | 0 |
| maxReplicas | 3 | 20 |
| max_pages (per replica) | 40 | 5 |
| memory_threshold | 95% | 85% |

### Strategy
Horizontal scaling: fewer pages per replica, more replicas. Each replica gets its own
Chromium process with dedicated CPU. Azure Container Apps scales replicas based on HTTP
traffic and scales to zero when idle (zero cost).

### Evidence (from Azure Log Analytics)
- tassufoods.fi: 524s total latency, but FETCH log shows 9.51s actual crawl time
- 8+ minutes spent waiting with pool health checks showing 85% memory, no FETCH activity
- Memory spiking to 100% intermittently during concurrent page processing

---

## v0.8.6 Upgrade (2026-03-26)

### What Changed
Merged 197 upstream commits covering v0.8.0 → v0.8.5 → v0.8.6.

### Security Fixes (Critical)
- **litellm supply chain compromise**: Replaced `litellm` with `unclecode-litellm==1.81.13` (PyPI supply chain attack)
- **Redis CVE-2025-49844 (CVSS 10.0)**: Upgraded Redis to 7.2.7
- **Pod deadlock fix**: Removed shared LOCK contention in monitor

### New Anti-Blocking Features (v0.8.5)
- **`remove_consent_popups=True`**: CMP-aware cookie consent removal (OneTrust, Cookiebot, Didomi)
  - Tested on accountor.com: 7811 tokens without needing `magic=True` (was 32 tokens before)
- **3-tier anti-bot retry + proxy escalation**: `max_retries=N` with proxy list auto-escalation
- **`flatten_shadow_dom=True`**: Flattens Web Components into readable DOM
- **`fallback_fetch_function`**: Custom async fallback when all retries fail

### Bug Fixes
- `scan_full_page` hang fix (prevents infinite-scroll pages from hanging)
- `is_blocked()` re-check on fallback fetch failure
- BM25ContentFilter deduplication fix
- Screenshot distortion fix
- MCP SSE endpoint crash fix on Starlette >=0.50

### Dependency Changes
- `litellm` → `unclecode-litellm==1.81.13` (security)
- `tf-playwright-stealth` → `playwright-stealth>=2.0.0`

### Merge Conflicts Resolved
- `deploy/docker/server.py` — Kept our auth middleware, took upstream's `get_crawler` top-level import + `crawler = None` cleanup pattern
- `deploy/docker/config.yml` — Kept `enabled: true`, added upstream's `api_token` field
- `crawl4ai/__version__.py` — Took upstream v0.8.6
- `Dockerfile`, `README.md`, `SECURITY.md`, `deploy/docker/README.md`, `docs/md_v2/blog/index.md` — Took upstream versions

### Regression Test Results (v0.8.6)
| Site | Config | Result | Tokens |
|------|--------|--------|--------|
| monidor.fi | baseline | 404 (site restructured) | - |
| caverna.fi | baseline | PASS | 5833 |
| accountor.com | `remove_consent_popups=True` | PASS | 7811 |
| solwers.com | baseline | PASS | 12441 |

### Recommended Config Updates for MAS
```python
# Default config (replaces "fast" config)
CrawlerRunConfig(
    remove_consent_popups=True,
    remove_overlay_elements=True,
)

# Heavy config (replaces magic=True workaround)
CrawlerRunConfig(
    remove_consent_popups=True,
    remove_overlay_elements=True,
    scan_full_page=True,
    max_retries=2,
)
```

---

## v0.8.0 Upgrade Notes

### Security Fixes (Critical)
- **RCE Fix**: Removed `__import__` from hook allowed builtins
- **LFI Fix**: Added URL scheme validation, blocked file://, javascript:, data: URLs

### Breaking Changes (No Impact on Aitosoft)
- Hooks disabled by default (we don't use hooks)
- file:// URLs blocked in Docker API (we only use http/https)

### Dependency Changes
- Python requirement: 3.9 → 3.10 (we use 3.11)
- New: `patchright>=1.49.0` (stealth browser)
- **REMOVED from core**: `sentence-transformers` (now optional, saves ~500MB)

---

## Change Log

### 2026-01-20: Production Deployment to West Europe

**Purpose:** Deploy to production using existing aitosoft-prod infrastructure

**Deployment Details:**
- **Location**: West Europe (co-located with MAS)
- **Resource Group**: `aitosoft-prod` (reusing existing resources)
- **Image**: `aitosoftacr.azurecr.io/crawl4ai-service:0.8.0-secure`
- **Endpoint**: `https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io`
- **Authentication**: ✅ Enabled and tested
- **Cost**: ~€30-50/month (only container app cost)

**Files Created:**
- `azure-deployment/deploy-aitosoft-prod.sh` - Production deployment script
- `DEPLOYMENT_INFO.md` - Current production info, credentials, usage examples

**Infrastructure Used:**
- `aitosoftacr` - Existing ACR (now has crawl4ai-service repository)
- `aitosoft-aca` - Existing Container Apps environment
- `workspace-aitosoftprodnCsc` - Existing Log Analytics

**Benefits:**
- Cost efficient (reuses existing infrastructure)
- Same region as MAS (lower latency)
- Simple token auth working correctly

---

### 2026-01-20: Add Simple Token Authentication

**Purpose:** Add simple Bearer token authentication for production security

**Files Modified:**
- `deploy/docker/server.py` - Added SimpleTokenAuthMiddleware to security setup (3 lines)
- `deploy/docker/config.yml` - Enabled security: true
- `azure-deployment/production-config.yml` - Enabled security, disabled JWT

**Files Created:**
- `deploy/docker/simple_token_auth.py` - Middleware for static token authentication (39 lines)
- `azure-deployment/SIMPLE_AUTH_DEPLOY.md` - Auth implementation guide

**How it works:**
- Uses `CRAWL4AI_API_TOKEN` environment variable as the auth token
- Requires `Authorization: Bearer <token>` header on all requests (except /health, /docs)
- Bypasses auth if `CRAWL4AI_API_TOKEN` is not set (development mode)
- Total modification: 42 lines of code added to upstream

**Why:** Upstream crawl4ai only provides JWT auth where anyone can get a token by calling `/token` with any email. This is unsuitable for preventing unauthorized access. Our simple token auth provides real security with one static secret token.

---

### 2026-01-19: Repository Cleanup

**Purpose:** Consolidate documentation and clean up repo structure

**Files Deleted:**
- `DEVELOPMENT_NOTES.md` - Merged into this file
- `message-to-claude.md` - Redundant with CLAUDE.md
- `.github/workflows/test-release.yml.disabled` - Dead code
- `.github/workflows/release.yml.backup` - In git history

**Files Moved:**
- `test_llm_webhook_feature.py` → `test-aitosoft/`
- `test_webhook_implementation.py` → `test-aitosoft/`

**Files Updated:**
- `CLAUDE.md` - Removed reference to deleted message-to-claude.md

---

### 2026-01-19: Repository Cleanup and Test Fixes

**Purpose:** Clean up development notes and fix async test support

**Files Modified:**
- `DEVELOPMENT_NOTES.md` - Cleaned up, removed outdated sections
- `test-aitosoft/test_fit_markdown.py` - Added `@pytest.mark.asyncio` decorator

**Dependencies Added:**
- `pytest-asyncio` - Required for running async tests with pytest

---

### 2026-01-19: Initial Repository Setup

**Purpose:** Configure development environment for Aitosoft team

**Files Modified:**
- `.devcontainer/devcontainer.json` - Refactored to use setup.sh, added GitHub CLI feature
- `.gitignore` - Added exception for `.devcontainer/setup.sh`

**Files Created:**
- `.devcontainer/setup.sh` - Extracted setup logic into maintainable script
- `CLAUDE.md` - Project guidance for Claude
- `AITOSOFT_CHANGES.md` - This file (change tracking)

**Files Updated (local only, git-ignored):**
- `.claude/settings.local.json` - Configured broader permissions for Claude Code
- `.env.local` - Fresh API token for local development

---

## Inherited from Previous Work (July 2025)

These files were created in the original Aitosoft fork:

| File/Directory | Purpose | Status |
|----------------|---------|--------|
| `test-aitosoft/` | Aitosoft-specific tests (separate from upstream) | Working |
| `azure-deployment/` | Azure Container Apps deployment guides | Needs review |
| `run_validation_tests.py` | Test orchestration script | Working |
| `.github/workflows/` | CI/CD pipelines | Working |

---

## Upstream Sync Notes

When merging upstream updates:
1. Check if `.devcontainer/devcontainer.json` has upstream changes
2. Our `setup.sh` approach may need reconciliation with upstream's inline commands
3. Review any changes to `deploy/docker/` which we depend on
4. Test that `test-aitosoft/` tests still pass after merge

---

## Planned Changes

- [ ] Deploy v0.8.0 to Azure production
- [ ] Verify production health check + auth
- [ ] Connect to multi-agent platform

---

## Quick Reference

### Start Local Server
```bash
uvicorn deploy.docker.server:app --host 0.0.0.0 --port 11235
```

### Test Endpoints
```bash
# Health check
curl http://localhost:11235/health

# Crawl request
curl -X POST http://localhost:11235/crawl \
  -H "Content-Type: application/json" \
  -d '{"urls": "https://example.com", "priority": 10}'
```

### Run Tests
```bash
pytest test-aitosoft/                    # Aitosoft-specific tests
pytest -xvs test-aitosoft/test_fit_markdown.py  # Single test
```
