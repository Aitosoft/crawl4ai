# Aitosoft Changes Log

This file tracks all modifications made to the crawl4ai fork for Aitosoft's internal use.
Keeping this log helps when syncing with upstream updates.

---

## Current State

**Last Updated**: 2026-08-09

> **BUILT AND UNDEPLOYED, 2026-08-09: the image `desc` cap.** One page returned
> **232 MB four times** at HTTP 200 `success: true` with no log line anywhere;
> an image's `desc` was an ancestor's whole subtree text, copied per image and
> per srcset variant. Capped at 200 chars: `media` 231,708,619 → **538,747 B
> (430×)**, `cleaned_html` and markdown **byte-identical**, every entry kept.
> Suite 312 green. **Held only for a deploy window** — MAS is running an
> ~18,000-company sweep and Tero decides when it goes out; MAS themselves say
> the change is invisible to them and can land any time. The section below is
> the full account, including what it does **not** bound.
>
> **Two task files closed the same day without code:**
> `inference-tier-500s-are-not-retryable.md` **closed unfixed** — MAS's corpus
> refutes its premise (`www.ktth.fi` returned 14,542 chars on 2026-04-17; the
> `laatutrio.fi` apex paths 21,234 and 14,564 on 2026-08-08), so marking those
> pages permanently dead would have been silent data loss on live sites. Its four
> surviving findings were rehomed, not lost.
> `base-config-boolean-defaults-never-applied.md` **closed** — its proposed fix
> is obsolete because `CrawlerRunConfig.set_defaults()` exists.
>
> **One correction to this file's own record, and it is the dangerous direction:**
> the claim that an inline `application/pdf` behaves exactly like a
> `Content-Disposition: attachment` download is **false in production**. Real
> Chrome renders it into a 174-byte viewer shell at HTTP 200 which tier-3
> inference calls a block. Re-measured on both browser arms 2026-08-09: 4 of 5
> download kinds identical, `pdf-inline` alone diverges. **`unrenderable_content`
> has therefore fired zero times in production, ever.** See the 2026-08-02 §2
> entry below, which is corrected in place.
>
> **Deployed 2026-08-06: `0.9.2-consent-guard` (revision `--0000037`).** Our own
> consent JS was deleting customer pages; the fix, its three counters, and
> `render_defect` at 200 for a deleted root. **One wire-status change**: a
> capture with no `<body>` is now `render_defect` at HTTP 200 (terminal) instead
> of `render_error` at 500 (retried 3x). Pre-agreed with MAS
> (`19-…` §1, `21-…` §1). Proof on the diagnosed host, the smoke, and how to
> read the counter: the 2026-08-06 section below.
>
> **MAS's segment 2 RAN on 2026-08-06 (13:46–14:36 UTC) and is fully read** —
> `tasks/done/segment-2-counter-readout.md`. 50 companies, 61 domains, **274
> requests / 261 render admissions**, and the two repos reconcile
> request-by-request. **No code change came out of it.** Headlines: 27 declined
> root removals on 3 companies (12.9 % of stored pages) that were 15-byte
> captures at 500 on the prior image; the silent inner channel **0**;
> `CONSENT STRUCTURAL` **0**; genuine click-navigations **0**; 0 fence-504 /
> janitor / memory refusal / collapse-guard fire, the **fourth** consecutive
> clean workload. **All 12 of the run's 500s came from two URLs**, neither a real
> render failure — that plus the patchright-retry waste are the only open items
> (`tasks/README.md` 6–8), and both are cost, not data loss. Recap sent as
> `tmp/mas-repo-messages/28-…`, which also corrects a shared premise: MAS's
> `--concurrency 2` bounds **companies, not renders** (peak 7 in flight), and
> **their flag is free up to ~15** against our fleet ceiling (60 then, **90** since `maxReplicas` 30 → 45 on 2026-08-08).
>
> **Deployed 2026-08-05: `0.9.2-egress-dns-fix`.** The egress-path work —
> blocking DNS off the event loop, `RES_OPTIONS`, and two misattributions. It
> carries **one wire-status change**: a domain that does not resolve is now
> `origin_unreachable` at HTTP 200 instead of an SSRF 400. MAS was told in
> `tmp/mas-repo-messages/16-to-mas-a-dead-domain-was-never-an-ssrf-refusal.md`.
>
> **The `-fix` suffix is not cosmetic.** The first deploy that day
> (`0.9.2-egress-dns`, revision `--0000035`) shipped a `NameError` that made a
> dead domain a **500** — worse than the 400 it replaced. Every test suite and
> CI passed it, because every test patched the layer above the broken line.
> Caught by the first live probe after deploy, ~8 minutes of exposure, no MAS
> traffic in the window. Full account, including why nothing caught it:
> `tasks/done/egress-proxy-blocks-the-event-loop.md`.
>
> **2026-08-05, infrastructure only — no image, no code.**
> `ContainerAppHTTPLogs` is now enabled: diagnostic setting **`aca-http-logs`**
> on the managed environment `aitosoft-aca`, **HTTP category only**. Console and
> system logs already arrive via the environment's `appLogsConfiguration`, so
> adding those categories here would double-ingest and double-bill — do not
> "complete" the setting by adding them.
>
> Why: it is the only surface that can record a request the ACA ingress
> terminated *before* a container existed. Until now that was a pure absence —
> there were no diagnostic settings at all on the app or the environment, and the
> platform `Requests` metric demonstrably under-records exactly the cold-start
> window (2026-07-30: one crawl served at 08:14:56, zero metric datapoints
> 08:13–08:19). It answers an outstanding MAS question.
>
> Cost: ~13,400 ingress requests/month across `crawl4ai-service` +
> `aitosoft-edge`, workspace is PerGB2018 at 30-day retention → ~0.02 GB/month.
> With MAS's projected ~120,000 sweep fetches it stays near $0.50/month.
> **It has no history** — it describes 2026-08-05 forward only.
>
> **The ACA ingress timeout is 240 s and is not configurable on this app.** The
> knob is `properties.ingressConfiguration.requestIdleTimeout` on the
> *environment*, and it requires premium ingress, which requires workload
> profiles. `aitosoft-aca` is `workloadProfiles: null` — so this sits behind the
> *same* environment migration as the 4 GiB ceiling, not a separate one. There is
> no app-level timeout property at any API version through `2026-03-02-preview`.
> It is an **idle** timeout; we stream nothing until the end, so for our traffic
> idle == elapsed.
>
> **There is no replica resize to be had.** Azure caps this app at **2 vCPU /
> 4 GiB**, which is what it already runs — the environment is a *legacy
> Consumption-only* managed environment. The April note's `--memory 8.0Gi` was
> never a valid command and `4 vCPU / 8 GiB` belongs to a different environment
> type. Measured 2026-08-02; see `tasks/README.md`. Do not plan against headroom
> we cannot buy.

### Version
- **Local**: v0.9.2 (upstream/develop 2026-07-16) + Aitosoft patches (see entries below). **`main` is one behaviour change ahead of production** — the image `desc` cap, committed and undeployed (2026-08-09). No image has been built or pushed for it, so do not go looking for a tag. It is the *only* undeployed behaviour change — the consent-JS work went out as `--0000037`
- **Production**: the above + collapse recovery + `unrenderable_content` + a log line on every failed result + the egress-path work + **the consent-JS guard and its counters** (deployed 2026-08-06)
- **Docker Image**: `aitosoftacr.azurecr.io/crawl4ai-service:0.9.2-consent-guard` (revision `crawl4ai-service--0000037`, deployed 2026-08-06, digest `sha256:4ad6e11634a5c14b07faac9ba434cef73ff120a89f579b80ecf4be37f325c215`)
- **Previous**: `0.9.2-egress-dns-fix` (revision `--0000036`, deployed 2026-08-05) — the rollback target. Before that, `0.9.2-collapse-recovery` (revision `--0000034`, digest `sha256:70cd89720a1b546f62690d0da99a9485ef1f5649ee34b85650b0a91b1c52de3d`). **Revision `--0000035` (`0.9.2-egress-dns`) is a burned tag** — it shipped a `NameError` and lasted 8 minutes; do not roll back to it.
- **Prod smoke 2026-08-05 (egress-dns-fix)**: health 200 (0.20 s) ✅, unauthenticated POST /crawl → 401 ✅, render-capacity invariant ✅, revision `--0000036` **Running at 100 % with `--0000035` Deprovisioning — checked before the crawl** ✅. **Tier 1 regression 4/4** ✅.
  **The check that was worth running, and it is now a habit:** a crawl of a *lapsed* domain — HTTP 200, `success:false`, `failure_class: origin_unreachable`, `"DNS: host does not resolve"`, 0.23 s. It exercises the whole egress path and **contacts no third party**, because the name does not resolve. It is also what caught the `NameError` in `--0000035` eight minutes after that deploy, when four green test suites and a green CI run had not.
  **The negative check matters as much:** `169.254.169.254` and `127.0.0.1:8080` both still return 400 `URL blocked (SSRF protection)`. The change moved *only* "there is no address at all" out of that bucket; the security verdict is untouched.
