# Testing

How to prove a change works without spending customer goodwill. Counts and
runtimes were measured 2026-11-03 on this devcontainer (arm64). Test sites,
expected contacts and the burned-host list are in `TEST_SITES_REGISTRY.md`.

---

## Golden rules

0. **Live traffic is the last instrument, not the first.** Use stored captures,
   `test-aitosoft/fixture_origin.py` and `raw://` first (see "Zero-traffic
   instruments"). A live request is justified only when the question is about a
   specific third party's behaviour and nothing else can answer it. Then it is
   **one request**, recorded in `TEST_SITES_REGISTRY.md`, with the host added to
   its burned list in the same session.
1. **Site safety:** at most 1–2 hits per host per session; rotate. Our own
   over-scraping got talgraf.fi permanently Cloudflare-blocked. Never live-test a
   host on the registry's burned list, or one MAS has classified `blocked` or
   `challenge`.
2. **Tier 1 must pass 4/4 before any deploy.**
3. Tier membership: `TIER_1_SITES` in `test-aitosoft/test_regression.py` is the
   source of truth. The registry holds metadata.
4. **Use the `optimal` config; never `magic`.** `magic` removes real content on
   cookie-consent sites. The server will **not** stop you: `aitosoft_trust.py`
   (its step 3) un-forbids `magic`, `simulate_user` and `override_navigator` for our
   trusted client. Any doc that says the server rejects `magic` is stale.

Why rule 0 outranks rule 1: every live test leaves from the Azure SNAT address
that MAS's production fetches also use, and that address is not contractually
ours. Our test hits and their sweeps draw on one reputation budget, and "this
host blocks datacentre IPs" looks identical to "this host blocked us because of
what we did".

---

## Offline suites: what proves what

```bash
pytest test-aitosoft/                                                # 332 tests, ~270 s
pytest test-aitosoft/ --ignore=test-aitosoft/test_fixture_origin.py  # 262 tests, ~30 s (pure-function)
pytest test-aitosoft/test_fixture_origin.py                          # 70 tests, ~245 s (browser, loopback)
pytest deploy/docker/tests/test_security_*.py -q                     # upstream's: 343 passed + 1 xfailed, ~8 s (needs pypdf)
```

None of these contacts a server or a customer site. Run them from the repo root.
Since v0.9.5 the security suite needs `pypdf` (now in `deploy/docker/requirements.txt`, so CI and
the image have it). Without it two `test_security_pdf_image_write` tests fail; install it with
`pip install -r deploy/docker/requirements.txt`, or run the suite from a venv that has it.
`test-aitosoft/conftest.py` keeps pytest from collecting the four live CLI
scripts. Counts change whenever a test is added, so regenerate them instead of
trusting the table:

```bash
pytest test-aitosoft/ --collect-only -q | grep '::' | cut -d: -f1 | sort | uniq -c
```

| Suite | Tests | Pins | Re-run after touching |
|---|--:|---|---|
| `test_mas_contract.py` | 16 | MAS's audited request fields against the untrusted boundary plus our relaxations; multi-URL → 400; every 429 carries `capacity_gate` | `async_configs.py`, `aitosoft_trust.py`, any upstream sync |
| `test_admission.py` | 13 | RenderGate capacity, bounded queue, 429 + `Retry-After` | admission / capacity |
| `test_crawler_pool.py` | 27 | PERMANENT re-init, `max_browsers` evict-or-refuse (never wait), memory guard, the cgroup reading | `crawler_pool.py`, `deploy/docker/utils.py` memory functions |
| `test_static_mode.py` | 10 | per-hop SSRF redirect validation, bounded fan-out, monitor outcome | `aitosoft_static_mode.py` |
| `test_patchright_fallback.py` | 4 | in-flight counter, recycle race | `aitosoft_patchright_fallback.py` |
| `test_redirect_block_detection.py` | 12 | block detection judges the final redirect hop; a benign 301→200 stays a success | `antibot_detector.py`, `async_webcrawler.py` |
| `test_antibot_challenge_detection.py` | 31 | challenge families served at HTTP 200; the Shopify `Access Denied` false positive | `antibot_detector.py` patterns |
| `test_render_bounds.py` | 17 | `page.evaluate`, `page.content` and `total_timeout` are bounded; `total_timeout` sits inside `wall_clock_s` | capture path, adapters, timeouts |
| `test_failure_classification.py` | 56 | the `failure_class` taxonomy and its wire status (table below) | `aitosoft_failure_class.py`, error-text matching |
| `test_noscript_body_collapse.py` | 11 | a nested `<noscript>` no longer swallows the body | `strip_noscript()`, scraping strategy |
| `test_collapse_guard.py` | 34 | guard thresholds against real captures; recovery | `aitosoft_collapse_guard.py` |
| `test_egress_dns_offload.py` | 14 | DNS off the event loop; NXDOMAIN → `origin_unreachable`; proxy connect timeout; `http://` connect failure closes | `egress_proxy.py`, `egress_broker.py`, the seed check in `api.py` |
| `test_media_desc_cap.py` | 6 | image `desc` capped at 200 chars | `content_scraping_strategy.py` |
| `test_fixture_origin.py` | 67 | browser-driven: time, navigation, challenge resolution, hydration, redirect chains, consent/overlay JS, downloads, the wall-clock fence | capture path, block detection, `failure_class`, consent/overlay snippets, the fence |

**Tests that pin a defect on purpose.** Three tests in `test_fixture_origin.py`
assert today's wrong behaviour so that the fix has a red test to turn green:
`test_an_unmarked_interstitial_is_stored_as_content`,
`test_a_body_swallowed_into_a_script_is_still_silent` (`unclosed-script`) and
`test_a_self_inflicted_click_navigation_is_detected`. When the fix ships, invert
them; do not delete them. If one flips during a merge, that is a finding, not
noise.

### Known limitations

- **Locally, the browser suite does not run production's browser.** It runs Playwright's
  `chromium_headless_shell`, which has no PDF viewer. Details and the two fixes
  are under "arm64 devcontainer" below. It *can* run on real Google Chrome inside
  a built image: see "Inside a built image" below.
- **CI runs only the offline half of `test-aitosoft/`** (since 2026-11-03).
  `.github/workflows/aitosoft-tests.yml` runs
  `pytest test-aitosoft/ --ignore=test-aitosoft/test_fixture_origin.py` on
  Python 3.12 on every push and PR, unfiltered. The browser suite still runs
  only where someone types the command. Upstream's `security.yml` runs
  `deploy/docker/tests/test_security_*.py` on Python 3.10, on pushes to `main`,
  `develop` or `security/**` and on PRs, **path-filtered** to
  `deploy/docker/**`, `crawl4ai/async_configs.py` and the workflow file.
- **Four tests need the gitignored corpus.** `test-aitosoft/artifacts/*` is
  gitignored, so `test_collapse_guard.py`'s
  `test_thresholds_clear_every_real_capture`,
  `test_the_real_corpus_still_shows_the_gap` and
  `test_no_real_capture_is_mutated_by_the_guard`, and
  `test_antibot_challenge_detection.py::test_no_stored_real_capture_is_condemned`,
  only pass on a machine that holds the local corpus. They carry the
  `requires_corpus` marker: under CI (`CI` set) with no corpus they skip; on a
  fresh local clone they still fail loudly, which is the safe direction.
  `tasks/guard-corpus-is-not-in-the-repo.md`.
- **Fixture tests bypass the pinning egress proxy.** `ProductionPath` calls
  `api.handle_crawl_request` directly, so the lifespan that installs the proxy
  never runs. CONNECT handling, the connect timeout and dead-host cost are
  covered only by `test_egress_dns_offload.py`.
  `tasks/done/fixture-origin-bypasses-the-pinning-proxy.md`.

---

## Live CLI scripts

These need a running server and a token. **All four default to the production
endpoint**, so point them elsewhere explicitly:

```bash
export CRAWL4AI_API_URL=http://127.0.0.1:11235    # unset = production
export CRAWL4AI_API_TOKEN=<token>                  # required; scripts exit without it
```

| Command | Live cost | Status |
|---|---|---|
| `python test-aitosoft/test_regression.py --tier 1 --version <label>` | 1 request per Tier 1 host, a 2nd if the result is thin | The deploy gate. Report: `test-aitosoft/reports/<label>-regression-tier1.md`; captures: `test-aitosoft/artifacts/<label>/` |
| `python test-aitosoft/test_site.py <domain> [--page <path>] [--config optimal\|patient] [--render-mode full\|static] [--version <label>] [--no-save]` | 1 request | Single-site check. `static` is for hosts where Playwright hangs |
| `python test-aitosoft/test_fingerprint.py --label <label> [--url <api>]` | 4 fingerprint sites | **Broken since v0.9.2 (2026-07-16):** it sends `js_code`, which the untrusted boundary rejects with 400 (verified offline 2026-11-03). Baseline `test-aitosoft/stealth-v4/` is from 2026-04-11 |
| `python test-aitosoft/test_soak.py --duration-min 30 [--url <api>] [--parallel N]` | **Hundreds of requests** | **Do not run as written.** It loops over 9 public sites, three Tier 1 hosts and 3 "hard" URLs for the whole duration. The stored 2026-04-14 30-minute run sent 327 requests: 22–23 each to jpond.fi, caverna.fi and solwers.com, 36 to www.diabetes.fi, 18 to ahlmanedu.fi (`test-aitosoft/results/soak-20260414-160043.json`). It predates rule 0. For memory and leak questions, use `experiment_pool_memory.py` or a `raw://` probe |

What the Tier 1 gate actually checks (`test_regression.py` via `test_site.py`):
- HTTP 2xx with envelope `success: true`. The envelope is true for every
  processed request, origin failures included; per-result `success` is never
  read, so the markdown floor is what catches a failed page;
- at least 100 "tokens" of `raw_markdown`, where a token is `len // 4`, i.e. at
  least 400 chars;
- at least 50 % of the expected decision-maker names appear in `raw_markdown`.

It reads `raw_markdown`, not `fit_markdown`, because PruningContentFilter drops
contact blocks at threshold ≥ 0.35. If the markdown is under 100 tokens, it
retries once with `patient` (networkidle + full scroll), which is a second live
hit. It does not check phones, emails, `failure_class`, or
`expected_min_contacts` (that field is defined but never read). caverna.fi has
no expected names and passed on 2026-08-17 with 133 tokens. **Do not use `--all` or `--tier 2`:** Tier 2
repeats jpond.fi, solwers.com and caverna.fi, so `--all` hits them twice in one
run (four times with the thin-result retry), which breaks rule 1.

---

## The `optimal` config

`test_site.py` sends this by default, and `fixture_origin.DEFAULT_CRAWLER_CONFIG`
copies it with a shorter page timeout:

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

It carries MAS's content-shaping flags, but it is not MAS's whole request. MAS's
verbatim payload is pinned in `test_mas_contract.py`: `page_timeout: 90000`,
`locale: fi-FI`, `timezone_id: Europe/Helsinki`, plus a per-company
`browser_config` identity. Their `max_retries` was measured as 1 in production
on 2026-08-05 (`FINDINGS.md` §Request contract). Keep `remove_overlay_elements` false: its size rule
still removes large fixed or absolutely-positioned elements, such as a
full-width hero holding the contacts.

## What tests should expect from the server

| Situation | HTTP | Body | MAS does |
|---|---|---|---|
| Success | 200 | `success: true`, `failure_class: "none"` | uses `results[0]` |
| Origin failure: `origin_http_error`, `origin_blocked`, `origin_unreachable` (NXDOMAIN included) | 200 | `success: false` | logs it, no retry |
| `render_defect` / `unrenderable_content` (ours or nobody's, but permanent) | 200 | `success: false` | logs it, no retry |
| `render_error` (ours, transient) | 500 | | retries up to 3× at 1 / 2 / 4 s (also 502, 503) |
| `render_timeout`: the `limits.wall_clock_s` fence, 180 s | 504 | | no retry; 2 consecutive 504s on a host pivot that host to `render_mode: static` for the session |
| Capacity | 429 + `Retry-After` | `failure_class: "capacity"`, `capacity_gate` ∈ `render_slots` / `memory` / `browser_pool` / `unspecified`; the memory gate adds `memory_pct`, `limit_pct` | retries on a 5 / 10 / 20 / 30 s ladder; never parses `Retry-After` |
| More than one URL | 400 | | returns a failure, no retry |
| Truthy forbidden field (`js_code`, proxy fields, …) | 400 | falsy forbidden fields and unknown fields are silently dropped | returns a failure, no retry |
| Genuine SSRF target (`169.254.169.254`, `127.0.0.1:8080`) | 400 | | returns a failure, no retry |
| Missing or wrong bearer token | 401 | reachable without it: `/health`, `/token` (itself demands the token) and the static UI (`/dashboard`, `/playground`, `/static`); `/docs` and `/metrics` need the token | returns a failure, no retry |

The "MAS does" column is MAS's client as they re-read it at their HEAD on
2026-08-06 (`tmp/mas-repo-messages/23-from-us-your-3-limit-is-removable.md`;
first stated in `09-from-us-taxonomy-answer-and-zero-traffic.md`, 2026-07-31). Its retry
decision reads the wire status only, and the body only for its log message, so
`failure_class` changes no MAS behaviour. Their client gives up at 210 s.

Every result carries `render_mode` (`full` | `static`) and `failure_class`.
`failure_class` says whose fault a failure is; `status_code` (rewritten to the
final redirect hop) says what the origin answered. A styled 404 page is
`success: true`, `failure_class: "none"`, `status_code: 404`. The authority is
`aitosoft_failure_class.http_status_for`. To print the forbidden-field sets
after our relaxations, use the one-liner in `FINDINGS.md` §Untrusted-config
boundary.

**Never branch on `status_code == 200` meaning success, or on
`status_code >= 400` meaning failure**, in a test or anywhere else. The outcome
is result-level `success` plus `failure_class`. In MAS's 243-host re-scrape
(2026-08-01), 36 responses carried origin status **202**, all from challenge
families, and the same 202 carried interstitials, block pages, real content and
empty bodies. A block page at 202 passed as a healthy page until the
status-independent block-notice tier shipped on 2026-08-01 (`AITOSOFT_CHANGES.md`).

---

## Zero-traffic instruments

### Stored captures: scraper bugs, no browser

The `/crawl` response carries the raw `html`, and every Tier 1 run stores it
under `test-aitosoft/artifacts/<label>/` (local only, gitignored). Bisect the
markup offline:

```python
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
res = LXMLWebScrapingStrategy().scrap(url, html, word_count_threshold=1)
```

`antibot_detector.is_blocked(...)` takes stored HTML and markdown the same way.
This is how the nested-`<noscript>` loss and the challenge families were fixed
without contacting the affected hosts.

### Fixture origin: time, navigation and the browser

Stored HTML cannot tell you *when* we captured it. For challenge resolution,
hydration races, `page.content()` against a navigating frame, redirect chains or
the fence, use `test-aitosoft/fixture_origin.py`. It is a threaded loopback HTTP
server with one route per failure class, driven through `aitosoft_entry` →
`api.handle_crawl_request` → a real pool browser:

```python
def test_something(fixture_origin, production_path):        # fixtures registered by conftest.py
    outcome = production_path.crawl(
        fixture_origin.url("/challenge/resolve-after/5"),   # delay is an argument
        delay_before_return_html=0.1,                       # the capture wait
    )
    assert outcome.failure_class == "origin_blocked"
    assert outcome.http_status == 200                       # what MAS would see
    assert fixture_origin.hits_for("/challenge") == 2       # what it cost us
```

Routes are listed in the module docstring. Delay, body size, visible-text
length, status and markup shape are all parameters, and `?stall=` and `?status=`
work on every route. **A new failure class should be a new argument or one short
route, never a new website.** Habits that each cost a root cause when ignored:

- **Pad to a realistic size.** `/collapse/*` serves ~1.5 KB by default;
  `?bytes=73000` matches a real page. `deep-nesting` is harmless at 1.5 KB and
  fatal at 73 KB.
- **Name the unit.** MAS's 500 floor is markdown chars; the collapse ratio is
  markdown chars per visible-text char; `len(html)` and `len(cleaned_html)` are
  HTML bytes and appear nowhere in the guard.
- **Keep the healthy control healthy.** `CONTENT_HTML` renders ~1,200 markdown
  chars, above MAS's 500. `test_the_healthy_control_is_not_degenerate` fails if
  it is trimmed.
- **Never turn the loopback allowance into an env var.** `loopback_allowed()`
  flips the SSRF flags inside a `with` block around each crawl. A process-wide
  `CRAWL4AI_ALLOW_INTERNAL_URLS` would silently disable the SSRF assertions of
  every other suite in the same pytest run.
  `test_production_configuration_refuses_the_fixture_origin` guards this.

**Measuring rather than pinning.** When the answer is a number you do not have
yet (a curve, a threshold, a cost), write `experiment_*.py` next to the fixture:
no assertions, CSV or tables out, and the name keeps it out of collection.
`experiment_challenge_capture.py` produced the `W + 1.22 s` capture budget;
`experiment_pool_memory.py` prices a pooled browser.

### `raw://`: the full render path with no navigation

A `raw://<html>` URL skips DNS and the SSRF check (`deploy/docker/utils.py`,
`validate_url_destination`) but still renders in the browser via
`page.set_content()` whenever `needs_browser` is set, and `remove_consent_popups`
sets it. It therefore exercises RenderGate, the pool, a real Chromium launch,
the consent pass, scraping, markdown and the collapse guard. Wall time is about
1.3 s plus `delay_before_return_html`, so render duration is a dial. Verified
locally 2026-11-03 with a 0.1 s delay: 200, `failure_class: "none"`, 1.7 s.

It does **not** exercise navigation. `status_code` is always 200,
`redirected_status_code` is null, block detection is skipped for `raw:` URLs,
and there is no egress path. Use the fixture origin for those.

**Zero egress holds only for self-contained HTML.** `set_content()` fetches every
absolute subresource and runs inline scripts. Nothing blocks routes by default
(`text_mode: false`; `browser_manager.py` installs route blocking only for
`avoid_css`, `text_mode` and `avoid_ads`). Replaying a stored real capture as
`raw://` therefore fetches the customer's images, CSS and scripts and fires
their analytics. Strip `<script>`, `<iframe>`, `<link>` and absolute
`src`/`srcset`/`href` first, identically in both arms. This comes from reading
the code; it was not executed.

For load and scaling (cold start, 429s, replica count), use
`cold_burst_probe.py` and `sustained_rate_probe.py`; see `AZURE_OPERATIONS.md`
§3.10. Both default to the production endpoint and call `az` for replica state.

---

## Before/after comparison (upstream merge)

Feed the same input through both trees, so no third party's drift can enter the
diff. Cheapest arm first.

**1. Offline suites on both trees.**

```bash
git worktree add <dir> <pre-merge-sha>
cp -r test-aitosoft/artifacts/. <dir>/test-aitosoft/artifacts/      # the corpus is gitignored
(cd <dir> && python -m pytest test-aitosoft/ -q -rA -p no:cacheprovider) > before.txt
python -m pytest test-aitosoft/ -q -rA -p no:cacheprovider > after.txt
diff <(grep -E '^(PASSED|FAILED|ERROR|XFAIL|XPASS)' before.txt | sort) \
     <(grep -E '^(PASSED|FAILED|ERROR|XFAIL|XPASS)' after.txt | sort)
```

Repeat with `deploy/docker/tests/test_security_*.py`. **Use `python -m pytest`
in the second tree, not `pytest`.** `pip install -e .` registers a finder that
maps `crawl4ai` to the main checkout. Plain `pytest` in a worktree therefore
imports the main checkout's `crawl4ai` together with the worktree's
`deploy/docker` (the suites add their own tree's `deploy/docker` via
`__file__`), a silent mix of two versions. `python -m` puts the cwd first.
Verified 2026-11-03. Confirm with `python -c "import crawl4ai;
print(crawl4ai.__file__)"` from the worktree root.

**2. Scrape and markdown over the stored corpus (no browser, no network).**
Upstream changes to the scraper or the markdown generator show up here first.
There are 86 stored result JSONs on this machine (2026-11-03), each with `url`,
`html` and the image's own `markdown`. The loop below runs over all of them in
~4 s:

```python
import glob, json
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
for p in sorted(glob.glob("test-aitosoft/artifacts/*/*.json")):
    if p.endswith("-meta.json"):
        continue
    r = json.load(open(p))
    s = LXMLWebScrapingStrategy().scrap(r["url"], r["html"], word_count_threshold=1)
    md = DefaultMarkdownGenerator().generate_markdown(input_html=s.cleaned_html, base_url=r["url"])
    print(p, len(s.cleaned_html), len(md.raw_markdown))
```

Run it in each tree (`PYTHONPATH=<tree> python script.py`) and diff the output.
This is not the server's exact scraping configuration: only 30 of the 86 stored
captures reproduce their stored markdown length. **Compare tree against tree,
never snippet against stored markdown.** If upstream renamed the API, that is a
finding in itself.

**3. Two local servers, identical `raw://` bodies.** This covers the browser
stage and the response envelope. Start one server per tree on its own port (see
below; the old tree needs `PYTHONPATH=<tree>`). POST the same self-contained
bodies to both, then diff `success`, `failure_class`, `render_mode`,
`raw_markdown`, `len(cleaned_html)` and the size of `media`. Skip the echoed
`url`, which contains the whole payload. Browser behaviour that depends on
navigation stays with arm 1.

**4. Tier 1, once, on the merged build.** This is one live pass under rule 1.
Compare each host's capture with the previous run's under
`test-aitosoft/artifacts/`.

---

## arm64 devcontainer: what runs and what does not

**Running the server locally:**

```bash
redis-server --daemonize yes
cd deploy/docker
CRAWL4AI_API_TOKEN=<anything> \
CRAWL4AI_ARTIFACT_DIR=/tmp/artifacts \
python -m uvicorn aitosoft_entry:app --host 127.0.0.1 --port 11235
```

`aitosoft_entry:app` is the production entry point (`supervisord.conf`), so it
applies the config.yml defaults and the trust relaxations. `server:app` skips
both. On this machine startup **fails** with `Chromium distribution 'chrome' is
not found at /opt/google/chrome/chrome`, because `deploy/docker/config.yml:254-255`
pins `chrome_channel: chrome` / `channel: chrome` and Chrome has no linux/arm64
build. Comment those two lines out for the local run. **Never commit that edit**
(it has been committed by accident before), so check
`git diff --exit-code deploy/docker/config.yml` before committing. With the two
keys removed (verified 2026-11-03, patched in-process), the server boots,
`/health` returns 200, unauthenticated `/crawl` returns 401, and a `raw://`
crawl returns 200. To serve a second tree (a worktree), run the same command from
`<tree>/deploy/docker` with `PYTHONPATH=<tree>` and a different `--port`.
`python -m` puts `deploy/docker` first on the path, not the tree root, so
without `PYTHONPATH` the server imports the main checkout's `crawl4ai`. If boot
fails on a `jwt` import, a stale `jwt` 1.4.0 package is shadowing PyJWT: run
`pip uninstall jwt`.

**Neither the local server nor the browser suite runs production's browser.**
`fixture_origin._resolve_channel()` falls back to `"chromium"` when no
`google-chrome` is on PATH, which is always the case here. Then
`crawl4ai/browser_manager.py:1127`, a Windows workaround applied on every
platform, drops `channel` whenever it equals `"chromium"`. Playwright therefore
launches `chromium_headless_shell`, which has no PDF viewer.
`CRAWL4AI_FIXTURE_CHANNEL=chromium` cannot help, because it is the same string
that gets dropped. The full Chromium build is installed
(`~/.cache/ms-playwright/chromium-*`), and launching it with an explicit
`channel="chromium"` reproduces production's behaviour; that is how the
inline-PDF divergence was measured on 2026-08-09. Known consequence: the five
`/download/*` tests behave like production for four kinds, but `pdf-inline`
passes for the wrong reason. Production's Chrome renders an inline PDF into a
174-byte shell that tier-3 inference calls a block (`render_error`, 500).

The two fixes, neither built:
- make the workaround Windows-only (`sys.platform == "win32"`). Not worth filing
  upstream: upstream fixed it in `a1bd6c8`, on `develop` after v0.9.5, so a
  merge of `develop` brings it (`tasks/file-upstream-prs.md`);
- give the fixture a test-local explicit `channel="chromium"` override.

Either way, CI runs only the offline suites, not this one (see "Known limitations").

---

## Inside a built image: real Chrome, amd64

The only place our browser suite runs on production's browser. `az acr run` starts the image in
ACR's task infrastructure; nothing is deployed and the fixture origin is loopback, so there is no
third-party traffic beyond `pip install pytest`. ~6 min, a few cents. First done 2026-11-03.

```bash
az acr run --registry aitosoftacr --timeout 2700 --cmd 'aitosoftacr.azurecr.io/crawl4ai-service:<tag> bash -c "export HOME=/home/appuser CI=true PYTHONDONTWRITEBYTECODE=1; cd /tmp/project; google-chrome --version; pip install -q --user pytest pytest-asyncio; python -m pytest test-aitosoft/ -q -p no:cacheprovider -rf 2>&1 | tail -30"' /dev/null
```

- `HOME`: `az acr run` sets an unwritable one, and crawl4ai creates `~/.crawl4ai` on import.
- `CI=true`: the corpus is excluded from images since `.dockerignore` (2026-11-03), so the four
  `requires_corpus` tests skip.
- **Images up to `0.9.2-capacity-gate-2`** carry an unreadable `/tmp/project/.env` that makes
  python-dotenv raise in every test. Copy the tree without it first:
  `mkdir /tmp/p2 && cd /tmp/project && tar --exclude=./.env --exclude=./.env.txt -cf - . | (cd /tmp/p2 && tar xf -)`, then run from `/tmp/p2`.
- **Expected on real Chrome: `test_a_download_is_not_a_retryable_server_error[pdf-inline]` fails**,
  the production inline-PDF 500 described under "arm64 devcontainer". Everything else passes:
  69/70 on `0.9.5-candidate` (Chrome 156), 66/67 on `0.9.2-capacity-gate-2` (Chrome 151).

---

## Quality gates

| Gate | When | Bar |
|---|---|---|
| Offline suites (`pytest test-aitosoft/`) | before every deploy; after every upstream sync | all pass (332 on 2026-11-03, after the v0.9.5 merge). On a fresh clone the four corpus tests fail (they skip under CI); see "Known limitations" |
| Upstream security suite (`pytest deploy/docker/tests/test_security_*.py`) | after every upstream sync; after changing `deploy/docker/` | all pass, 1 xfail (316 + 1 on 2026-11-03) |
| Tier 1 regression | before every deploy | 4/4 |
| Post-deploy smoke | after every deploy | `/health` 200; unauthenticated `POST /crawl` → 401; check the new revision has 100 % of traffic **before** crawling (a mid-cutover smoke reported the old image on 2026-07-30; `az` commands are in `AZURE_OPERATIONS.md`); one authenticated `raw://` crawl → 200, `failure_class: "none"`. A made-up domain → 200, `success: false`, `origin_unreachable`, `DNS: host does not resolve`; it exercises the egress path without contacting anyone, and is what caught the 2026-08-05 `NameError` |
| Post-deploy SSRF negatives | after every deploy | `169.254.169.254` and `127.0.0.1:8080` still → 400 `URL blocked (SSRF protection)`. Only a host with no address at all moved to `origin_unreachable`; this proves the security verdict did not move with it. The made-up-domain probe logs a `Traceback` (`Crawl error:`) for the caught `OriginUnresolvable`. That is expected: judge the wire status, not the stack |
| Post-deploy byte-compare | after every deploy | one Tier 1 page's markdown (md5 or byte count) identical to a capture **you took pre-deploy**, from a local server running the same code. Pick a host the pre-deploy run hit only once, so this stays within rule 1's two hits. Never compare against a figure quoted in a doc: caverna.fi went from 1,210 to 532 chars of markdown between July and August. This shows the deployed image produces the same bytes on a real page, which a 200 does not |
| Upstream merge | after every sync | the above, plus the before/after comparison, plus `git diff upstream/develop...HEAD --stat -- crawl4ai deploy Dockerfile` listing only files in `AITOSOFT_FILES.md` (26 files, +4,880/−193 on 2026-11-03). Use three dots, which diff from the merge base. Two dots (`upstream/develop HEAD`) also count every upstream change since our last sync as our divergence: 352 files on 2026-11-03, with upstream 233 commits ahead |
| Stealth/browser changes | after changing stealth or browser flags | `test_fingerprint.py` against `stealth-v4/`, **currently broken** (see "Live CLI scripts") |
