# Testing Framework

Rewritten 2026-07-16 (v0.9.2 upgrade). The old version of this file predated
the stealth package and recommended `magic: true` configs — which the v0.9.x
server now REJECTS (untrusted-boundary 400) — and listed retired sites as
Tier 1. If you see advice contradicting this file elsewhere, this file wins.

---

## Golden rules

0. **Live traffic is the last instrument, not the first.** A new failure class
   gets a fixture route. A live request is justified only when the question is
   about a specific third party's behaviour and cannot be answered any other
   way — and then it is one request, recorded in `TEST_SITES_REGISTRY.md`, with
   the host added to the burned list in the same session.
1. **Site safety:** never hit the same site more than 1-2 times per session.
   Over-scraping permanently Cloudflare-blocked talgraf.fi. Rotate sites.
   Hosts already burned (and the offline suite that replaces each) are listed
   under "Burned during the 2026-07-30 WAA eval" in `TEST_SITES_REGISTRY.md`.
   Never live-test a host MAS classified `blocked` or `challenge`.
2. **Tier 1 must pass 4/4 before any deploy** (quality gate).
3. Source of truth for tier membership: `test-aitosoft/test_regression.py`
   (`TIER_1_SITES`). Site metadata: `TEST_SITES_REGISTRY.md`.
4. Use the `optimal` config (matches MAS production). Never `magic` — it
   removes content on cookie sites AND the server rejects it when truthy.

Why rule 0 outranks rule 1: rule 1 is a budget, and we had no way to spend it
honestly. Every failure class diagnosed since 2026-04 was diagnosed against a
customer's site, all of it leaving from one Azure SNAT address that is not
contractually ours and that MAS's production fetches share — so "this host
blocks datacentre IPs" and "this host blocked us because of what we did" were
indistinguishable, and their re-scrape and our test hits drew on one account.
`test-aitosoft/fixture_origin.py` removes the reason: a local origin with a
route per failure class, driven through the real production path. Adding a
class there is a query parameter. See `tasks/done/fixture-origin.md`.

## How to run

All tests are HTTP clients against a running service. Point them anywhere via
env vars:

```bash
export CRAWL4AI_API_URL=http://127.0.0.1:11235   # default: production endpoint
export CRAWL4AI_API_TOKEN=<token>                 # required

python test-aitosoft/test_regression.py --tier 1 --version <label>  # quality gate
python test-aitosoft/test_site.py <domain> --page <path>            # single site
python test-aitosoft/test_site.py <domain> --render-mode static     # static mode
python test-aitosoft/test_fingerprint.py --label <label>            # stealth diagnostic
python test-aitosoft/test_soak.py --duration-min 30                 # leak hunting
```

Everything pytest collects is OFFLINE — no server, no customer site:

```bash
pytest test-aitosoft/          # 285 tests, ~240 s
```

That splits in two, and the split matters when you are choosing where to put a
new test:

| | Suites | Tests | Time | Covers |
|---|---|---:|---|---|
| Pure-function | the twelve below | 231 | ~15 s | synthetic strings through `strip_noscript`, `is_blocked`, `classify_result`, the config boundary, the gate |
| Browser-driven | `test_fixture_origin.py` | 54 | ~220 s | **time, navigation and the browser** — challenge resolution, hydration races, redirect chains, the wall-clock fence |

```bash
pytest test-aitosoft/test_mas_contract.py test-aitosoft/test_admission.py test-aitosoft/test_static_mode.py test-aitosoft/test_crawler_pool.py test-aitosoft/test_patchright_fallback.py test-aitosoft/test_redirect_block_detection.py test-aitosoft/test_render_bounds.py test-aitosoft/test_failure_classification.py test-aitosoft/test_noscript_body_collapse.py test-aitosoft/test_antibot_challenge_detection.py test-aitosoft/test_collapse_guard.py test-aitosoft/test_egress_dns_offload.py
```

This list drifts, three times now: it said "seven suites, 64 tests" three suites
later, and it was still missing `test_collapse_guard.py` a day after that suite
shipped. **`CLAUDE.md` no longer keeps a parallel copy** — it runs
`--ignore=test-aitosoft/test_fixture_origin.py` instead, which is the same split
expressed as a complement and cannot go stale. Prefer that form; this explicit
list survives only because it names the suites.

The four CLI scripts (`test_regression.py`, `test_site.py`,
`test_fingerprint.py`, `test_soak.py`) need a live server + token and are run by
hand as shown above. `test-aitosoft/conftest.py` keeps pytest from collecting
them; three of their helpers are named `test_*`, so a clean run used to report
three errors, and a permanently red bar trains you to ignore the bar.

**Always run from the repo root** — artifact/report paths are relative
(`test-aitosoft/reports/`); running from inside `test-aitosoft/` creates a
nested `test-aitosoft/test-aitosoft/` clutter directory.

Reports land in `test-aitosoft/reports/`.

### Reproducing a scraper bug with zero site hits

Golden rule 1 makes live bisection expensive. You almost never need it: the
`/crawl` response already carries the raw `html`, so capture it once and bisect
the markup locally.