- **Prod smoke 2026-08-02 (collapse-recovery)**: health 200 ✅ (8.0 s cold start from zero), unauthenticated POST /crawl → 401 ✅, render-capacity invariant `render_capacity=2` == `http-renders` rule ✅ (`deploy-image.sh` exit 0), revision `--0000034` **`Running` at 100 % with `--0000033` Deprovisioning — checked before the crawl**, per the 2026-07-30 mid-cutover lesson ✅. **Tier 1 regression 4/4** (`--version collapse-recovery`) ✅.
  **The check that was actually worth running:** zero `RENDER DEFECT`, zero `COLLAPSE RECOVERED`, zero `RESULT FAILURE` across the four live pages. The guard's evidence is 37 stored captures of exactly these hosts, so a Tier 1 run is a genuine test that the corpus still describes the live sites — and the recovery path, which can now *rewrite* a result's markdown, stayed entirely out of the way on real customer pages. Had it fired, the instruction was to treat it as a finding, not to tune the threshold.
  **Found while verifying, not by a failure:** `test-aitosoft/artifacts/` is gitignored, so the 140 captures those thresholds are asserted against exist only on this machine and three offline tests fail on a fresh clone. Our only pre-deploy gate is machine-dependent. `tasks/guard-corpus-is-not-in-the-repo.md`.
- **Prod smoke 2026-08-02 (pool-cap)**: health 200 ✅ (33 s cold start from zero), unauthenticated POST /crawl → 401 ✅, render-capacity invariant `render_capacity=2` == `http-renders` rule ✅ (`deploy-image.sh` exit 0), revision `--0000033` at 100 % traffic with `--0000032` ScaledToZero — **checked before the crawl**, per the 2026-07-30 mid-cutover lesson ✅. **Tier 1 regression 4/4** (`--version pool-cap`) ✅. Pool instrumentation live: `📊 Pool: hot=0, cold=1, permanent=yes, resident=2/6, mem=13.3%, anon=585MB file=328MB inactive_file=43MB`.
  **Worth more than the smoke it came from:** that line is a *serving* replica reading **13.3 %**, not the ~65 % the disputed regression predicts for 2 browsers. It does not refute the intercept (Tier 1 is 4 sequential requests; the 68 disputed samples were a 243-host probe at concurrency) — but it does show the baseline is **not** a constant that "appears with traffic". It needs *concurrent* traffic, which points at candidate 1 (in-render transient memory) in `replica-memory-baseline-unexplained.md` and away from candidates 3 and 4.
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
- **`pytest test-aitosoft/` = 312 tests, ~260 s, all offline, zero live requests** (the four live CLI scripts are no longer collected; see `test-aitosoft/conftest.py`)
- Pure-function subset: **245 tests, ~30 s** (`--ignore=test-aitosoft/test_fixture_origin.py`)
- Browser-driven subset: test_fixture_origin.py (67), against a local fixture origin, ~215 s
- **The browser-driven subset has never run production's browser, and no CI
  workflow runs `test-aitosoft/` at all.** `browser_manager.py:1123-1128` drops
  `channel` whenever `chrome_channel == "chromium"` (a Windows workaround applied
  everywhere), so Playwright launches `chromium_headless_shell`. Found 2026-08-09
  when an inline-PDF claim turned out to be true only on the shell. Not a
  hypothetical: it is why five download tests pass while exercising the wrong
  arm. TESTING.md's arm64 section carries the detail and the two possible fixes
- **The fence test's flake is FIXED (2026-08-06)** after being diagnosed rather
  than tolerated. It had reached 1 failure in 10 full runs. Measured: the fence
  fires at 1.00 s and the request returns at 1.04-1.07 s, so **unwind costs
  0.05 s** — which refutes the reading that would have made it a product finding
  (a fence slow to cancel would eat the 60 s between our 180 s fence and the
  240 s ingress limit). The variance is entirely outside the fence: a healthy
  `/ok` control ran median 1.33 s, **max 4.05 s**, the outlier a cold browser
  launch. Fixed by `FENCE_STALL_S = 8`, which widens the gap between fence and
  origin rather than the assertion's meaning, and costs the suite nothing.
  `tasks/done/flaky-fence-test-margin.md`.

---

## One page produced a 232 MB response, four times, at HTTP 200 `success: true` (2026-08-09)

**Built, tested, and held for a deploy window — MAS is running an ~18,000-company
sweep and Tero greenlights the deploy.** MAS's own instruction is that the change
is invisible to them and can land any time, including mid-sweep; we are not
deploying into it anyway.

### What changed

One constant and one call, in a file we already patch:

```python
# crawl4ai/content_scraping_strategy.py
MEDIA_DESCRIPTION_MAX_CHARS = 200
...
# in find_closest_parent_with_useful_text()
return truncate(current.text_content().strip(), MEDIA_DESCRIPTION_MAX_CHARS)
```

`truncate()` is **upstream's own helper** (`utils.py:3004`, literally
`value[:threshold] + '...'`) and 200 is **upstream's own constant** for bounding
an over-long value (`preprocess_html_for_schema(attr_value_threshold=200)`). So
the patch adds no idiom of ours, and what we ship is what we would PR.

### The defect

`find_closest_parent_with_useful_text` walks **up** from an `<img>` until an
ancestor has enough words, then returns **that ancestor's entire subtree text**.
Image containers hold no words of their own, so on a product-catalogue grid the
walk passes every one of them and stops at whichever container also holds the
page prose. `add_variant` then copies that string into every srcset/`<picture>`
variant, so the payload is O(variants × page_text).

`https://www.thermokon.fi`, four requests on 2026-08-08:

| | |
|---|---|
| media entries | **1,160** (= 580 distinct images × 2.0 fan-out) |
| distinct `desc` strings | 19 |
| entries carrying the *same* 154,798-char string | **1,104** |
| `media` as JSON | **231,708,619 B** — 56× everything else in the result combined |
| on the wire | 137, 136, 145, 146 MB, HTTP 200, `success: true`, `failure_class` absent |
| outcome | 216 s each, Envoy `DC` — MAS's 210 s per-attempt client timeout fired |

**Nothing logged anything.** `[COMPLETE] ✓`, no `RESULT FAILURE`, no
`failure_class`, no collapse-guard fire. The only surface that recorded it is
`ContainerAppHTTPLogs.BytesSent`, which nothing read until 2026-08-09.

### Measured effect

Re-derived independently against the stored render, and against 78 stored
captures in `test-aitosoft/artifacts/`:

| | baseline | shipped |
|---|---:|---:|
| `media` JSON | 231,708,619 | **538,747 (430×)** |
| media entries kept | 1,160 | **1,160** |
| `cleaned_html` | 989,759 | **identical (md5)** |
| markdown | 761,365 | **identical (md5)** |
| `json.dumps(media)` | 0.655 s | **0.002 s** |
| `scrap()` | 1.485 s | 1.366 s (~8 %, p = 0.0014 over 9 interleaved reps) |

