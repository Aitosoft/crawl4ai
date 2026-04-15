# Appendix — Implementation Quality Review

**Reviewer:** Claude (independent review pass, 2026-04-15)
**Scope:** Code changes summarized in the implementation report against the
spec in `static-html-fallback-mode.md`. Review based on source inspection of
`deploy/docker/schemas.py`, `deploy/docker/api.py` (lines 60–330, 840–1080),
`deploy/docker/server.py` (lines 25–178, 810–878), and
`test-aitosoft/test_site.py`. No runtime re-verification was performed.

---

## Verdict

Ship-ready, with a few small follow-ups worth noting before the MAS campaign
relies on this path at scale. The implementation adheres to the spec, keeps
the full-mode path completely untouched in behavior, and goes slightly beyond
the spec in the one place it had to (decoy stripping for roadscanners.com).

---

## What is solid

### 1. Scope discipline
The diff touches exactly the files the spec named — schemas, api.py,
server.py, the test CLI, and the change log. No new endpoint, no refactor of
the full-mode branch, no changes to `crawler_pool.py`, patchright retry, or
the Fix-1 timeout fence. That matches the explicit "do not risk the
production-proven stack" constraint. Reasoning: blast radius stays bounded to
a new, opt-in code path.

### 2. Correct placement of the static short-circuit
Two defensive layers:
- `server.py` (line 838) intercepts `render_mode == "static"` **before** the
  stream check and **before** the `all(not result["success"]) → HTTP 500`
  rewrite. This is what preserves the "HTTP 200 + inner success=false"
  contract in the spec's error section.
- `handle_crawl_request` (line 888) has its own branch that dispatches to
  `handle_static_crawl_request` immediately after URL normalization. This
  protects any future caller that invokes `handle_crawl_request` directly
  (e.g. tests, job runner) without routing through `server.py`.

Reasoning: the server-level branch is load-bearing (it's what makes the 500
rewrite not apply). The inner branch is belt-and-suspenders. Redundant but
cheap, and defensive in a codebase where `handle_crawl_request` is a fairly
public function.

