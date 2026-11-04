# Aitosoft Changes Log

What changed in this fork, when, why, and what it cost or proved. Newest first.

- **What differs from upstream right now** is in `AITOSOFT_FILES.md`. That file
  is the per-file inventory; this one is history.
- **What is deployed right now** is not tracked here. Query it with the `az`
  commands at the top of `AZURE_OPERATIONS.md`, which also owns rollback (by
  digest since 2026-11-04; `0.9.2-egress-dns` is burned).
- **Image tags in entries** record which build carried a change. They are
  history, not current config.
- **Detail** lives in the `tasks/done/*.md` file each entry cites. An entry here
  is the summary plus the evidence a later decision depends on.
- **Post-deploy checks** (smoke, SSRF negatives, the pre-deploy byte-compare)
  are in `TESTING.md` §Quality gates.

---

## 2026-11-04: v0.9.5 deployed to `crawl4ai-service-se`, between two joint agent runs (`0.9.5-merge`)

**What changed:**
- **Production moved before we deployed:** MAS moved every agent to Sweden Central that morning and
  cloned this service as `crawl4ai-service-se` (environment `aitosoft-aca-se`, workload-profiles
  type; a new FQDN; egress from a 161-address pool). Our scripts, queries and docs were repointed
  (`cd9c4af`); the West Europe app is idle until MAS deletes it (on or after 2026-11-11).
- **`0.9.5-merge` deployed by digest** (`sha256:c34667704c3d…84caa5`, revision
  `crawl4ai-service-se--0000001`, live 09:12:58Z). `deploy-image.sh` now always updates by digest.
- **The browser moved 151 → 157** (Google Chrome 157.0.8103.38; the candidate built a day earlier
  had 156). Python packages as pinned.
- **Redis starts on `-se` again**: upstream `fadc53f` (in the merge) made the `::1` bind optional;
  on v0.9.2 it aborted on every `-se` start. `/crawl` never used it.

**Evidence:** two joint runs with MAS, one change each (the region, then the merge with Chrome 157),
75 companies each, wire counts identical on both sides. No regression. Run (ii)'s one lost company
and two newly empty pages were the sites (TEST_SITES_REGISTRY), and its two 500s were a scale-in
(AZURE_OPERATIONS §2.4). Cost per request was flat: AZURE_OPERATIONS §4.5. #2416 changed 0 of 630
real pages: FINDINGS §Parse collapse. Gates, numbers and the record: `tasks/upgrade-upstream-v0.9.5.md` §10.

---

## 2026-11-03: upstream v0.9.5 merged, behaviour kept for MAS (deployed 2026-11-04, above)

**What changed:**
- **Upstream v0.9.2 → v0.9.5** (`838869b`, 187 commits, 7 conflicted files, 25 hunks), an ordinary
  merge of the tag. Fourteen upstream security advisories come with it; none was urgent for us.