**The win is serialization, not scraping.** The walk still builds each
ancestor's `text_content()` before the slice, so do not repeat the earlier
"the cap makes scraping faster" framing — it was a single timing inside its own
noise, and the 330× is somewhere else.

### Why it is safe, verified from both sides and not from the summary

- **Nothing in this repo reads `desc`.** Exhaustive search of the dict-key and
  attribute forms across all Python: written at `content_scraping_strategy.py`
  and at `utils.py:1330` (a legacy scraper whose only in-tree caller is a
  **commented-out line**, `crawl4ai/legacy/web_crawler.py:232`), declared once as
  `MediaItem.desc`. **Zero readers.** Nothing in `deploy/` reads `.media` at all.
- **Markdown does not come from `media`** — `generate_markdown` takes
  `input_html`, and image `score` is computed *before* `desc` exists.
- **MAS never reads `media`**, per-field, verified by grep across their tree
  (`tmp/mas-repo-messages/40-…` §1). They take `markdown`, `cleaned_html`,
  `html`, `title`, `links` and the redirect URL.
- **No test asserted on it** — `test_mas_contract.py` contains literally zero
  `media`/`desc`/`image` references, and upstream's own tests assert only
  `src`/`alt`/`type`/`score`. The pre-existing 306 offline tests passed unchanged.
- **The cap covers every client-reachable path.** `scraping_strategy` is on the
  untrusted allowlist, but `UNTRUSTED_ALLOWED_TYPES` holds exactly two scraping
  strategies — `LXMLWebScrapingStrategy` (patched) and `PDFContentScrapingStrategy`.
  Patching the **class** shuts the hole; an injected default would have been
  replaceable by a client-sent strategy object. That is what decided (a1) over
  the `CrawlerRunConfig.set_defaults()` route.
- **`desc` is documented to MAS as "a snippet of nearby text or a short
  description (optional)"** (`c4ai-doc-context.md:3565`, served by `/ask`), and
  the doc's own example value is already elided. A 200-char cap contradicts no
  promise this repo has made.

### n ≥ 2, and the second one succeeded

`grumblo.com` returned **22.1 MB at HTTP 200 with `ResponseFlags = -`** on
2026-08-09 — i.e. MAS stored it. The task file listed it as "consistent with,
not proven". Settled with **one plain `httpx` GET** (no crawler, dev-container
egress, recorded in `TEST_SITES_REGISTRY.md`): on the **static** HTML alone, 272
images carry **1,524,174 chars of `desc` — 88 % of a 1,732,603-byte `media`
payload** — 60 of them sharing one 24,293-char string. Cap → 107,772 B, 16×,
`cleaned_html` byte-identical. The rendered DOM production saw is necessarily
larger.

**That is the case neither side counts:** thermokon failed loudly and grumblo
succeeded, so MAS has been storing multi-megabyte payloads that no instrument on
either side flags.

### What this does NOT fix, stated because it is easy to overclaim

The cap bounds **`desc`**, not a media entry, and the response body is still
unbounded:

- **`alt`** is copied into every variant by the same `add_variant` — one `<img>`
  with a 50,000-char `alt` and 5 srcset entries gives 300,879 B of media from a
  50,244 B document. Linear in the document.
- **`media.tables` is worse and is on by default.** `table_extraction.py` does
  `row_data.extend([text] * colspan)` with `colspan = int(cell.get("colspan", 1))`,
  unvalidated. `<th colspan="50000">` on a **4,624-byte** page yields
  **4,504,226 B** of `media`; `colspan="2000000"` leaves the wire unchanged but
  costs **+91 MB RSS from 905 bytes of HTML in 0.12 s**; `colspan="auto"` makes
  `int()` raise and the table vanishes at `success: true`.

**Neither is being built.** Both need pathological markup, no production instance
has ever been seen, and the `desc` bug fired on ordinary catalogue HTML. The
response-size guard (`tasks/done/media-desc-…` §3c) is therefore **parked, not
unnecessary** — `limits.max_body_bytes` bounds the *request*, and nothing
anywhere bounds a response.

### Tests

`test-aitosoft/test_media_desc_cap.py`, 6 tests, offline, 1.2 s. Suite is now
**312** (was 306). The uncapped arm is produced by raising the constant, so both
arms run the real production code path.

The one that matters is `test_the_cap_changes_only_desc`: it asserts
`cleaned_html` and `links` are byte-identical between arms, no image is dropped,
and every non-`desc` field is unchanged — the safety argument in executable form.
`test_the_variant_fanout_cannot_re_multiply_the_string` deliberately uses an
**absolute** byte bound rather than a multiple of the constant, because the first
draft of this suite had a threshold that moved with the value it was testing and
therefore could not fail when the truncation was removed (found by reverting the
constant and watching only 2 of 6 tests go red).

### What the implementing session found wrong in the task file

The diagnosis survived to the byte. Eight peripheral things did not, and three
are worth carrying: **the walk never reaches `<html>`** in 78 real captures (lxml
leaves `html.text` `None`, so the conjunction cannot fire there); **the
pathological corpus population was undercounted** (19 of 78 captures, 12 jpond
*plus 7 accountor*, not 12 of 68); and **the file's own cap ladder mixes two
units** (images-only vs whole-`media`, a 54-byte delta). Also: the `"..."` marker
costs 3 bytes per entry, so the shipped figure is 538,747 / 430× and not the
535,435 / 433× a bare slice gives — the code comment said the wrong one until it
was re-measured. Full list in
`tasks/done/media-desc-duplicates-the-page-per-image.md`.

---

## Our own consent JS deleted customer pages (2026-08-06)

**DEPLOYED 2026-08-06 as `0.9.2-consent-guard`, revision `--0000037`**, digest
`sha256:4ad6e11634a5c14b07faac9ba434cef73ff120a89f579b80ecf4be37f325c215`.
Tier 1 4/4 pre-deploy; prod smoke below. One wire-status change; see "The
contract change". MAS's segment 2 (50 companies) is unblocked —
`tmp/mas-repo-messages/22-…` needs relaying.

### The proof, in production, on the host it was diagnosed from

`www.kubler.fi` — the confirmed Enfold host, **15 bytes at HTTP 500** before
this image, 8 requests / 32 navigations / 266 s in segment 1:

```
HTTP 200  success=true  failure_class=none  html=314,807 B  markdown=55,545 chars
5 contact emails (jani-pekka.rulamo@, jukka.mustakallio@, jussi.siira@,
kimmo.kuusinen@, kubler@)  ·  2 phone numbers  ·  4.6 s
```

**And it was our fix that did it, not the site changing under us** — which is
the check worth insisting on, because "it works now" is not evidence of why.
Three independent confirmations:

1. `av-cookies-no-cookie-consent` **is still on `<html>`** in the live capture
   (item 25 of 39 in the class list, which is why it is easy to miss in a
   truncated dump).
2. The production log line, verbatim:

```
CONSENT DECLINED: requested=https://www.kubler.fi url=https://kubler.fi/ n=1
chars=2634 pagechars=2634 selector=[class*="cookie-consent" i] node=html id=
class=html_stretched responsive av-preloader-disabled … structural=True
```

3. `structural=True`, `node=html`, `chars == pagechars` — the selector matched
   the document root and 100 % of the page's text. That is the deletion, caught
   at the point of removal instead of after it.

The line also earns its two design decisions in one shot: **the requested URL
differs from the current one** (`www.kubler.fi` → `kubler.fi/`, an ordinary
redirect, but the join key MAS asked for in `21-…` §6 would have been lost
otherwise), and **the selector survived intact** — on the rich console it would
have rendered as the empty string.

**A unit warning, from the same line.** `pagechars` is
`document.body.innerText`: **rendered visible text**, no link URLs, no hidden or
collapsed content. It is *not* markdown length and must never be compared with
one. Kübler reads `pagechars=2634` against `markdown=55,545` — and 48,673 of
those markdown characters are `[text](url)` constructs. Same trap the collapse
guard's docs already warn about (visible-text chars in vs markdown chars out are
different units); it now applies to this counter too.

