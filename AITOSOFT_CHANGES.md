# Aitosoft Changes Log

This file tracks all modifications made to the crawl4ai fork for Aitosoft's internal use.
Keeping this log helps when syncing with upstream updates.

---

## Current State

**Last Updated**: 2026-07-17

### Version
- **Local**: v0.9.2 (upstream/develop 2026-07-16) + Aitosoft patches (see entries below)
- **Production**: v0.9.2 + render admission + static-mode hardening + single-URL contract guard + pool cleanup/re-init + patchright tidy + fence-504 observability (deployed 2026-07-17)
- **Docker Image**: `aitosoftacr.azurecr.io/crawl4ai-service:0.9.2-fence-obs` (revision `crawl4ai-service--0000030`, digest `sha256:9944c935...`)
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
- Offline suites green: test_mas_contract.py (8), test_admission.py (10), test_static_mode.py (10), test_crawler_pool.py (4), test_patchright_fallback.py (4)

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