```python
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
res = LXMLWebScrapingStrategy().scrap(url, html, word_count_threshold=1)
len(res.cleaned_html)   # compare against len(html)
```

This is how the nested-`<noscript>` body loss was found and fixed (312 KB HTML
→ 97 B `cleaned_html`) without a single extra request to the affected host.
Same trick for block detection: `antibot_detector.is_blocked(...)` takes stored
HTML/markdown, which is how the challenge families were fixed against MAS's
stored samples rather than against live challenged hosts.

### Reproducing one that needs a browser

Stored HTML cannot answer anything about *when* we captured it. For challenge
resolution, hydration races, `page.content()` against a navigating frame or a
redirect chain ending in a block, use the fixture origin
(`test-aitosoft/fixture_origin.py`): a threaded HTTP server with a route per
failure class, driven through `aitosoft_entry` → `api.handle_crawl_request` →
a real pool browser, so `failure_class`, `render_mode`, the final-hop
`status_code` rewrite, the patchright retry and the wall-clock fence are all
genuinely exercised.

```python
def test_something(fixture_origin, production_path):        # fixtures are global
    outcome = production_path.crawl(
        fixture_origin.url("/challenge/resolve-after/5"),   # delay is an argument
        delay_before_return_html=0.1,                       # the capture wait
    )
    assert outcome.failure_class == "origin_blocked"
    assert outcome.http_status == 200                       # what MAS would see
    assert fixture_origin.hits_for("/challenge") == 2       # what it cost us
```

Everything is a parameter — delay, body size, visible-text length, status code,
markup shape, plus `?stall=` (server-side sleep) and `?status=` on every route.
**A new failure class should be a new argument or one short route, never a new
website.** Existing routes are listed in the module docstring.

**Measuring rather than pinning.** When the question is a number we do not yet
have — a curve, a threshold, a cost — write an *experiment* next to the fixture,
not a test. `test-aitosoft/experiment_challenge_capture.py` is the worked example
(~140 crawls, ~20 min, no assertions, CSV + tables out); it produced the
`W + 1.22 s` capture budget in `tasks/challenge-interstitial-resolve.md` for zero
live requests. Tests pin behaviour we have decided on; experiments measure
behaviour we have not, and `pytest test-aitosoft/` must stay fast, so name them
`experiment_*.py` — that keeps them out of collection without another
`collect_ignore` entry.

**That gap is closed (2026-08-01).** `CONTENT_HTML` used to render to ~140
markdown characters — *below* MAS's `DEGENERATE_CAPTURE_CHARS = 500` — so a
completely successful fixture capture was degenerate by the customer's own floor.
It now renders **1,227 markdown characters over 1,135 of visible text**, above 500
on both sides of the unit boundary, and
`test_fixture_origin.py::test_the_healthy_control_is_not_degenerate` fails if
anyone trims it back. Keep it that way: the collapse guard's thresholds are sized
against this page, and a healthy control that trips the customer's floor is not a
control.

Two fixture habits that came out of sizing that guard, both of which cost a root
cause when ignored:

- **Pad to a realistic size before drawing conclusions.** `/collapse/*` serves
  ~1.5 KB by default; `?bytes=73000` reproduces `apteam.fi`'s fingerprint.
  `deep-nesting` does **not** collapse at 1.5 KB and does at 73 KB, so an
  unpadded enumeration misses a whole mechanism — not merely a threshold.
- **Name the unit every time.** MAS's 500 is **markdown characters**; our collapse
  ratio is markdown characters per **visible-text character**; `len(html)` and
  `len(cleaned_html)` are **HTML bytes** and appear nowhere in the guard, because
  they are dominated by inline CSS/JS that cleaning strips by design.

The fixture runs on loopback, which `egress_broker` exists to refuse. It is not
weakened: `loopback_allowed()` flips the two flags
`CRAWL4AI_ALLOW_INTERNAL_URLS` sets, scoped to a `with` block around each crawl,
never as a process-wide environment variable —
`test_fixture_origin.py::test_production_configuration_refuses_the_fixture_origin`
asserts the production configuration still refuses the fixture's own URL, in the
same suite. Do not turn that into an env var; the other suites in the same
pytest process would silently lose their SSRF assertions.

### Running the server locally (devcontainer)

```bash
redis-server --daemonize yes
cd deploy/docker
CRAWL4AI_API_TOKEN=<anything> \
CRAWL4AI_ARTIFACT_DIR=/tmp/artifacts \
python -m uvicorn aitosoft_entry:app --host 127.0.0.1 --port 11235
```

arm64 caveat (this devcontainer): real Chrome doesn't exist for linux/arm64 —
temporarily comment the `chrome_channel`/`channel` lines in
`deploy/docker/config.yml` for local runs (NEVER commit that). The deployed
amd64 image has real Chrome.

PyJWT caveat: a stale `jwt` 1.4.0 package can shadow PyJWT and break server
boot locally — `pip uninstall jwt` fixes it (the image installs fresh and is
unaffected).

## The `optimal` config (mirrors MAS)