`crawl4ai/js_snippet/remove_consent_popups.js` — which MAS sends on **every**
request — ended with 20 generic selectors (18 substring patterns + `.cc-banner`/`.cc-window`) (`[class*="cookie-consent"
i]` and friends) and called `el.remove()` on whatever they matched, with no
guard on *what*. The Enfold WordPress theme writes `av-cookies-no-cookie-consent`
onto `<html>` to mean **cookie consent is switched off on this site**, so we
matched a flag asserting there is no banner and deleted the document.
`page.content()` then serializes the doctype alone: `<!DOCTYPE html>`, 15 bytes.

Four failure shapes, and **two of them were silent** — a green 200 with data
missing, invisible to both repos by construction, because the element is removed
*before* the capture either side stores. Full evidence:
`tasks/done/consent-scripts-delete-the-page.md`.

### What changed

| file | change |
|---|---|
| `crawl4ai/js_snippet/remove_consent_popups.js` | **Structural guard** — `documentElement`, `body` and `head` are never removed, whatever matched them (Phases 3 and 4). **The 20 generic selectors no longer remove anything**: they are a separate list that is *observed* and reported. Phase 5's `document.body.style` accesses are null-guarded. The snippet now **returns a report** |
| `crawl4ai/js_snippet/remove_overlay_elements.js` | Same structural guard. `backgroundColor.includes("rgba")` replaced with a real alpha test — see below. Null-guarded `document.body` |
| `crawl4ai/async_crawler_strategy.py` | `remove_consent_popups(page, url)` takes the *requested* URL, reads the snippet's report, and logs it (`_report_consent_pass`). Detects a self-inflicted click-navigation by comparing `page.url` across the pass. The animation wait moved out of the `try` |
| `deploy/docker/aitosoft_failure_class.py` | A capture with **no `<body>` element** is `render_defect` (200, terminal), not `render_error` (500, retried 3×) |
| `test-aitosoft/fixture_origin.py` | `/consent/{shape}` + `/consent/elsewhere`, and `consent_reports()` |

### The three counters, and why they are worth an image on their own

Neither repo's archive can size this retrospectively — MAS's "0 of 193 pages
carry `av-cookies-*`" is not weak evidence, it is *the only possible result*.
So the fix ships with the instrument:

```
CONSENT DECLINED    a generic selector matched something we no longer remove.
                    chars/pagechars is the whole question: a 200-character match
                    was a banner and removing it was right; a match holding a
                    large share of the page was never a banner, and removing it
                    is what silently cost MAS contact blocks
CONSENT STRUCTURAL  a *named* vendor selector matched <html>/<body>/<head>.
                    Should never fire. If it does, the named list has the same
                    defect the generic list had
CONSENT NAVIGATION  our own Phase-1 click moved the page. Everything captured
                    after it belongs to a URL nobody asked for
```

Non-overlapping tokens, none a substring of another — the same reason
`COLLAPSE RECOVERED` and `RENDER DEFECT` are split. Every line carries the
**requested** URL beside the current one, which is the join key MAS reconciles on
(`tmp/mas-repo-messages/21-…` §6) and which is no longer `page.url` once a click
has navigated.

**They go out through the stdlib `logging` module, not `self.logger`** — the one
place this change deviates from the surrounding upstream file's idiom, and it is
deliberate. `AsyncLogger` renders through a rich console, which fails a counter
three ways, all measured rather than assumed:

- It prints only `if self.verbose or force_verbose`, and `verbose` comes from
  `BrowserConfig` — which is in the untrusted-config allow-list. A client
  sending `browser_config: {"verbose": false}` would silence the counter.
- It **wraps at the console width**. These lines run past 190 characters, so
  each one would arrive in the container log as *two* records, and a query for
  `chars=` and `class=` on the same record would silently lose rows.
- It **eats brackets**: `AsyncLogger._log` escapes the message template
  (`"[" → "[["`) but inserts param values raw, and `[[` is not an escape in rich
  — it renders as `[]`. An unescaped `[class*="cookie-notice" i]` reached the
  console as **the empty string**, deleting the most diagnostic field in the
  line.

`COLLAPSE RECOVERED`, `RENDER DEFECT` and `RESULT FAILURE` already use this
channel (`api.py`), so this is the one the existing Log Analytics queries target
rather than a new one. **A segment runs once**, and a counter that can read zero
for four different reasons is not a counter.

### The click channel is detected and NOT fixed, deliberately

Phase 1 clicks 86 named CMP buttons, 12 generic attribute selectors, a
text-content regex over every button and link, a shadow-DOM pass and an iframe
pass. Two of those five were measured selecting ordinary site furniture —
`accept-terms-btn`, `<a role="button">Got it!</a>` — whose default action is a
navigation, after which we capture a **different page, in full, at 200**.

We log it. We do not re-navigate. MAS's archive bounds this channel at **0.046 %
of companies**, which makes measuring it proportionate and rebuilding navigation
state disproportionate. `test_a_self_inflicted_click_navigation_is_detected`
asserts today's defect on purpose, the same way the padded-block tests did.

Detection is in **Python, not the snippet**: a click that navigates destroys the
JS execution context, so the snippet's own `location.href` comparison would never
run and its return value would never arrive. `page.url` survives that, and it is
the *consequence*, so it covers all five click surfaces including the two the
fixture does not reproduce.

### `remove_overlay_elements`: the size clause was a no-op for years