- **Four silent upstream changes were held at today's behaviour**, each pinned by tests:
  - TLS tolerance (`f0ada4c` removed `--ignore-certificate-errors`), via
    `egress_broker.ALLOW_INSECURE_TLS`;
  - the 180 s `page_timeout` cap (now `CRAWL4AI_MAX_TIMEOUT_MS`);
  - the capture point (`b536bf5`'s conditional consent wait, one line reverted);
  - recycling off (`max_pages_before_recycle: 0`; upstream #2419).
- **Also kept:** our 15 s connect budget through upstream's new proxy-chaining dials, and
  falsy-field tolerance extended to upstream's new global forbidden set.
- **MAS-visible, additive:**
  - every result carries keyed `links`/`media`;
  - 36 of 74 stored pages gain whitespace (+2 to +32 chars);
  - nested-noscript `fit_html` keeps content;
  - `Connection: close` on plain-http origins;
  - `/health` reports 0.9.5.
  - The heads-up is `tmp/mas-repo-messages/55-to-mas-…` (sent 2026-11-04).
- **Build:**
  - `azure-deployment/pip-constraints.txt` (the 0.9.2-capacity-gate-2 image's freeze) via
    `PIP_CONSTRAINT`.
  - `.dockerignore`: images up to `0.9.2-capacity-gate-2` carried `/tmp/project/.env`, `PRIVATE.md`
    and `tmp/`.
- **CI (on `main`, `f203391`):** `aitosoft-tests.yml` runs the offline half of `test-aitosoft/` on
  every push.

**Evidence:**
- **Server A/B, `main` vs merged, 40 cases on one binary:** identical status, `failure_class`,
  timing and `raw_markdown`.
- **Suites:** offline 262, fixture 70, security 343.
- **Inside the candidate image on real Chrome 156:** fixture 69/70, the one failure being
  production's known inline-PDF case.
- **Independent review:** no resolution bug; five follow-ups, all done.
- Full record: `tasks/upgrade-upstream-v0.9.5.md` §8.

**What it doesn't hold still:** Google Chrome. The candidate image moves 151.0.7922.137 →
156.0.8078.79. Python packages are identical to production's except `anyio` (floats) and `pypdf`
(new). Read any post-deploy rendering change as "merge *or* Chrome".

---

## 2026-08-17: every 429 names the gate that refused (`0.9.2-capacity-gate-2`)

**What changed:**
- Every HTTP 429 now carries `capacity_gate`, one of `render_slots`, `memory`,
  `browser_pool` or `unspecified`. The memory gate also carries `memory_pct`
  (one decimal) and `limit_pct`.
- The change is additive: `failure_class` stays `"capacity"` for all of them,
  so MAS's 429 baseline does not split.
- **`detail` is byte-identical.** MAS has a live regex over
  `memory at N% (limit M%)`.
- **An absent field means an old build.** The field is defaulted at
  serialisation (`envelope_extra_for`), so it covers raise sites we do not own.
- `-2` differs from `0.9.2-capacity-gate` only in comments and a reserved-key
  guard, so the committed tree and the image are the same bytes.

**Why:** three mechanisms raised one exception with an identical envelope. Over
the 175 h sweep, ~94 % of 429s were the pool memory guard, which is benign: a
threshold crossing on a gauge whose median sits above its trip point. Only ~6 %
were RenderGate, the one that means "full". A stop trigger phrased as "429s
above ~4.5 %" was therefore unevaluable.

**There are four 429 sources, not three.**
- The fourth is slowapi. `RateLimitExceeded` subclasses starlette's
  `HTTPException(429)`, `/crawl` carries `@limiter.limit`, and slowapi's handler
  is never registered. An inbound rate-limit breach therefore lands in our
  handler and reports `unspecified`.
- **Asymmetry for MAS:** a render-path 429 sends `Retry-After: 5`; an
  `unspecified` one sends none.
- The `/llm` job quota could also 429, but `per_principal: 0` makes it dead.

**`gate` defaults to `"unspecified"`.** Making it required would raise
`TypeError` inside `get_crawler`, turning a 429 into a 500. Defaulting to
`render_slots` would misattribute any future unlabelled raise.

**Not done:** `/md`, `/html`, `/screenshot`, `/pdf` and `/execute_js` still turn
a pool refusal into a 500. MAS uses none of them.

**Verification:**
- **Live, with the `raw://` burst generator** (zero third-party traffic): 12
  concurrent requests produced 4 × 200 and 8 × 429, all `render_slots`. Both
  RenderGate raise sites fired: queue full at ~1 s and wait timeout at ~14 s.
- **Tests:** `test_mas_contract.py` asserts the serialised body through the real
  exception handler. `test_admission.py` and `test_crawler_pool.py` assert the
  label at the real raise sites. The 245 tests that existed before all passed
  with the change in place, and would have passed with it wrong.
- **Mutation check:** deleting the one-line merge in `server.py` fails 4 of the
  5 contract tests.
- `cold_burst_probe.py` now reports the gate split.

`tasks/done/capacity-gate-in-the-429-envelope.md`.

Closed the same day without code: `tasks/done/fixture-origin-bypasses-the-pinning-proxy.md`.
The gap is real, but every fixture targets an always-up local `http://` origin,
and `test_egress_dns_offload.py` already covers the reachable 80 %.

## 2026-08-14: ACA scale trigger 6 → 12 (infrastructure only, no image)

**What changed:** the scale rule's trigger went from 6 to 12, and `maxReplicas`
from 45 to 20.

**Effect:** the fleet went from ~12 replicas to ~2 on identical traffic, and
efficiency per request rose. Fewer replicas means fewer cold Chromium launches
per company.
- The 12-hour readout is `tasks/done/trigger-12-readout-2026-08-14.md`.
- Its p99 improvement did not survive the full sweep. The full-sweep figures are
  in `tasks/done/post-sweep-closure-2026-08-17.md`: 6.4× lower cost per
  request, in USD.

**Incident:** an `OOMKilled` (exit 137) happened on this config at 2026-08-15
04:30. It self-recovered and lost zero pages.

**Trap:** the readout's "zero OOM kills, ever" is wrong. ACA labels a kill
`OOMKilled` only when it repeats inside the crash-backoff window. Labelled kills
had already happened on the larger fleet from 2026-08-13. Count restarts from
console `supervisord started with pid` lines, not from the label.

Read current values live; do not take them from here.

## 2026-08-09: image `desc` capped at 200 chars (`0.9.2-desc-cap`)

**The defect:** `find_closest_parent_with_useful_text` walks up from an `<img>`
and returns the first ancestor's whole subtree text. On a catalogue grid that is
the whole page, and `add_variant` copies it into every srcset variant.

**Production instance:** `www.thermokon.fi` on 2026-08-08.
- 1,104 of 1,160 media entries carried the same 154,798-char string, so `media`
  was 231,708,619 B, 56× the rest of the result.
- Four requests, each HTTP 200 `success: true` on a ~232 MB payload. Each ran
  216 s on the wire and had streamed 136–146 MB when MAS's client (210 s
  timeout) gave up (Envoy `DC`), so the company was lost deterministically.
- **Nothing logged anything.** Only `ContainerAppHTTPLogs.BytesSent` saw it.

**The fix:** `MEDIA_DESCRIPTION_MAX_CHARS = 200` through upstream's own
`truncate()`.
- `media` dropped to 538,747 B (430×).
- `cleaned_html` and markdown are md5-identical, and all 1,160 entries are kept.
- The win is serialisation (0.655 s → 0.002 s), not scraping (~8 %).

**No contract change.**
- Nothing in this repo reads `desc`, markdown does not come from `media`, and
  MAS verified per-field that they never read `media`.
- Patching the class, rather than injecting a default, also covers a
  client-sent scraping-strategy object.

**Second instance:** `grumblo.com` returned 22.1 MB at 200 and MAS *stored* it.
This is the silent-success case that no instrument on either side counts.

**Still unbounded:** `alt` and `media.tables` (`AITOSOFT_FILES.md` §2). No
response-size bound exists anywhere; `limits.max_body_bytes` bounds the request.

**Test trap:** `test_media_desc_cap.py` uses an absolute byte bound. The first
draft's threshold moved with the constant and could not fail.

`tasks/done/media-desc-duplicates-the-page-per-image.md`.

Closed the same day without code:
- `inference-tier-500s-are-not-retryable.md`. MAS's corpus showed those pages
  returning real content on other days, so marking them dead would have been
  silent loss.
- `base-config-boolean-defaults-never-applied.md`. Superseded by
  `CrawlerRunConfig.set_defaults()`.

## 2026-08-06: our consent JS was deleting customer pages (`0.9.2-consent-guard`)

**The defect:** `remove_consent_popups.js` ended Phase 3 with 20 generic
selectors (18 substring patterns plus `.cc-banner` and `.cc-window`). It called
`el.remove()` on whatever matched, with no guard. The Enfold theme puts
`av-cookies-no-cookie-consent` on `<html>` to mean "consent is off", so we
deleted the document. Playwright then serialises the doctype alone:
`<!DOCTYPE html>`, 15 bytes.

**Four failure shapes.** Two were silent, and invisible to both repos'
archives, because the removal precedes any capture:
- `<html>` removed → 15 B → 500.
- `<body>` removed → head-only → 500.
- An inner element holding content removed → 200, `success: true`, contacts
  gone. Silent.
- A Phase-1 click that navigates → the wrong page, in full, at 200. Silent.

**What changed (files in `AITOSOFT_FILES.md` §1):**
- A structural guard in both snippets.
- The generic selectors now observe instead of removing.
- The overlay snippet's `rgba` clause gets a real alpha test.
- Three log counters.
- **One wire-status change, pre-agreed with MAS:** a capture with no `<body>`
  element is `render_defect` at 200 (terminal). It used to be `render_error` at
  500, retried three times.

**The rule is permanence, not emptiness.**
- Chromium synthesises `<body>` for every document, so its absence means a
  script removed it, and no retry rebuilds it.
- A near-empty but structurally intact capture stays `render_error` at 500,
  because it might paint next time.
- The check keys on the shape, not the byte count; a padded `<head>` puts the
  same defect at 20,087 B.
- Exactly 15 B means a removed `documentElement`. An empty 200 is 39 B, and a
  body that is the literal string is 54 B.

**Proof on the diagnosed host:** `www.kubler.fi` went from 15 B at 500 to 200,
55,545 chars and 5 emails. The Enfold class is still on `<html>`, and the log
reads `CONSENT DECLINED … node=html … structural=True`, so the fix did it, not
the site.

**What the old behaviour cost:** Kübler alone, in segment 1, took 32 navigations
and 196.9 s (20.7 % of the run's render seconds). The first count, 266.5 s /
26.1 %, double-summed nested `[COMPLETE]` lines.

**Reading the counters:**
- `CONSENT DECLINED` carries `chars` and `pagechars`. `pagechars` is
  `body.innerText`, visible text; never compare it with markdown length
  (Kübler: 2,634 against 55,545).
- **Read `node`/`class` first, `chars` second, the ratio last.** A wrapper that
  held contacts measured 9.4 % of its page and a real banner 7.3 %, so the ratio
  does not separate them.
- `CONSENT STRUCTURAL` should never fire. If it does, the 120 named selectors
  have the same defect.
- `CONSENT NAVIGATION` compares full URLs, so fragment-only changes are false
  positives.
- **Query multi-word tokens with `indexof(col, "…") >= 0`, not `contains`.**
  On `_CL` columns `contains` is term-based. It once returned 383 false
  `CONSENT STRUCTURAL` hits.

**Measured outcome:**
- **Segment 2** (2026-08-06, 50 companies, 261 renders): 27 `CONSENT DECLINED`
  on 3 companies, every one `node=html structural=True`. The silent inner channel
  was 0, `CONSENT STRUCTURAL` was 0, and genuine click-navigations were 0.
- **Banner value, from MAS's side:** 95 matched containers held 0 contact data.
- **Full sweep:** `CONSENT STRUCTURAL` was 0 in 186,178 requests.
- **Upstream PR framing:** argue the root collision, not banner data
  (`tasks/file-upstream-prs.md`).

**Click channel:** detected and logged, not fixed. MAS bounds it at 0.046 % of
companies.

**Test traps:**
- `/consent/named-root` (`<body id="cookie-notice">`) is the only fixture that
  only the structural guard can pass. With the generics gone, every other
  root-shaped fixture stays green with the guard reverted.
- The overlay fixture is 280×160 because a full-width hero is removed by the
  legitimate size rule.

`tasks/done/consent-scripts-delete-the-page.md`, `segment-2-counter-readout.md`.

## 2026-08-05: egress path. DNS off the event loop, and a dead domain is not an SSRF refusal (`0.9.2-egress-dns-fix`)

**Contract change:** a domain that does not resolve is now `origin_unreachable`
at HTTP 200, terminal. It was HTTP 400 `URL blocked (SSRF protection)` with no
`failure_class`, because `egress_broker._resolve` mapped `gaierror` onto the
policy refusal. A registry sweep is mostly lapsed domains.
- The change is contained to `api.py`, because `validate_url_destination` is
  shared by seven endpoints whose opaque 400 is correct.
- The streaming path keeps the 400.
- **This is a small DNS oracle**: 200 versus 400 tells "no such name" apart
  from "refused". It is acceptable only behind a fail-closed token with one
  client. Do not port it upstream as-is.

**DNS off the event loop:** every resolve on the crawl path was a blocking
`getaddrinfo` on the single event loop that also serves `/health`, the
RenderGate and every fence.
- The dominant caller is the seed check, which runs on every `/crawl` before
  admission.
- Measured with ACA's own resolver (`ndots:5` plus four search domains) and a
  nameserver that never answers: **22.75 s of frozen loop per resolve**.
- **The fix has two parts, and they are complements:**
  - `asyncio.to_thread` relocates the stall. On its own it is not enough: the
    pool is 8 threads with an unbounded queue, and cancellation does not reclaim
    a thread.
  - `RES_OPTIONS="timeout:2 attempts:2 ndots:1"` is what bounds the stall
    (~4 s). It also cuts happy-path DNS about 5×.
- **`RES_OPTIONS` fails silently**, because glibc ignores options it cannot
  parse. It has never been verified on a replica; `FINDINGS.md` §Egress says
  how.

**Plain-`http://` misattribution:** the proxy answered a failed connect with a
`_BLOCKED` 403, which Chromium renders as the page. Our detector then called it
`origin_blocked` and spent a patchright leg.
- Measured: 403 → `origin_blocked` in 16.1 s, versus closing without a reply →
  `origin_http_error` in 0.5 s.
- A 502 or 504 does not work either: the empty body trips our inference tier.
- The connect budget also went from 30 s to 15 s. Chromium's own 30 s timer had
  always fired first.

**Burned tag:** the first image that day, `0.9.2-egress-dns`, shipped a
`NameError`, which made a dead domain a **500**. It passed 229 offline tests, 54
browser tests, 316 upstream security tests and CI, because every test patched
`resolve_and_pin` or `validate_url_destination`, the layer above the broken
line. **Patch the layer below the one you test** (`socket.getaddrinfo`).

`tasks/done/egress-proxy-blocks-the-event-loop.md`.

## 2026-08-05: `ContainerAppHTTPLogs` enabled (infrastructure only)

The diagnostic setting `aca-http-logs` on environment `aitosoft-aca` covers the
**HTTP category only**. Console and system logs already arrive through the
environment's `appLogsConfiguration`, so **adding those categories here would
double-ingest and double-bill**. This table is the only surface that records a
request the ingress handled without a container (cold start). It has no history
before 2026-08-05. Query guidance is in `AZURE_OPERATIONS.md`.

## 2026-08-02: collapse recovery, `unrenderable_content`, a log line on every failed result (`0.9.2-collapse-recovery`)

**1. Recovery.** When the collapse guard fires, `html2text` re-converts the
same rendered HTML. Measured through the browser at 73 KB:

| shape | markdown | html2text | recovered |
|---|---:|---:|---|
| `unclosed-noscript` | 0 | 1,265 | yes, identical to the healthy control |
| `deep-nesting` | 0 | 1,239 | yes, minus a table separator |
| `unterminated-comment` | 0 | 0 | no |
| `unclosed-script` | 0, and the guard cannot see it | 0 | no |

- **A recovered page goes out as an ordinary success** (`failure_class:
  none`). MAS reads `success` and would discard a failed result's rescue.
- **A recovery must clear both the 500-char floor and the ratio floor.** Without
  the ratio floor, a 599-char rescue of a 41,408-char page goes out green with
  40,809 chars silently lost.
- **Reuse the converter, never static mode's pipeline.**
  `_strip_hidden_decoys()` decomposes every `noscript`, which on the unclosed
  shape is the whole page (1,265 → 0).
- **What happens to the other fields:**
  - `cleaned_html` and `links` stay as the collapsed parse left them; they are
    evidence.
  - The other markdown variants are blanked, so one object cannot contradict
    itself.
- **Logging:** `COLLAPSE RECOVERED` and `RENDER DEFECT` are disjoint tokens.
  `RENDER DEFECT` carries the recovered char count: 0 means empty, non-zero
  means a partial recovery that was declined.

**2. Downloads become `unrenderable_content`** (non-retryable, 200, not an
origin class).
- **Trigger:** one `GetVCard` URL produced every HTTP 500 of MAS's 2026-08-01
  run. Chromium refuses to commit a navigation to a download, so `page.goto`
  raises `Download is starting`.
- **Why not `origin_http_error`:** upstream leaves `status_code` null in this
  case, so that label would lie.
- **`accept_downloads: true` does not help**; it was checked.
- **It arrives as a failed result, not an exception.** `arun` wraps its body
  and returns a failed `CrawlResult`, so `classify_result` decides it.
- **Inline PDF is the exception (corrected 2026-08-09).** Real Chrome renders it
  into a 174-byte viewer shell at 200. Tier-3 inference calls that a block,
  giving `render_error` at 500, retried. Our browser suite missed this because it
  runs `chromium_headless_shell`, which has no PDF viewer (`TESTING.md`). MAS now
  removes PDFs at dispatch.
- **The class does fire.** It recorded 12 events on 8 hosts in the August sweep
  (vCards, attachment PDFs). A claim that it "has never fired" was quoted onward
  and expired within six hours.
- **PDF text extraction regression:** MAS holds April captures with
  11–45 K chars of PDF text. What produced them is **not established**: `pypdf`
  is not in the image, and no crawl path extracts PDF text. One stored April
  row's `render_mode` and first 200 chars would settle it.

**3. `RESULT FAILURE`** is now logged for every failed result. Failed results
were logged nowhere; they were visible only while they produced a 500.
- **Generalisation:** every time the taxonomy moves a class off 5xx, it deletes
  that class's only log line.
- The `api.py` exception gate also asks `http_status_for` now. It had been a
  second status-mapping site, and a `render_timeout` that escaped `arun` went
  out as 500 instead of 504.

**Counting traps that came out of this:**
- **Count failures by `failure_class=`, never by log token.** `RESULT FAILURE`
  (result path) and `ORIGIN FAILURE` / `TERMINAL FAILURE` (exception path) are
  disjoint. A dead domain is refused before admission, on the exception path.
  Counting one token undercounted `origin_unreachable` by 57 %.
- **We cannot count 404s.** A 404 with a styled body renders successfully and
  logs nothing. `failure_class` says whose fault it was; `status_code` says what
  the origin said.
- **One client request is `1 + max_retries` navigations.** MAS sends 1, and
  upstream retries on any exception, not only blocks.

`tasks/done/cleaned-html-collapse-guard.md`, `download-navigation-is-not-a-render-error.md`.

## 2026-08-02: browser cap and LRU eviction (`0.9.2-pool-cap`)

**What changed:**
- **`pool.max_browsers: 6`**, enforced in `get_crawler` by evicting the
  least-recently-used *idle* browser. Before this, nothing bounded live
  browsers: residency tracked the distinct configs seen within the TTL, and
  peaked at 9–10 per replica.
- **`get_crawler` never waits.** `release_crawler` takes the same `LOCK`, so a
  wait deadlocks the pool with no 504, no 429 and no janitor recovery. It evicts
  or refuses (429). Evicted browsers close in a detached, timeout-bounded task,
  because `close()` has no timeout.
- **The memory-adaptive TTL collapse is removed.** It closed browsers exactly
  when memory was tight, which produced 136 launches for a working set of 10–12
  signatures.
- **The `📊 Pool:` line is unconditional** and carries `resident=N/cap`.
- **The memory guard sheds one idle browser, then refuses anyway.**
  - "Evict, re-read, refuse" is not implementable: the close is scheduled on a
    task that cannot run before the re-read.
  - Routing it through `_evict_for_capacity(headroom=1)` would be a no-op below
    the cap.
  - It keeps a memory → browser-count feedback loop, narrower than the TTL's
    (it fires only on refusals, not on a timer). Drop samples around the
    `memory pressure X%` evictions before fitting anything (`FINDINGS.md`
    §Browser pool).
- **`permanent_unused_ttl_sec` went from 600 to 120.** The boot browser is
  unreachable by construction (`AITOSOFT_FILES.md` §2). It held ~140 MB through
  minutes 0–10 of a replica's life, when all nine of MAS's memory refusals
  happened.
- `get_container_memory_percent()` subtracts `inactive_file`. This was later
  shown insufficient; see 2026-08-01 below.

**Why 6:** it rests on cardinality, not memory.
- `user_agent_mode: "random"` is client-settable, and our own client doc
  recommends it. It generates one pool signature per request: 8 configs gave 5
  signatures.
- 6 = 3 × `render_capacity`.

**Measurements:**
- **Per-browser memory:** +142.8 MB on a 1.5 KB page versus +170.0 MB on a
  median real page (236 KB, 17 images). A pooled browser costs the process, not
  the page.
- **Navigating to `about:blank` does not unwind a browser.** Per-browser memory
  is a ratchet set by the heaviest page it ever loaded, so only closing resets
  it. This refuted `pool-browser-retains-last-page.md`.
- **Do not quote `mem% = 59.3 + 2.65 × browsers`** or "the cap would not have
  helped". The fit is disputed on three counts, all biasing toward zero
  (`tasks/done/replica-memory-baseline-unexplained.md`).

**Found, not fixed:** the `monitor_routes.py` self-deadlock.

**Deliberately left out of this image:**
- Flipping the envelope `success` to the aggregate. MAS never reads it on 2xx.
- An "unmarked interstitial" rule. It has no evidence, so inferring one would
  recreate defect B against every small real page.

`tasks/done/pool-residency-unbounded.md`, `render-500-window-2026-07-31.md`.

## 2026-08-01: detector round 3, patchright capture wait, memory guard → 429, collapse guard (`0.9.2-detector-round3`)

**Defect A: padded block pages passed as content.**
- Four hosts served 80,671 B rendering to `403 - Forbidden` at origin status
  **202**, and got `success: true`. Every size gate read `len(html)`.
- **Fix:** the evidence gates moved to visible text, and a new block-notice tier
  was added.
- **Trap:** the task file claimed "the pattern side already works". **No
  pattern matched that body.** The hosts caught at 403 were caught by the status
  fallthrough. Measure which branch fired before believing a diagnosis.
- **The 500-char gate is measured:** the smallest healthy page among 58 stored
  captures has 739 visible chars. It is also the collapse guard's floor.
- **Shopify false positive:** a notice must be in the title or a heading, or
  cover ≥ 50 % of the text. Without that, the Shopify `/pages/access-denied`
  family comes back (247 chars).
- `monidor.com`, a stored real capture (11,515 B, 58 chars of text), was a
  second instance. It added two patterns.

**Defect B: inference reported as the origin blocking us.**
- `is_blocked` returns one verdict for "the origin said so" and "we came back
  with nothing". Four of MAS's 33 `origin_blocked` verdicts were the second kind.
- **The expensive one was `norex.com`.** Its `html` was 15 B: a deleted
  `documentElement`, later traced to our consent JS on 2026-08-06. The
  `Crawl4AI Error: not fully supported` placeholder was what our scraper
  generated from those 15 bytes. Conflating input and output sent four sessions
  to the anti-bot tier.
- **Fix:** `_INFERRED_BLOCK_RE` maps inference to `render_error`. **Discarding
  the reason does not discard the status**:
  - 403/503 still mean blocked.
  - Any other 4xx/5xx becomes `origin_http_error`.
  - No status at all becomes `render_error`.
- **`fodbar.fi` is unchanged by decision.** The origin said 403, so we report
  403.
- **A and B had to ship together.** Without A, B would turn padded blocks that
  tier 3 used to catch into `render_error`.
- **Fixture trap:** `/block/padded-403` served a bare `<div>`, which gives tier 3
  two signals. The real page has `<h1>`+`<p>`, which gives one. A fix validated
  on the old fixture closes none of the real hosts. Both shapes are now served.

**Patchright retry capture wait.** The retry used to get the identical
`CrawlerRunConfig`, so it could never resolve a challenge the first attempt had
outlasted.
- It now gets `crawler.retry_capture_wait_s` (10.0), clamped so it never lowers
  a client's value.
- **Measured:** a wait `W` resolves challenges up to `W + 1.22 s`, and the retry
  leg is `W + 1.22` to within 0.04 s.
- **Never raise the global `delay_before_return_html` instead.** That costs
  about 267 render-hours per MAS sweep.

**Memory guard → 429.** All nine 500s in MAS's 2026-07-31 probe were the pool
guard raising `MemoryError`. MAS retries a 500 three times, so memory pressure
quadrupled its own load. The guard now raises `RenderCapacityExceeded`, giving
429 + `Retry-After`. This is a symptom fix.
- **Superseded understanding (2026-08-15):** the guard reads the cgroup
  figure minus `inactive_file`, which still includes *active* page cache. The 85
  % threshold sits near the signal's median, so refusals are threshold crossings,
  not pressure.
- A real OOM can still happen between samples at ordinary readings.
- Do not treat a change in the refusal rate as a change in the system
  (`tasks/done/memory-guard-charges-reclaimable-page-cache.md`).

**Collapse guard, shipped in the same image.**
- **Detection:** it compares visible-text chars in the rendered HTML with
  markdown chars out. It flags a collapse at ≥ 500 visible chars when markdown is
  < 500 chars (it returns early at `produced >= 500`) and the ratio is ≤ 0.10.
  The thresholds come from 37 stored real captures: the lowest ratio among the
  31 healthy content pages is 1.311, and the other 6 (5 cookie-wall/JS shells and
  1 challenge page) had nothing to lose.
- **An HTML-byte ratio was rejected.** It fires on healthy pages: a 73 KB
  healthy control has the same 0.0036 ratio as a collapsed page. It is also
  blind to `unterminated-comment`, whose `cleaned_html` keeps the content.
- **Whitespace is normalised first.** Raw counting reads a challenge page as 506
  chars instead of 58.
- **The root cause is not solved.** Four markup shapes lose the body by three
  mechanisms, enumerated padded at 73 KB. `deep-nesting` is harmless at 1.5 KB
  and fatal at 73 KB. `unclosed-script` is a known blind spot.
- **One class, one wire status.** Both render modes now go through
  `server._crawl_response`, because static mode had served `render_error` at 200
  while full mode served it at 500. `NON_RETRYABLE_CLASSES` added the missing
  axis, permanence. `bad_request` is in it, so a static-mode SSRF refusal is not
  retried.
- **The healthy fixture control had to grow.** It rendered ~140 markdown chars,
  under MAS's own 500 floor, and is now 1,227.

`tasks/done/detector-round3-evidence-vs-inference.md`, `cleaned-html-collapse-guard.md`.

## 2026-07-31: local fixture origin (test only)

`test-aitosoft/fixture_origin.py` is a threaded HTTP server with one route per
failure class. Delay, size, status, visible-text length and markup shape are all
parameters. The `production_path` fixture drives it through `aitosoft_entry` →
`api.handle_crawl_request` → a real pool browser.

**Why:** every failure class since April had been diagnosed against a
customer's site, from one shared SNAT address. "This host blocks datacentre IPs"
and "this host blocked us because of what we did" could not be told apart.

**How it keeps SSRF safe:** `loopback_allowed()` flips the two egress flags only
inside a `with` block. Setting `CRAWL4AI_ALLOW_INTERNAL_URLS` instead would
silently disarm `test_static_mode.py`'s SSRF assertions in the same process.

**First find:** an *unclosed* `<noscript>` still swallows the whole body. The
offline test reported it fixed because libxml2 auto-closes the element; Chromium
instead serialises the rest of the document inside it. Only a browser in the
loop shows this. `conftest.py` also stops pytest collecting the four live CLI
scripts.

`tasks/done/fixture-origin.md`.

## 2026-07-30: failure classification, final-hop block detection, bounded render calls, `<noscript>`, challenge tier (`0.9.2-failure-class`)

Two rounds that shipped as one image. Evidence base:
`tasks/waa-eval-2026-07-30-forensics.md`.

**Block detection judged the wrong redirect hop.**
- `status_code` is the first hop by upstream design (#660 → PR #1435). The body
  is from the last hop. `is_blocked` was fed the 3xx, so every redirect-then-block
  site came back `success: true` with the block page as content.
- Live example: `konecranes.com` returned 301 → 403 Varnish.
- **Fix:** `effective_status()` at all three call sites. It is strictly
  additive, because no status rule matches a 3xx. PR #2112.
- **Shipped alone, this would have made things worse.** The blocked result then
  hit upstream's "all failed → 500" rule, and our security handler genericised
  the 500 and stripped `redirected_status_code`.

**`failure_class`: an origin failure is never our 5xx.** This was MAS's Q2,
answered (a).

| Reality | Wire |
|---|---|
| origin 4xx/5xx, edge block, DNS/TCP/TLS failure | 200, result `success:false`, `origin_http_error` / `origin_blocked` / `origin_unreachable` |
| our render broke | 500 `render_error` |
| our fence fired | 504 `render_timeout` |
| replica full | 429 `capacity` |

- **`failure_class` is on every result**, successes as `"none"`. A missing field
  means an old build.
- **`status_code` in the API response is now the final hop.** `CrawlResult`
  keeps upstream's semantics, so the rewrite happens at serialisation in
  `api.py`. `redirected_status_code` stays as it was.
- **Classification bias:** anything unrecognised is `render_error`, ours and
  retryable, never an origin class. Being wrong that way is loud and costs
  renders. Being wrong the other way silently tells MAS a healthy site is broken.
- **An empty 5xx body is `origin_http_error`, not `origin_blocked`.** 503 stays
  a block, because Incapsula and Varnish serve blocks with it.
- **The monitor used to record success for every request.** It now records the
  outcome the client actually sees.

**`status_code` 202 is not a success signal** (added 2026-08-01). 36 of 243
re-scraped hosts returned 202, all from the challenge families. The same 202
carried interstitials, block pages, real content and empty bodies. Branch on
`success` and `failure_class`, never on the status.

**Render calls that no timeout covered.**
- `page.content()`, `page.evaluate()` and `page.close()` are sent with no
  protocol timeout. They wait on an execution-context promise that every
  navigation replaces.
- **Observed:** 172 s of silence, then a 504 at the 180 s fence.
- **Fixes:**
  - `bounded_evaluate` (30 s).
  - Optional DOM steps (10 s).
  - `_capture_html` settle-and-retry (15 s per attempt, 25 s total).
  - `page.close()` (10 s).
  - A shared `total_timeout` (100 s via `config.yml`, server-side only).
  - All of this is PR #2113.
- **Measured:** the navigation-race shape (`maitokolmio.fi`) went from a 504 at
  180 s to 200 with full content in 5.0 s. A permanently wedged page went from a
  silent 504 to a 500 at 94 s with the reason logged.

**Nested `<noscript>` swallowed the page.** `strip_noscript()` before parse.
- `kiertopakkaus.fi`: 312,628 B of HTML became 97 B of `cleaned_html` and 1 B of
  markdown, at `success: true`. MAS found 406 pages on 70 hosts, identical 3½
  months apart.
- Static mode was never affected, because `_strip_hidden_decoys` drops
  `noscript`.
- PR #2114.

**Challenge tier.** MAS scanned 117,323 stored pages with our patterns: 22 hits,
only 2 genuine.
- The dominant family (371 pages) was not in the list, so its literals became
  tier 1.
- **`Checking your browser` had never been evaluated on the pages it was written
  for.** Tier 2 only runs on 4xx/5xx, and interstitials arrive at 200.
- **Fix:** a challenge tier at any status, gated on visible text.
- **The visible-text gate has a test behind it:** a 40-paragraph Finnish article
  about bot protection is 8.2 KB.
- **`Access Denied` was tightened** to title or heading context.

`tasks/done/origin-vs-crawler-failure-classification.md`,
`redirect-status-blinds-block-detection.md`, `render-retry-unbounded-hang.md`,
`noscript-collapses-body-to-empty-markdown.md`, `antibot-detector-challenge-blindspot.md`.

## 2026-07-17: fence-504 observability (`0.9.2-fence-obs`)

Logging only.
- **`WALL-CLOCK FENCE 504: url=… deadline_s=… elapsed_s=… gate=…`** (logger
  `api`). Before this, the July eval had 3 fence 504s with zero log lines.
- **`RenderGate ADMIT url=… waited=… in_use=…/… queued=…`** on every grant.
  `RenderGate REJECT` lines are byte-identical to before, because playbook
  queries grep them.
- **Silent nav retries: no patch.** Upstream already logs every retry
  (`Anti-bot retry n/max`). The eval's zero-log wedges were therefore single
  indefinite hangs. That was confirmed 2026-07-30 as the untimed
  `evaluate` / `content` calls.

`tasks/done/504-fence-observability-2026-07-17.md`.

## 2026-07-17: pool cleanup and patchright tidy (`0.9.2-pool-cleanup`)

- **`crawler_pool.py` rebuilt from upstream bytes** with only the real changes
  re-applied, which removed a dead overflow scan.
- **The PERMANENT browser is re-created lazily** after the janitor force-closes
  it. Before this, one stuck slot degraded all default-config traffic until
  restart.
- **Patchright:**
  - An explicit in-flight counter replaces peeking at `Semaphore._value`.
  - A recycle race is closed: the singleton is dereferenced inside the
    semaphore.
  - The patchright fallback runs on its own fixed persona, deliberately.

`tasks/done/crawler-pool-cleanup-2026-07-17.md`, `patchright-fallback-tidy-2026-07-17.md`.

## 2026-07-17: single-URL `/crawl` contract, server-enforced

`len(urls) > 1` returns 400 *"multi-URL requests not supported: MAS contract is
single-URL per request"*. The check runs before seed validation, before the
static branch and before admission, and covers `/crawl/job`. `/crawl/stream` is
not guarded.

**MAS's commitment (2026-07-17):** "We commit to single-URL /crawl requests
long-term — enforce it at the boundary." Their client sends `urls: [url]` and
reads `results[0]`.

**Why:** RenderGate clamps weight to capacity. A multi-URL request could
therefore render above the 2-renders-per-replica invariant at
`GLOBAL_SEM` concurrency.

`tasks/done/render-gate-batch-coherence-2026-07-17.md`.

## 2026-07-17: static mode SSRF hardening (`0.9.2-static-hardening`)

- **The security gap:** static mode followed redirects with no per-hop check, so
  a public page 302-ing to `169.254.169.254` would have been fetched and
  returned.
- **Redirects are now manual** (≤ 5 hops), each validated with
  `egress_broker.check_redirect`, the same rule full mode uses. A refusal is an
  inner `success:false` with an opaque message, inside a 200 envelope.
- **Also:**
  - Fan-out is bounded (`Semaphore(10)`).
  - The timeout moved to `crawler.static_fetch_timeout_s`.
  - The monitor records 502 when every URL fails.

`tasks/done/static-mode-hardening-2026-07-17.md`.

## 2026-07-17: render admission (RenderGate) (`0.9.2-render-gate`)

**The incident (2026-07-16):** `kynnos.fi/yritys/` returned a 504 at exactly
180 s under only 4–6 concurrent renders.
- One replica served the whole burst, launched 7 Chromium browsers on 2 vCPU,
  and stalled.
- Upstream's limits (`GLOBAL_SEM`, the per-browser page cap) both wait silently
  *inside* the fence.
- Memory was not a factor (67 % peak).

**What changed:** `aitosoft_admission.py`.
- **Limits:** at most `render_capacity` (2) concurrent full renders per replica,
  a queue of 4 and at most 15 s of waiting, then 429 + `Retry-After: 5`.
- **Placement:** the gate is acquired before browser acquisition and before the
  fence, so the 180 s budget starts at dequeue. Static mode bypasses it.

**Capacity benchmark** (2-CPU-pinned Chromium): N=2 costs +7 % p50 over N=1,
N=4 +22 % (p95 +43 %), and N=6 +44 % (p95 2×).

**Superseded on the scale rule:** this change also set the ACA scale trigger
equal to `render_capacity`. That is a category error. The trigger is neither a
concurrency nor, despite Microsoft's documented definition, a request rate: the
scaler reads Envoy upstream request *and connection* counts, which grow with the
replica count (`AZURE_OPERATIONS.md` §3.1–3.2). The trigger is set independently
since 2026-08-08.

**Budget trap:** 15 s of queue + 180 s of fence fits under the 240 s ingress
limit only on a warm replica. A cold start (up to 65 s observed) can make the
margin negative, although MAS's 210 s client timeout fires first.

`tasks/done/capacity-scaling-redesign-2026-07-17.md`.

## 2026-07-16: upstream v0.9.2 merged

117 upstream commits (v0.8.6 → v0.9.2). The dominant theme is a secure-by-default
Docker server: fail-closed auth, the untrusted-config boundary, SSRF egress
pinning and declarative-only hooks.

**Merge method:** the 2026-04 whitespace commit (`055d4ce`) had reformatted ~90
upstream files into an 11.5k-line phantom diff. This merge took upstream's tree
wholesale and re-applied only our real patches, and pre-commit has been scoped
to our files since. Procedure: `AITOSOFT_FILES.md` §5.

**Patches:**
- **Dropped:** the stealth 2.x port, `api.py`'s `wait_for` timeout, and
  `simple_token_auth.py`. `AITOSOFT_FILES.md` §4 lists what replaced them.
- **New file:** `aitosoft_static_mode.py`, moved out of `api.py`.

**Trust relaxations for our client:** `browser_config.headers` is allowed and
the `page_timeout` clamp is 180 s. The current boundary is in
`AITOSOFT_FILES.md`.
- **Trap:** this entry's original MAS notice said `magic`, `simulate_user` and
  `override_navigator` would 400. **They are accepted**, and a falsy forbidden
  field is dropped. `js_code` and proxy fields still 400 when truthy.

**Other client-visible changes at the time:**
- Unknown fields are silently dropped.
- `/docs`, `/metrics` and `/playground` need the token.
- The 504 body is plain `"Crawl exceeded the time limit"`.
- (A dead domain became an SSRF 400 here; since 2026-08-05 it is
  `origin_unreachable` at 200.)

**Deployment notes:**
- The image `CMD` is now `entrypoint.sh`. Set `GUNICORN_BIND=0.0.0.0:11235` on
  the Container App.
- `/app` is read-only at runtime.
- Upstream added a per-replica `GLOBAL_SEM` of `pool.max_pages` (5).

**Broken-cert sites still crawl in full mode.** The reason is not the
context-level `ignore_https_errors`, and not a regression from
`enforce_egress`; both earlier explanations were wrong. Upstream hardcoded
`--ignore-certificate-errors` into every Chromium launch, which disables
validation process-wide. Upstream removed that flag in v0.9.5 (`f0ada4c`), so
it must be decided at the next merge (`AITOSOFT_FILES.md` §5).
`tasks/done/tls-broken-cert-regression-2026-07-17.md`.

`tasks/done/upgrade-v0.9.2.md`, `merge-upstream-develop.md`.

## 2026-04-15: static mode, `render_mode: "static"` (`0.8.6-static-mode`)

**Why:** `roadscanners.com` hung Playwright at the DevTools-protocol level for
the full fence, with zero crawl4ai log lines, while plain HTTP fetched it fine.

**What changed:**
- **`render_mode: "static"`** is an opt-in that fetches with httpx and converts
  with the vendored `html2text`. No browser, pool or patchright retry is
  involved.
- **`_strip_hidden_decoys()`** removes `script`, `style`, `noscript` and
  `template`, inline-hidden nodes, and the classes `oe_displaynone`, `d-none`
  and `is-hidden`. Odoo hides a `null` span inside emails. It deliberately keeps
  `sr-only` and `visually-hidden`. If a site reports missing contacts in static
  mode, check this pass first.
- **Every result carries `render_mode`**, in both modes.
- **MAS pivots a host to static after two consecutive 504s.**
- Redirect handling and failure mapping changed later; see 2026-07-17 and
  2026-08-01.

`tasks/done/static-html-fallback-mode-2026-04-15.md`.

## 2026-04-14: request timeout and stuck-slot leak (`0.8.6-leak-fix`)

**The incident:** two bot-protected sites hung requests beyond the 240 s
ingress limit. FastAPI does not cancel the backend coroutine on client
disconnect, so `release_crawler` never ran. `active_requests` leaked, the
janitor skipped the "busy" browser, and overflow browsers piled up.

**Fixes:**
- **A 180 s `asyncio.wait_for` around `arun` plus patchright.** Since v0.9.2,
  upstream's `limits.wall_clock_s` does this.
- **`BUSY_SINCE` with a janitor force-close after 600 s.** Still carried.
- **The patchright singleton is bounded** (semaphore 5, recycled every 100
  uses).
- **`batch-scale.sh` pins `minReplicas` around batches.** It has been an
  emergency valve only since RenderGate.
- **Added files:** `setup-memory-alert.sh` and `test_soak.py`.

`tasks/done/leak-fixes-deploy-2026-04-14.md`.

## 2026-04-14: pool `max_pages` enforced (`0.8.6-maxpages-fix`)

**The incident:** `max_pages: 5` was never enforced, so one browser reached 44
active pages on 2 vCPU and starved.

**Fix:** `get_crawler` now opens an overflow browser (`<sig>_ovf_N`) when a
browser is full.

## 2026-04-14: wrapper entry point and upstream security merge (`0.8.6-security-v2`)

**Wrapper:** `aitosoft_entry.py` replaced the patches in upstream files. It
calls `BrowserConfig.set_defaults(**config.yml kwargs)`, so every request
inherits stealth, channel, UA and viewport. `aitosoft_browser_merge.py` and the
`server.py` auth patch were removed.

**Upstream merge:** 8 commits, including two CVSS 9.8 fixes (AST sandbox
escape, `eval()` in computed fields).

## 2026-04-11: stealth package and patchright fallback (`0.8.6-stealth-v4`, then v5)

**The trigger:** MAS saw consistent 500s on four Cloudflare, Akamai and WAF
sites that answered `curl` fine. The fingerprint diagnostic
(`test_fingerprint.py`) found a stale UA, no WebGL (`--disable-gpu`), wrong
locale and timezone, and stealth patches that never applied.

**What changed:**
- Real Chrome in the image (`playwright install chrome`), for its TLS/JA3
  fingerprint.
- GPU flags gated on `enable_stealth` in `browser_manager.py`. PR #2085, still
  carried.
- config.yml browser kwargs: stealth on, `chrome` channel, 1920×1080, current
  Windows UA, `text_mode: false`.
- `--disable-gpu`, `--disable-software-rasterizer` and `--disable-web-security`
  removed from the launch flags.
- `test-aitosoft/reference/persona_generator.ts`, a deterministic per-company
  persona for MAS.

**Result:**
- The fingerprint now matches real Chrome. `test-aitosoft/stealth-v4/` holds the
  artefacts.
- **The four sites stayed blocked.** Two different engines got identical
  blocks, so the blocks are IP-based, not fingerprint-based.

**Patchright fallback (v5).** `aitosoft_patchright_fallback.py` retries
detector-blocked results once through undetected-chromium, inside the request.
If the retry also fails, the first-tier diagnostic is kept. Residential proxies
were deferred.

**Superseded within days:** the `aitosoft_browser_merge.py` helper and its
`api.py` hooks (replaced by the 2026-04-14 wrapper), and the stealth 2.x import
port (upstream #1960).

`tasks/done/stealth-package.md`.

## 2026-04-04: resource scaling

Requests waited 8+ minutes for CPU while each crawl took under 10 s:
1 vCPU / 2 GiB was running 40 concurrent pages. The fix was 2 vCPU / 4 GiB per
replica, `max_pages` 40 → 5, the memory threshold 95 → 85 %, and horizontal
scaling. 2 vCPU / 4 GiB is this environment's maximum (`AZURE_OPERATIONS.md`).

## 2026-03-26: upstream v0.8.6 merged

197 upstream commits (v0.8.0 → v0.8.6).
- **Security:** the `litellm` supply-chain compromise was replaced by
  `unclecode-litellm`, and Redis CVE-2025-49844 was fixed.
- **New upstream features:** `remove_consent_popups` (0.8.5), anti-bot retry
  with `max_retries`, `flatten_shadow_dom`, `fallback_fetch_function`.

**Trap:** this entry originally recommended that MAS send
`remove_overlay_elements=True` and credited `remove_consent_popups` with fixing
accountor.com. **`remove_overlay_elements` deletes page content and must not be
recommended**: its `rgba` clause was always true. The accountor attribution is
unsupported by the stored captures; see `FINDINGS.md` §Consent and overlay scripts.

## 2026-01: fork set up, first production deployment (`0.8.0-secure`)

- **The fork:** dev container, `CLAUDE.md` and this log.
- **The deployment:** Azure Container Apps in West Europe, co-located with MAS
  in the existing `aitosoft-prod` resource group.
- **Auth:** a 39-line `simple_token_auth.py`, because upstream's JWT gave a
  token to anyone. It was replaced by upstream `AuthGateMiddleware` in v0.9.2.
- **Upstream v0.8.0 security fixes:** hook builtins RCE, and `file://` /
  `javascript:` LFI.
- Most of this period's deployment toolchain is gone. `d284593` (2026-07-17)
  deleted 13 `azure-deployment/` files (the token, JWT and North-Europe deploy
  scripts and their docs), two pre-fork docs and a January scratch directory;
  `batch-scale.sh` and `setup-memory-alert.sh` survive, as do `CLAUDE.md` and
  this log.