```json
{
  "wait_until": "domcontentloaded",
  "scan_full_page": false,
  "remove_overlay_elements": false,
  "remove_consent_popups": true,
  "page_timeout": 60000,
  "delay_before_return_html": 2.0
}
```

## Key findings (hard-won, don't relearn)

| Finding | Detail |
|---------|--------|
| `remove_consent_popups: true` solves cookie walls | Accountor: 7811 tokens; magic was never needed |
| Raw markdown > fit_markdown for contacts | PruningContentFilter drops contact blocks at threshold >= 0.35 |
| `magic: true` is harmful | Removes real content on cookie-consent sites; also rejected by v0.9.x server |
| Blocked sites are IP-based, not fingerprint | Two different browser engines got identical blocks (2026-04-11 study) |
| Playwright can hang pre-Python | Some hosts (roadscanners.com) hang the DevTools protocol; that's what `render_mode: "static"` is for |

## v0.9.x server behavior tests should expect

- Forbidden config fields (`js_code`, proxy fields, `cookies`, …) → HTTP 400
  when truthy; silently dropped when falsy (our tolerant boundary,
  `aitosoft_entry.py`).
- Unknown config fields → silently dropped.
- Dead/unresolvable domains → HTTP 400 `URL blocked (SSRF protection)`.
- Wall-clock timeout (config `limits.wall_clock_s`, 180s) → HTTP 504.
- Every result carries `render_mode: "full" | "static"`.
- Only `/health` is public; everything else needs the bearer token
  (including `/docs` and `/metrics`).

## Quality gates

| Gate | When | Bar |
|------|------|-----|
| MAS contract test (`pytest test-aitosoft/test_mas_contract.py`) | before every deploy + after every upstream sync | 8/8 pass — offline, pins MAS's exact request fields against the untrusted boundary + single-URL 400 |
| Render-gate test (`pytest test-aitosoft/test_admission.py`) | before every deploy; after any admission/capacity change | all pass — offline, pins RenderGate capacity/queue/429 semantics |
| Static-mode test (`pytest test-aitosoft/test_static_mode.py`) | before every deploy; after any static-mode change | all pass — offline, pins per-hop SSRF redirect validation, bounded fan-out, monitor outcome |
| Crawler-pool test (`pytest test-aitosoft/test_crawler_pool.py`) | before every deploy; after any pool change | all pass — offline, pins PERMANENT lazy re-init after stuck force-close |
| Patchright-fallback test (`pytest test-aitosoft/test_patchright_fallback.py`) | before every deploy; after any fallback change | all pass — offline, pins in-flight counter + recycle-race fix |
| Redirect block-detection test (`pytest test-aitosoft/test_redirect_block_detection.py`) | before every deploy; after any block-detection change | 11/11 pass — offline, pins that block detection judges the FINAL redirect hop, that benign 301→200 stays a success, and the retry/patchright cost of a blocked verdict |
| Render-bounds test (`pytest test-aitosoft/test_render_bounds.py`) | before every deploy; after any change to the capture path, adapters, or timeouts | 17/17 pass — offline, pins that `page.evaluate`/`page.content`/`total_timeout` are all bounded, and that config.yml's `total_timeout` stays inside `wall_clock_s` |
| Failure-classification test (`pytest test-aitosoft/test_failure_classification.py`) | before every deploy; after any change to `failure_class`, the error-text matching, or the 200/500/504 mapping | 34/34 pass — offline, pins MAS's Q2 contract: origin-caused ⇒ 200 + `success:false`, 5xx reserved for us, `failure_class` on every result |
| Noscript-collapse test (`pytest test-aitosoft/test_noscript_body_collapse.py`) | before every deploy; after any change to `strip_noscript()` or the scraping strategy | 11/11 pass — offline, pins that a nested `<noscript>` no longer swallows the body |
| Challenge-detection test (`pytest test-aitosoft/test_antibot_challenge_detection.py`) | before every deploy; after any `antibot_detector` pattern change | 18/18 pass — offline, pins both measured challenge families at HTTP 200 and the Shopify `Access Denied` false positive |
| Fixture-origin test (`pytest test-aitosoft/test_fixture_origin.py`) | before every deploy; after any change to the capture path, block detection, `failure_class` or the fence | **54/54 pass — offline but browser-driven (~220 s)**, measured 3× consecutively on 2026-08-05 (221.6 / 220.0 / 219.8 s). The "23/23, ~50 s" this row claimed was stale by a wide margin. Three of its tests pin defects **on purpose** (padded block at 202, unmarked interstitial, unclosed `<noscript>`); when the owning task ships, invert them, don't delete them. Note `MAS_MAX_RETRIES = 2` in this file models a request shape MAS has **never** sent (production is 1) — see `tasks/README.md` corrections |
| Tier 1 regression | before every deploy | 4/4 pass |
| Fingerprint diagnostic | after stealth/browser changes | no regressions vs `test-aitosoft/stealth-v4/` |
| Soak test | after pool/leak-related changes | flat memory over 30 min |
| Post-deploy smoke | after every deploy | health + 1 crawl + auth 401 check |
| Upstream merges | after every sync | Tier 1 + `git diff upstream/develop HEAD` matches AITOSOFT_FILES.md inventory |