`getComputedStyle(el).backgroundColor` is the literal string `rgba(0, 0, 0, 0)`
for every element with a transparent background — the default. So
`backgroundColor.includes("rgba")` was **true for essentially every element**,
the whole size-and-appearance clause was dead, and the rule degenerated to
"remove every visible fixed-or-absolute element". Now tests the actual alpha
(`0 < a < 1`, i.e. a translucent scrim, which is the clause's evident intent).

MAS sends `false`, so this is not on the critical path — it is in this image
because it is the same defect family and the same upstream PR. **Still do not
recommend the flag.**

### The contract change

A capture whose document root is gone was `render_error` at **HTTP 500**, which
MAS retries three times. Four attempts × four navigations under the patchright
tier = **16 navigations for a URL that will do exactly the same thing every
time.** Kübler paid it twice over in segment 1: 32 navigations, 266 s, **26.1 %
of the whole run's render seconds** for 1 company of 25.

It is now `render_defect` — ours, **permanent**, HTTP 200, `success: false`,
already in `NON_RETRYABLE_CLASSES`. Pre-agreed with MAS
(`tmp/mas-repo-messages/19-…` §1, `21-…` §1), so it does not need announcing
before it ships, but it is a wire-status change and gets the usual care.

**The line that must survive:** permanence, not emptiness.

| shape | verdict | why |
|---|---|---|
| no `<body>` element in the capture | `render_defect`, 200 | Chromium synthesises `<body>` for every document it parses, so its absence means a script removed it. No retry rebuilds a deleted root |
| near-empty but structurally intact | stays `render_error`, 500 | a JS shell that painted nothing this time may paint next time |

Keyed on the **shape**, not on the byte count — a padded `<head>` puts the same
defect at 20,087 bytes. 15 bytes is still diagnostic when reading a log line: an
empty 200 serializes to **39** and a body that *is* the string `<!DOCTYPE html>`
to **54**, so exactly 15 is a removed `documentElement` and nothing else.

`render_defect`'s docstring said "our parse lost the body"; it is now "the body
is gone and we are the reason". Widened on purpose — it keys on the shape of the
damage, which is what makes it survive the next mechanism. This is the third
distinct thing to produce a body-shaped hole (the `<noscript>` family, the four
markup shapes in `cleaned-html-collapse-guard.md`, now our own JS).

### What the implementing session found wrong in the task files

Three things, all small — the diagnosis itself reproduced exactly:

1. **The task file proposed dropping the 20 generic selectors. Dropping them
   silently would have thrown away the measurement the whole plan depends on.**
   Step 5 of the cross-repo plan branches on "declined-removal counter fires
   often / ~never", and a deleted selector cannot decline anything. They are kept
   and evaluated, removal-free — one `querySelectorAll` pass we were already
   doing — which also answers MAS's third A/B arm from our own logs.
2. **The structural guard and the generic drop were indistinguishable in test.**
   With the generics gone, the Enfold class matches nothing, so every
   `<html>`/`<body>` fixture would pass with the guard reverted. Added the
   `named-root` shape (`<body id="cookie-notice">`, one of the *120 named*
   selectors) so the guard has a test only it can pass.
3. **The overlay fixture had to be small.** A full-width absolutely-positioned
   hero is removed by that script's *size* rule, which is legitimate — it would
   have proved nothing about the `rgba` fix. The route serves a 280×160 opaque
   box, which only the degenerate clause could ever have removed.

Not wrong, but worth recording: `classify_error_text` never sees `html`, so the
root-gone check lives in `classify_result` and is **below** both origin branches.
A root that vanished on a page the origin refused is still the origin's verdict
to give; inverting that order would start reporting 403s as our own defect.

### Tests

- `test-aitosoft/test_fixture_origin.py` — 12 new browser-driven tests over
  `/consent/{shape}`: the four destructive shapes survive; the counter reports
  `chars`/`pagechars`; the structural guard names the element it saved; a real
  banner surviving costs noise and not content; both click surfaces are detected;
  the overlay flag no longer removes an opaque element.
- `test-aitosoft/test_failure_classification.py` — 8 new: a deleted root is
  permanent and an empty page is not, a missing capture is not a deleted root,
  the origin still outranks the shape, the wire status is 200.
- The `norex.com` row in `MAS_DEFECT_B_CASES` now carries its real 15-byte
  capture and expects `render_defect`. Its old label — "our own
  `Crawl4AI Error:` placeholder in 15 bytes of HTML" — conflated two fields
  (`html` is bare doctype; the placeholder is what our scraper *generated from*
  it) and is the sentence that sent four sessions to the anti-bot tier instead of
  to our own DOM cleanup.

### What the pre-deploy run actually measured

**Tier 1, 4/4, one pass, four live requests** (`--version consent-guard-local`,
local server on arm64/Chromium). Then the counters were read out of the same
server's stdout — no extra traffic, because the gate run *is* the experiment.

**Zero `CONSENT DECLINED` across all four sites, and the zero is real.** Verified
rather than assumed: `api` and `aitosoft_admission` INFO lines were present in
the same log, and the counter was then proved end-to-end by crawling the local
`/consent/*` fixtures through the running server (below). This is the first live
evidence for "the generic selectors do no work" beyond the 7-host corpus — and
the strongest single case is **`accountor.com`, a real Cookiebot wall, which
produced zero generic matches**: the named selectors did all of it. That is
exactly the claim the fix rests on.

**End-to-end through the real server, zero live traffic** (fixture origin +
`CRAWL4AI_ALLOW_INTERNAL_URLS`), all four at HTTP 200 / `success: true` /
`failure_class: "none"` with the contacts present:

```
/consent/html        n=1 chars=1168 pagechars=1168  node=html   structural=True
                     selector=[class*="cookie-consent" i] class=html_stretched av-cookies-no-cookie-consent …
/consent/inner       n=1 chars=1168 pagechars=12368 node=footer structural=False
                     selector=[class*="cookie-notice" i] class=site-footer cookie-notice-footer
/consent/banner      n=1 chars=92   pagechars=1261  node=div    structural=False
                     selector=[class*="cookie-notice" i] class=cookie-notice-bar
/consent/named-root  CONSENT STRUCTURAL selector=#cookie-notice node=body  (+ a generic decline)
```

`/consent/html` was 15 bytes at HTTP 500 before this image; 1,568 bytes at 200
after. `/consent/named-root` is the one only the structural guard saves.

**One thing to carry into reading segment 2, because it corrects an assumption
in the task file.** The ratio does **not** cleanly separate the two cases:
`inner` (a wrapper that also held the contacts) is 9.4 % of its page and
`banner` (a correct removal we are now skipping) is 7.3 %. What separates them
here is **absolute `chars`** (1,168 vs 92) and, more tellingly, **`node`** — a
`<footer>`/`<section>`/`<main>` match is a page region, a
`<div class="cookie-notice-bar">` is a banner. Read `node` and `class` first,
`chars` second, the ratio last. And do not expect the counter to classify
individual hits: its job is to size the population, and only the *content* of
the removed element decides whether a removal would have been loss.

### Prod smoke 2026-08-06 (consent-guard)

Taken **after** `--0000037` reached 100 % with `--0000036` Deprovisioning, per
the 2026-07-30 mid-cutover lesson.

| check | result |
|---|---|
| `/health` | 200 in 0.17 s ✅ |
| unauthenticated `POST /crawl` | 401 ✅ |
| render-capacity invariant | `render_capacity=2` == `http-renders` rule ✅ |
| SSRF negatives (`169.254.169.254`, `127.0.0.1:8080`) | both 400 ✅ — the change touched nothing here |
| lapsed domain (the `NameError` canary from 08-05) | 200, `origin_unreachable`, `DNS: host does not resolve`, 0.15 s ✅ |
| `caverna.fi` — clean control | 200, `success: true`, `none`, 532 chars, 4.4 s ✅ |
| **`www.kubler.fi`** | **200, `success: true`, `none`, 55,545 chars, 5 emails** ✅ |

**Two live third-party requests for the whole deploy**, and both were the ones
that could not be answered any other way: `caverna.fi` proves the *built image*
renders through real Chrome (the pre-deploy Tier 1 ran on arm64/Chromium, so
the engine was genuinely untested), and `kubler.fi` proves the fix on the host
it was diagnosed from. `kubler.fi` is on the burned list as of this session.

Incidental but useful: the capture's `<html>` carries `avia-chrome-138`, i.e.
the deployed amd64 image really is driving **Chrome 138**, not bundled Chromium.
That is the one thing a local Tier 1 run structurally cannot check.

**A `Traceback` in the post-deploy log window is expected here, and it is not a
regression.** The lapsed-domain probe raises `OriginUnresolvable` from
`api._normalize_and_validate_seeds`, which is *caught* and turned into
`origin_unreachable` at HTTP 200 — the 2026-08-05 design. The stack is logged on
the way through, so a `Traceback` / `NameError` sweep after any deploy will hit
it. Check the client's wire status, not the presence of a stack: this one paired
with `ORIGIN FAILURE … failure_class=origin_unreachable` and a clean 200.

The whole smoke ran on a **scale-from-zero replica** — container up at 07:55:39,
first request served 07:55:57 — with `RenderGate` waits at 0.0 s and memory
146 → 157 MB against an 85 % guard.

### Two of our own numbers corrected on 2026-08-06, both by counting twice

1. **The generic container list is 20, not 18** — 18 substring patterns plus
   `.cc-banner` and `.cc-window`, which are the same kind of guess with a shorter
   name. Named containers are **120, not 122**. The 140 total was right; only the
   split was wrong, and it was wrong in every file we had written.
2. **Kübler's segment-1 cost was 196.9 s / 20.7 %, not 266.5 s / 26.1 %.** We
   summed all sixteen `[COMPLETE]` lines; eight of those are the first Playwright
   leg **nested inside** the same request's total — the double-`[COMPLETE]`
   behaviour we had documented ourselves in `tmp/mas-repo-messages/14-…` and then
   failed to apply to our own arithmetic. Measured both sides of the ratio the
   same way; the priority it set is unchanged, it was over-stated by a quarter.

**The 32 navigations figure does NOT move** and was never inflated by the
`max_retries` docs error: it is a count of `[FETCH]` lines, and the 16
`Anti-bot retry 1/1` lines in the same window confirm `max_retries: 1` on the
wire. At 2 it would have been 48.

Both errors were summing the wrong rows, not measuring the wrong thing. Neither
was caught by review; both were caught by counting a second time.

### To check first in segment 2

1. **`CONSENT DECLINED` rate, and `node`/`class` on each.** A `<footer>` /
   `<section>` / `<main>` match is a page region and points at the silent
   channel; a `<div class="cookie-notice-bar">` is a banner and is a removal we
   are now correctly skipping. Read `node` and `class` before `chars`, and
   `chars` before the ratio — see the ratio caveat above.
2. **`CONSENT STRUCTURAL` should appear never**, other than on Enfold-shaped
   hosts where the *generic* pass reports `structural=True`. A line naming one
   of the **120** named vendor selectors means that list has the same defect the
   generic one had, and it wants looking at immediately rather than at the end
   of the segment. **Segment 2 result: zero, across 261 renders** — the named
   list holds. (This line said 122 until 2026-08-06, contradicting the
   correction 26 lines above it. Counted by tokenizing the arrays: **86 + 12**
   accept selectors, **120 named + 20 generic** containers = 140. Naive quote
   regexes get this wrong because the selectors contain embedded quotes, e.g.
   `'[class*="cookie-consent" i]'`.)
3. `RESULT FAILURE … failure_class=render_defect` at **200**, not 500. If it
   fires at all after this image, a mechanism nobody has identified is still
   deleting documents — that is a new investigation, not a tuning exercise.
4. `origin_blocked` **per segment**. A rate that climbs segment over segment is
   IP-reputation decay and should stop the sweep. Segment 1's baseline was 0.

---

## The egress path: blocking DNS, and two misattributions (2026-08-05)

**Committed, NOT deployed.** One change alters a wire status, and this repo's
rule is that behaviour changes wait for the relay (additive ones ship and get
announced). Everything here is in `main`; production is still
`0.9.2-collapse-recovery`.

Full record, including the ten things the task file got wrong:
`tasks/done/egress-proxy-blocks-the-event-loop.md`.

### What changed

| File | Change | Ours or upstream |
|---|---|---|
| `api.py` | Seed SSRF check awaited off the loop; a host with **no address at all** now raises `OriginUnresolvable` → `origin_unreachable` at HTTP 200 instead of an SSRF 400. Streaming path keeps the 400 | ours |
| `egress_proxy.py` | Both `resolve_and_pin` calls awaited off the loop; connect budget 30 s → 15 s as `DEFAULT_CONNECT_TIMEOUT_S` + ctor arg; **`http://` connect failure now closes instead of replying `_BLOCKED`** | **upstream file** |
| `egress_broker.py` | `_resolve` docstring only — it is blocking and callers on a loop must offload it | **upstream file** |
| `aitosoft_static_mode.py` | Redirect `check_redirect` awaited off the loop | ours |
| `aitosoft_failure_class.py` | `OriginUnresolvable` + `classify_exception` mapping | ours |
| `supervisord.conf` | `RES_OPTIONS="timeout:2 attempts:2 ndots:1"` on the gunicorn program | ours |

`egress_proxy.py` and `egress_broker.py` were **byte-identical to
`upstream/develop`** before this — introduced by upstream `60886d1`. So this is
a new merge surface and a fifth upstream PR candidate, and
`.github/workflows/security.yml` runs upstream's 37 tests over them on push to
`main`. All 316 upstream security tests pass.

### Why

Every DNS resolution on the crawl path ran as a bare blocking
`socket.getaddrinfo` on the app's **single** event loop (`gunicorn --workers 1`,
uvicorn worker) — the loop that also serves `/health` (ACA readiness **and**
startup probe), the render-admission gate and every wall-clock fence. The
dominant call site is the seed check on **every** `/crawl`, which runs *before*
render admission and is therefore not bounded by render capacity.