### 3. `render_mode` tagging on both paths
Every response — static OR full — carries `render_mode`. Full-mode tags at
line 1067 (per-result) plus a fallback tag at 1077 on the error-path
dict-build. Spec called this out as a non-trivial requirement ("not just
static"); honored.

### 4. Hidden-decoy stripping (beyond spec)
Without `_strip_hidden_decoys` the spec's own acceptance check would have
failed: roadscanners.com injects a hidden `<span class="oe_displaynone">null
</span>` between the user and domain parts of every email, so naive
html2text produces `name@nullroadscanners.com`. The BS4 pass removes:
- `<script>`, `<style>`, `<noscript>`, `<template>` (conservative; these are
  already dropped by html2text but cleaning them here keeps whitespace sane)
- Inline `style="display:none"` / `visibility:hidden`
- Conservative class allowlist: `oe_displaynone`, `d-none`, `is-hidden`,
  `sr-only`, `visually-hidden`

Reasoning: this is the right layer — html2text has no CSS model, and writing
a CSS-aware pass would explode scope. The class list is scoped to well-known
utility conventions, which limits false-positive surface.

One edge-case caveat noted below under Concerns.

### 5. HTTP client lifecycle is correct
Module-scope `httpx.AsyncClient`, lazy-initialized with double-checked
locking (`_static_http_client_lock`), closed from the FastAPI lifespan at
`server.py:175`. Matches the spec's open-question guidance verbatim ("reuse
a module-scope client … or lazy-init'd at first use and closed in the
FastAPI lifespan shutdown"). Not per-request, which would burn sockets under
the ~2,000-companies/night campaign load.

### 6. Error-handling contract is precise
`_fetch_static_one` catches three layered exception classes
(`httpx.TimeoutException` → `httpx.RequestError` → bare `Exception`) and
encodes each into the error-shape dict from the spec. The function cannot
raise, which is why `asyncio.gather(...)` is called without
`return_exceptions=True`. Clean.

The `html2text` failure fallback (return raw HTML as markdown, still
success=true) matches the spec's "wrap in try/except … on failure still
return success: true" open-question guidance.

### 7. UA parity with full mode
`_get_static_user_agent()` reads the UA from config.yml via `load_config()`
and falls back to a hardcoded Chrome UA. This matters for target sites that
fingerprint both paths — MAS could otherwise see different block behavior
between static and full. Reasoning: a static fallback that looks like a
different client is a weaker fallback.

### 8. Response shape parity
Top-level envelope (`success`, `results`, `server_processing_time_s`,
`server_memory_delta_mb`, `server_peak_memory_mb`) matches full mode, so
MAS's existing monitoring queries and client branching continue to work
untouched. Spec called this out explicitly.

### 9. Test CLI surface is minimal and correct
`test_site.py --render-mode {full,static}` with default `full`. Only adds
the `render_mode` field to the payload when non-default — so existing calls
produce byte-identical payloads. Good regression hygiene.

---

## Concerns and improvement opportunities

Ordered by significance; none of them block shipping.

### C1. Monitor reports static failures as success=True
`handle_crawl_request`'s static branch (api.py:888–899) unconditionally
calls `track_request_end(request_id, success=True, status_code=200)` in its
`finally`. If every URL in a static batch failed (e.g. the host is
completely unreachable), the outer HTTP is still 200 — which is correct per
the spec — but the monitor will record this as a success. This will skew
any dashboard that counts static failures.

**Why it's minor:** MAS observes failures via the inner `success: false`
payload, not via our monitor. Dashboards can be corrected later by inspecting
`results[*].success`. Still worth a follow-up: compute `any_success =
any(r["success"] for r in results)` and pass that instead of a hardcoded
`True`.

### C2. No concurrency cap inside `handle_static_crawl_request`
`asyncio.gather(*(_fetch_static_one(u) for u in urls))` runs up to 100 HTTP
GETs concurrently (the schema caps `urls` at 100). Against a single target
host that's effectively a small burst, and httpx reuses the connection pool
so socket exhaustion is unlikely. But under the MAS campaign, nothing
prevents a caller from sending 100 URLs against one site and triggering
rate-limit / soft-block responses that would not have happened serially.

**Why it's minor:** MAS's current pattern is 1 URL per request. The
100-URL batch is a theoretical upper bound. If usage patterns shift, add an
`asyncio.Semaphore(10)` or equivalent.

### C3. `sr-only` and `visually-hidden` class stripping is slightly aggressive
Both classes are commonly used for a11y content that IS meant to be read
(just by screen readers, not visually). In practice these hold
skip-navigation links and form labels, rarely contact data — so the
false-positive risk to the use case is low. But a site that puts "Contact
us at …" inside an `sr-only` span for accessibility reasons would have that
content silently removed from the markdown.

**Mitigation if this bites:** drop `sr-only` and `visually-hidden` from the
class list; `oe_displaynone` + `d-none` + `is-hidden` cover the known decoy
patterns.

### C4. `verify=False` on the shared httpx client is documented but broad
It applies to every static fetch, not just hosts with known-broken TLS. The
spec's justification ("match `--ignore-certificate-errors` in config.yml")
is legitimate, but full mode at least has a browser sandbox around it;
static mode reads bytes directly into the Python process. Realistic attack
surface is low (we're GETting public marketing pages), but worth
acknowledging as a conscious tradeoff, not an oversight.

### C5. `/crawl/stream` silently ignores `render_mode: "static"`
`CrawlRequestWithHooks` inherits from `CrawlRequest`, so the stream
endpoint accepts the field but never short-circuits on it — the client
would get a Playwright-backed streaming response, not an error. Spec
explicitly said "do not touch `/crawl/stream`", so this is behavior by
omission, not a bug. But it's an easy footgun for a future MAS client. A
one-line `raise HTTPException(400, "render_mode=static not supported on
streaming endpoint")` in the stream handler would make the contract loud.

### C6. `resp.text` charset handling
httpx uses the Content-Type charset header when present and falls back to
UTF-8. For older sites that serve misdeclared encoding (e.g. ISO-8859-1
content labeled UTF-8), we'd get mojibake in the markdown. Full mode goes
through the browser, which handles this natively. Low-frequency issue, but
worth a note: if a specific Finnish site shows garbled characters in static
mode, the fix is `resp.encoding = resp.apparent_encoding` (requires adding
chardet or using httpx's built-in detection).

### C7. No static-mode coverage in `test_regression.py`
The regression harness only exercises full mode. Spec made this optional
("the goal here is non-regression of the full-mode path"), and the
`test_site.py --render-mode static` CLI is sufficient for ad-hoc checks.
But once the MAS campaign starts depending on static mode, a static-mode
Tier-2 site set (roadscanners + 1–2 other SPA hosts with known contact
data) would catch regressions in the `_strip_hidden_decoys` class list or
html2text behavior across future crawl4ai upgrades. Follow-up task, not a
blocker.

### C8. Minor: `_get_static_user_agent` re-imports `load_config` on every call
The import is inside the function and the config is re-read every time the
client is lazy-initialized. Since this runs at most once per process, it's
fine in practice, but a module-level `_CACHED_UA` would be cleaner.

---

## Things I specifically checked and am satisfied with

- Full-mode response shape unchanged (line 1081–1087 envelope is the
  pre-existing one, plus `render_mode: "full"` added per-result).
- `release_crawler` is NOT called on the static path — correct, since no
  crawler was acquired.
- Static branch runs BEFORE `BrowserConfig.load(browser_config)` at
  api.py:901, so a malformed `browser_config` from the client cannot fail a
  static request. This matches the spirit of "static should be the
  bulletproof fallback."
- `asyncio.wait_for(..., timeout=CRAWL_REQUEST_TIMEOUT_S)` (Fix 1) is NOT
  applied to the static path. Correct — `STATIC_FETCH_TIMEOUT_S=15` is the
  per-URL cap and there's no browser that could leak a pool slot.
- `render_mode` default in `CrawlRequest` is `"full"`, so every existing
  MAS payload routes to the existing behavior with no change.
- Pydantic `Literal["full", "static"]` will reject unknown values with a
  422, which matches the implementation report's claim of "invalid →
  correct" parse behavior.

---

## Recommended follow-ups (none blocking)

1. Fix the monitor success-tag on the static short-circuit (C1).
2. Explicit 400 on `/crawl/stream` when `render_mode == "static"` (C5).
3. Add a static-mode tier to `test_regression.py` once the feature is
   in-use (C7).
4. Revisit the hidden-class list if any site reports missing content (C3).

None of these affect correctness of the launched feature. The path as-built
gives MAS the bounded, deterministic fallback the spec called for.