Measured against the running replica's own resolver config (`ndots:5` + four
search domains, read off a live replica) with a nameserver that receives and
never answers: **22.75 s of frozen loop per resolve, 8 UDP queries**.
`RES_OPTIONS` takes that to ~4 s and removes 4 speculative NXDOMAIN lookups per
resolve on the **happy** path too — a page render performs 10–40 uncached
resolves. The two fixes are complements, not alternatives: `asyncio.to_thread`
relocates the stall into an 8-thread pool whose queue is unbounded and whose
threads are **not** reclaimed by cancellation; `RES_OPTIONS` is what bounds it.

### The contract change, and it is the one to announce

A lapsed domain used to reach MAS as **HTTP 400
`URL blocked (SSRF protection): URL blocked`, with no `failure_class`** —
`egress_broker._resolve` mapped `socket.gaierror` onto the same `EgressBlocked`
as a policy refusal. It is cheap (0.078 s, no render slot), so this was a
labelling defect, not a cost one. But a company-registry sweep is *mostly*
lapsed domains, and it is the `norex.com` inversion again: our own policy string
blaming a customer's domain.

Now: **HTTP 200, `success:false`, `failure_class: "origin_unreachable"`,
terminal, non-retryable** — which is what `ORIGIN_UNREACHABLE`'s own definition
("DNS / TCP / TLS never got there") always claimed.

Contained to `api.py` on purpose: `validate_url_destination` is shared by seven
other endpoints whose opaque 400 is correct, and `validate_webhook_url` funnels
into `except ValueError` handlers that would have become 500s. Only the failure
path re-asks whether the host has any address; the happy path still resolves
once. **This is a small DNS oracle** (200 vs 400 distinguishes "no such name"
from "refused") — acceptable only because the API is fail-closed behind a token
with one trusted consumer, and it must not be ported upstream as-is.

### The `http://` misattribution

On the absolute-URI path a proxy reply is an *ordinary response* Chromium
renders as the page — so replying `_BLOCKED` handed the browser a 403 whose body
is our own string `URL blocked`, which our own antibot detector then read as the
customer's site blocking us: `origin_blocked`, plus a wasted patchright retry.
Measured against a closed local port: **403 → `origin_blocked` in 16.1 s** vs
**close → `origin_http_error` in 0.5 s**. A 502/504 does *not* work — an empty
body trips our own inference tier and the retry fires anyway.

`_BLOCKED` stays on the policy branch and on the CONNECT path, which was already
correct (Chromium turns a non-200 CONNECT reply into
`ERR_TUNNEL_CONNECTION_FAILED` and never renders it → `origin_unreachable`).

### Tests

`test-aitosoft/test_egress_dns_offload.py` — 12 hermetic tests, 2.5 s, no
network, no browser. **The three behavioural ones were verified to fail against
the pre-change code.** Gates: 229 offline + 54 browser-driven + 316 upstream
security, all green.

### To check first after deploy

`RES_OPTIONS` is the one change that cannot be tested from here, and its failure
mode is **silence** — glibc ignores options it cannot parse, so a mangled value
looks exactly like the old behaviour. Confirm it arrived
(`az containerapp exec … --command "cat /proc/1/environ"`).

---

## Collapse recovery + `unrenderable_content` (2026-08-02)

Two independent items in one image, both small, both worth having in before a
heavier MAS sweep — every page recovered during a sweep is a page nobody has to
re-crawl afterwards.

### 1. A detected collapse is now recovered, not just reported

The guard shipped 2026-08-01 detects a capture whose body vanished in our parse.
Detecting it does not return the data. It now takes a **second opinion**: the
same rendered `html`, re-converted with `crawl4ai.html2text` — the converter
`aitosoft_static_mode` already serves to MAS. Measured through the browser at
73 KB, and **re-derived independently before shipping** (it reproduces to the
character, including the byte-identical 1,265):

| shape | markdown today | html2text over the same html | recovered? |
|---|---:|---:|---|
| `unclosed-noscript` | 0 | **1,265** | yes — byte-identical to the healthy control's own html2text output |
| `deep-nesting` | 0 | **1,239** | yes — content complete; the markdown table loses its `\| --- \|` separator |
| `unterminated-comment` | 0 | 0 | no |
| `unclosed-script` | 0 (guard-blind) | 0 | no |
| *healthy control* | 1,258 | 1,265 | — |

A recovered capture goes out as an **ordinary success** carrying the recovered
markdown (`failure_class: none`). Option B — `success: false` with the recovery
attached — buys nothing: MAS's client reads `success` and would discard exactly
what we rescued. Both are HTTP 200, so **no retry behaviour changes**; this is
additive from their side. `render_defect` now means what it says: *we lost the
body and could not get it back.*

Three things worth carrying forward, because two of them were nearly shipped
wrong:

- **Recovery reuses static mode's CONVERTER, never its pipeline.**
  `_fetch_static_one` calls `_strip_hidden_decoys()` first, which `decompose()`s
  every `noscript` — and on an unclosed `<noscript>` Chromium has re-serialized
  the whole document *inside* that element, so BeautifulSoup deletes the page.
  Measured 1,265 → 0. It reproduces `strip_noscript()`'s failure by a different
  route. Pinned by `test_recovery_must_not_reuse_static_modes_pipeline`. The cost
  of skipping it: hidden-decoy email obfuscation (the roadscanners.com
  `oe_displaynone` class) is not stripped from recovered markdown. On a page that
  would otherwise return nothing, that is the right trade.
- **A recovery must clear BOTH the degenerate floor and the ratio floor.** The
  first draft accepted on MAS's `DEGENERATE_CAPTURE_CHARS = 500` alone, arguing
  that recovery should treat its output exactly as the normal path would. Review
  refuted it by measurement: a page with 41,408 characters of visible text
  recovering **599** would go out green (599 > 500) and lose 40,809 characters
  silently — a *new* silent-loss channel inside the fix for silent loss. The two
  paths are not symmetric: here the guard has **already proved** the collapse.
  No new constant; every genuine recovery measured sits 10–28× above the ratio
  floor.
- **A partial recovery is not attached.** On a failed result the markdown is
  evidence — what our parse produced — and MAS reads `success` and stops. The
  character count goes in the log line instead, where it is the diagnosis.

**New log token, deliberately disjoint from the old one:** `COLLAPSE RECOVERED`
is *not* a substring of `RENDER DEFECT`, so the recovered and lost populations
stay countable apart across images. The 2026-08-01 baseline of 2.7 % of pages /
18 % of hosts is now the **sum** of the two. `RENDER DEFECT` also carries the
recovered char count: 0 means html2text agreed the page was empty, non-zero means
a partial recovery we declined — a third case nobody has seen yet.

**What it does not fix:** `cleaned_html` and `links` on a recovered result are
left as the collapsed parse produced them — deliberately, they are the evidence
and they explain the recovery rather than contradicting it. The other markdown
variants (`fit_markdown`, `markdown_with_citations`, `references_markdown`) are
**blanked**, not left: review caught `markdown_with_citations` still holding the
collapsed parse's one character next to 1,266 characters of recovered
`raw_markdown` — one object, contradicting itself, every signal green. That is
this module's own failure shape one field to the left. Empty says "we did not
produce one"; anything else lies.

**Honest sizing:** recovery is measured on **fixtures**. Which mechanism the 9
production URLs hit is still unknown, so the real-traffic yield is somewhere in
0–9 of 9. The reason to ship it is that it is a free **mechanism classifier**;
the yield is then a measurement rather than a claim.

### 2. A URL that downloads is `unrenderable_content`, at 200

One `GetVCard` endpoint produced every HTTP 500 of MAS's 2026-08-01 run.
Chromium refuses to commit a navigation to a download, `page.goto` raises, the
text matched nothing in the taxonomy, and `render_error` at 500 bought three
retries of a URL that will do the same thing forever.

`unrenderable_content` — non-retryable, HTTP 200, and deliberately **not** an
origin class. `origin_http_error` was the cheaper option and was rejected:
this module's documented bias is that mislabelling a healthy site as broken is
the expensive direction, and upstream leaves `status_code` **null** when the
navigation never commits — so it would have been a lie visible in the one field
MAS was promised holds the origin's real final status.

Three corrections to the diagnosis, all measured offline:

- **It arrives as a failed *result*, not an escaped exception.** Upstream's
  `arun` wraps its whole body in `try:` and returns a failed `CrawlResult`, so
  `classify_result` decides it, not `classify_exception`. The production log
  line's own prefix (`Crawl request failed: …`) is built at exactly one place —
  `server.py`'s `_crawl_response`, the result path.
- **`Content-Disposition: attachment` is not the trigger.** Inline `text/vcard`,
  inline `application/pdf` and `application/octet-stream` all fail identically.
  The rule is "Chromium will not render this inline". That answers the open PDF
  question: yes, on bundled Chromium. Production runs real Chrome, which ships a
  PDF viewer, so the inline-PDF row could differ there; the attachment rows
  cannot.

  > **CORRECTED 2026-08-09: it does differ, and that caveat was published here
  > and then dropped by every downstream reader — including CLAUDE.md's Key
  > Findings row, which stated the opposite as fact for a week.** Re-measured on
  > both browser arms against `fixture_origin`, zero live traffic: **4 of the 5
  > download kinds are identical and `pdf-inline` alone diverges.** Any Chromium
  > carrying the PDF-viewer extension — production's real Chrome, and
  > `channel="chromium"` locally — *renders* an inline PDF into a **174-byte
  > viewer shell** at HTTP 200 with no visible text and no `<embed>` (shadow
  > DOM), which the detector's tier-3 structural inference calls a block →
  > `render_error` → 500, retried.
  >
  > **Consequence: `unrenderable_content` has fired ZERO times in production,
  > ever.** Its trigger phrase appears 16 times in the archive, all on
  > 2026-08-01 — the vCard incident that motivated the class, the day *before*
  > the class shipped. Since 2026-08-02: zero. The class is correct for the four
  > kinds it does cover; it simply never covered PDFs.
  >
  > **Why it took a week: the tests could not see it.**
  > `crawl4ai/browser_manager.py:1123-1128` is a *Windows* workaround applied on
  > every platform that drops `channel` whenever `chrome_channel == "chromium"`,
  > so the browser suite launches `chromium_headless_shell` — which has no PDF
  > viewer. Five download tests have always exercised the download arm, and
  > `pdf-inline` passes for the wrong reason. See TESTING.md's arm64 section.
  >
  > **PDFs used to work, and that is a regression, not a limitation** — MAS holds
  > April captures with 11,101–45,118 chars of extracted PDF text
  > (`tmp/mas-repo-messages/40-…` §3). **What produced that text is NOT
  > established, and MAS's attribution to us is their inference, not a provenance
  > check:** `pypdf` is not in the image (`INSTALL_TYPE=default`, and
  > `deploy/docker/requirements.txt` does not list it), so
  > `PDFContentScrapingStrategy` cannot have run; there is no PDF branch anywhere
  > in the crawl path; and neither browser arm yields PDF text (pre-2026-04-11
  > config had no channel at all → headless shell → the download error).
  > `render_mode: static` is the only in-repo candidate and it does not fit —
  > `aitosoft_static_mode.py` has no content-type gate, so over an uncompressed
  > PDF it emits the PDF *source* (`%PDF-1.4 1 0 obj …`) and over a compressed
  > one mojibake. **Nobody needs PDFs today** (MAS is removing them at dispatch)
  > and nothing is being built. Recorded so a future user's request is not
  > treated as a novelty — and so the claim is not repeated as established. One
  > stored April row's `render_mode` plus the first 200 chars of its markdown
  > would settle it.
- **"Charged four renders" undercounts.** Upstream retries on *any* exception,
  not only on a detected block, so one client request at MAS's `max_retries: 2`
  is three navigations. Four client requests were 8–12 page loads.
  `crawl_stats.attempts` already ships in the envelope MAS stores.

`accept_downloads: true` does **not** rescue it — checked, because it was the
cheap lever nobody had tried. `page.goto` still raises and the download handler
then dies with `Target page … has been closed`.

**A second status-mapping site fell out of the change.** `api.py`'s exception
handler gated its 200-envelope branch on `_exc_class in ORIGIN_CLASSES` rather
than on `http_status_for` — the "one class, two wire statuses" defect MAS found
in July, in the one place the 2026-08-01 fix did not reach. It was latent (no
non-retryable-but-not-origin class could reach that handler); `unrenderable_content`
can. The same handler also dropped 504 on the floor: a Playwright timeout that
escaped `arun` (browser launch, pool acquisition) classified `render_timeout`
and went out as **500**, while the identical class at the wall-clock fence goes
out as 504. Both branches now ask `http_status_for`, so the exception path
mirrors `server._crawl_response` exactly.

### 3. Every failed result is now logged, which it never was

Found by the pre-deploy review while checking a claim in the download task file
("the class is now measurable"). It was not: **nothing logged a failed result's
`failure_class` at all.** These URLs were only ever visible because they
produced a 500 and `server.py` logs 500s — the `Crawl request failed: … Download
is starting` line is literally how the defect was found.

Generalise it, because it will recur: **every time this taxonomy moves a class
off 5xx, it deletes that class's only log line.** `unrenderable_content` was
about to be the first class shipped with no server-side counter at all. `api.py`
now emits `RESULT FAILURE: url=… failure_class=… status=… error=…` for every
failed result, which also closes a hole open since the taxonomy shipped: origin
blocks and origin 4xx arrive as *results*, while `ORIGIN FAILURE` is on the
*exception* path — so `OVERNIGHT_PLAYBOOK.md` has been describing a token that
almost never fires.

**To tell MAS:** the new class value, and that `render_mode: "static"` would
fetch that vCard's body with httpx and hand them the actual contact card. That
is their routing decision, not ours to make.

### Files

| File | Change |
|---|---|
| `deploy/docker/aitosoft_collapse_guard.py` | `recover_markdown()`, `_is_a_real_recovery()`, `GuardVerdict`; `guard_result` returns a verdict instead of a string |
| `deploy/docker/aitosoft_failure_class.py` | `UNRENDERABLE_CONTENT` + `_DOWNLOAD_RE`; `classify_exception` docstring corrected |
| `deploy/docker/api.py` | recovered vs lost branches + `COLLAPSE RECOVERED` token; `RESULT FAILURE` on every failed result; exception gate asks `http_status_for` for 200 **and** 504 |
| `test-aitosoft/fixture_origin.py` | `/download/{kind}` (5 kinds, hand-built PDF), `RECOVERABLE_SHAPES` |
| `test-aitosoft/test_collapse_guard.py`, `test_fixture_origin.py`, `test_failure_classification.py` | recovery + download coverage |
| `OVERNIGHT_PLAYBOOK.md` | `COLLAPSE RECOVERED` and `RESULT FAILURE` rows; `RENDER DEFECT` and `ORIGIN FAILURE` rows restated |

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
verdicts were this, and the expensive one was **`norex.com`**.

**Stated precisely, because the phrasing that stood here until 2026-08-06
conflated two fields and cost four sessions:** `html` was **15 bytes** — a bare
`<!DOCTYPE html>`, a script having removed `documentElement` — and
`Crawl4AI Error: This page is not fully supported` is what our scraper
**generated from** those 15 bytes after lxml raised `Document is empty`. Input
and output, not one thing. Read as one they describe a page that never existed,
which is why four sessions inspected the anti-bot tier instead of our own DOM
handling; the real cause turned out to be `remove_consent_popups.js` deleting
the root (2026-08-06). Either way it was our pipeline's failure reported to the
customer as the origin blocking them. This module's documented bias ("unrecognised failures are
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

## 2026-08-02 — DEPLOYED as `0.9.2-pool-cap` (revision `--0000033`)

Three amendments were made to the section below **at deploy time**; it was
written pre-deploy and is otherwise accurate.

**1. The memory guard now sheds before it refuses.** It used to refuse *before*
`_evict_for_capacity` could run, and removing the adaptive TTL (below) took with
it the only path that shed under pressure — so a replica over 85 % held every
idle browser for the full constant `idle_ttl_sec: 300`. It now evicts one idle
LRU browser per refusal, then refuses anyway.

The specified fix was "evict, **re-read**, then refuse". That is not
implementable: `_close_detached` schedules the close on a task that cannot start
before the coroutine yields, and there is no `await` before a re-read — so it
would measure the number it just read, exactly. Forcing it to start does not
help either (Chromium exit plus kernel reclaim are not synchronous, and sleeping
for them sits inside `LOCK` on the unfenced admission path). The reclaim lands
for the *next* arrival, which is what the 429 + `Retry-After` schedules.

Implementing it via the existing `_evict_for_capacity(headroom=1)` would have
been a **no-op below the cap** — its loop only runs when
`resident + headroom > MAX_BROWSERS` — and would have shipped green doing
nothing. Split out `_evict_lru_idle(reason)`, which also removed a latent
`LOCK`-holding infinite loop in the old body.

**Stated cost:** this re-arms a memory→browser-count feedback loop, the same
confound that disqualifies the 2026-07-31 slope. Narrower (it fires on refusals,
not on a timer) and the eviction log names `memory pressure X%` so those samples
can be filtered — but a naive fit across this build is still biased.

**2. The cap is justified on cardinality, not on memory.** `config.yml` derived 6
entirely from `mem% = 59.3 + 2.65 × browsers`, which is disputed on three counts;
a config comment is the most-read and least-reviewed documentation we have, and
it read as settled fact. Replaced with an argument that needs no memory at all:
`user_agent_mode` is in `UNTRUSTED_FIELD_ALLOWLIST` (`async_configs.py:227`),
`"random"` regenerates the UA in `BrowserConfig.__init__` (`:901`), and **our own
shipped client doc recommends it** (`c4ai-doc-context.md:167`). Verified: 8
identical `user_agent_mode: "random"` configs produce **5 distinct pool
signatures**; 8 identical fixed-UA configs produce **1**. Under that one word the
pool becomes write-only — one Chromium launch per request. Sizing stays
6 = 3 × `render_capacity`.

Also fixed: the guard's `logger.error` evaluated `hot=`/`cold=` *after* the
eviction, so the one line pairing a memory reading with pool composition was off
by one browser. Snapshotted before the shed now.

**3. `permanent_unused_ttl_sec` 600 → 120.** The boot browser is unreachable **by
construction** — `server.py:199` builds its config inline *without*
`enforce_egress`, while `get_default_browser_config():138` and every request path
apply it, so the signatures differ in `ignore_https_errors` and can never match
(0 hits in 224 production pool gets). At 600 s it held ~140 MB through minutes
0–10 of a replica's life, which is exactly the window that produced all nine of
MAS's memory refusals (replica up 04:44:49, refusals 04:46–04:50).
**Not the real fix, deliberately not bundled:** whether that browser should exist
at all — delete the `init_permanent` call, or route it through
`get_default_browser_config()` to make it reachable — is a `server.py` change,
the two options point opposite ways, and it deserves its own attributable change.

Tests: `test_crawler_pool.py` 24 → **27**; full offline suite **247 green**.

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
   **Corrected 2026-08-05: this assumes a WARM replica.** The ingress clock
   starts when the request reaches the ingress, which includes the
   scale-from-zero hold. Worst observed cold start **65 s** + 15 s queue +
   184 s worst measured fence exit = **264 s > 240 s**. Never observed (all
   13 × 504 in 93 days sat at 180–184 s, i.e. our own fence, none near 240 s),
   it needs three worst cases at once, and MAS's 210 s client timeout fires
   first regardless — so this is a stale budget line, not a live risk. But as
   written it invites the reader to believe the margin is 40 s when on a cold
   replica it can be negative.
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

> **⚠ SUPERSEDED — two of the four bullets below are no longer true.** This is a
> historical entry and is left intact on purpose, but a clean-context session
> reading it will be misled, so: (1) `magic`, `simulate_user` and
> `override_navigator` are **accepted**, not rejected — `aitosoft_trust.py:44-49`
> un-forbids them for our trusted client, and `:51-63` **drops** falsy forbidden
> fields rather than 400ing. `js_code` and proxy fields still 400 when truthy.
> (2) Dead domains are **HTTP 200 + `failure_class: origin_unreachable`** since
> 2026-08-05, not an SSRF 400. Current state: CLAUDE.md's untrusted-boundary
> section, verified by executing `apply_trust_relaxations()` 2026-08-06.

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
