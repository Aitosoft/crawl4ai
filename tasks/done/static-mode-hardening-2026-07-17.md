# Static-mode hardening (SSRF redirect gap + robustness bundle)

**Status:** DONE — deployed + live-verified 2026-07-17
**Priority:** High — item 1 is the only real security gap found in the audit
**Effort:** S-M. **Risk:** low (behavior changes only for redirect-to-private targets and error paths).

## Goal

Bring `deploy/docker/aitosoft_static_mode.py` (and its api.py monitor hook)
up to the same egress/robustness posture as full mode.

## Items

1. **SSRF: re-validate redirects per hop.** The httpx client uses
   `follow_redirects=True` (aitosoft_static_mode.py:85-97) with no per-hop
   validation, while full mode routes Chromium through upstream's pinning
   egress proxy with `check_redirect` on every hop (egress_broker.py:150).
   A crawled public page 302-ing to `http://169.254.169.254/` (Azure IMDS)
   or an internal service would be fetched and returned to the caller.
   Fix: `follow_redirects=False` + manual loop (≤5 hops), validating each
   `Location` via upstream's `egress_broker.check_redirect`.
2. **Monitor records success on failure.** The static branch's `finally` in
   api.py (~line 697-706) always records `status_code=200` to the monitor
   even when every URL failed (found in the 2026-04-15 appendix review C1,
   never fixed). Record the real outcome so dashboards aren't skewed.
3. **Bound the fan-out.** `asyncio.gather` over all URLs
   (aitosoft_static_mode.py:267) is unbounded — a 100-URL request opens 100
   concurrent fetches. Add a semaphore (e.g. 10).
4. **Dead parameter.** `config: dict` on the entry function (:257) is never
   used — drop it or honor it.
5. **Import placement.** `from crawl4ai.html2text import HTML2Text` (:188)
   sits before the try in a function whose contract is "never raises" — an
   import failure would propagate through gather to a 500. Move to module
   scope (fail at boot, not per-request).
6. **Config knob.** `STATIC_FETCH_TIMEOUT_S = 15` (:35) is hardcoded; every
   comparable knob lives in config.yml. Move it there.
7. **Stale comment.** The `verify=False` comment (:87) cites
   "--ignore-certificate-errors in config.yml", which no longer exists.
   Rewrite the justification (static mode is deliberately lax on TLS for
   broken-cert SME sites — see tasks/tls-broken-cert-regression.md for the
   full-mode counterpart).

## Plan

1. Implement 1-7 in one pass (they all touch the same file + one api.py hunk).
2. Extend test_admission.py-style offline tests: redirect-to-private-IP is
   refused; failure path records non-200; gather bounded.
3. Tier 1 regression + a static-mode spot check (`test_site.py <domain>
   --render-mode static`), then deploy via `azure-deployment/deploy-image.sh`.

## Progress

- 2026-07-17: Task created. No code changes yet.
- 2026-07-17: All 7 items implemented:
  1. `follow_redirects=False` on the shared client + manual loop in
     `_fetch_static_one` (≤ `STATIC_MAX_REDIRECT_HOPS = 5` hops). Each
     `Location` is resolved against the current URL (`httpx.URL.join`,
     relative Locations work) and validated with
     `egress_broker.check_redirect` — the same rule full mode enforces.
     Refused redirect → inner `success:false` with opaque error_message
     `"static-fetch: redirect blocked (SSRF protection)"` (no target echo,
     egress_broker's oracle rule), HTTP 200 envelope preserved. >5 hops →
     `"static-fetch: too many redirects (>5)"`.
  2. api.py static-branch `finally` now records the real aggregate outcome:
     `status_code=200` only if ≥1 URL succeeded, else 502 +
     `error="static: all URL fetches failed"`. Envelope contract unchanged.
  3. Fan-out bounded by `asyncio.Semaphore(STATIC_FETCH_MAX_CONCURRENCY=10)`
     per batch.
  4. Dead `config` param dropped from `handle_static_crawl_request`
     (api.py call site updated).
  5. `HTML2Text` + egress_broker imports moved to module scope.
  6. `crawler.static_fetch_timeout_s: 15` added to config.yml; read once
     per process via `utils.load_config` (same pattern as
     aitosoft_admission's gate sizing), fallback default 15.
  7. `verify=False` comment rewritten: matches full-mode behavior (upstream
     hardcodes `--ignore-certificate-errors` into every Chromium launch),
     deliberate for broken-cert SME sites; cites
     tasks/done/tls-broken-cert-regression-2026-07-17.md.
- 2026-07-17: New offline suite `test-aitosoft/test_static_mode.py`
  (10 tests, httpx.MockTransport, IP-literal hosts so zero DNS/network):
  public→private + IMDS redirect refused (and never fetched), public→public
  and relative-Location followed, >5 hops refused, semaphore bound observed
  (peak ≤ 10 across a 30-URL batch), all-URLs-fail records non-200 monitor
  outcome (502), partial success records 200, prod client pinned to
  `follow_redirects=False`, timeout knob read from config.yml.
  Offline gates green: 25 passed (test_mas_contract 7 + test_admission 8 +
  test_static_mode 10). pre-commit (black, ruff, mypy) clean.
  Docs synced: TESTING.md (offline gates + quality-gates row), CLAUDE.md
  (offline suites line), AITOSOFT_FILES.md (api.py +99/−9, config.yml
  +45/−10, module description, post-merge checklist).

- 2026-07-17: Deployed image `0.9.2-static-hardening` (digest
  `sha256:f9f6c7b75f04...`, revision `crawl4ai-service--0000027`) via
  deploy-image.sh — ACR build 9m14s, env vars untouched, render-capacity
  invariant OK (config 2 == ACA http-renders rule 2).
- 2026-07-17: Live verification, all green:
  - `/health` → `{"status":"ok","version":"0.9.2"}`.
  - Static spot check `test_site.py caverna.fi --render-mode static` →
    200, 899 chars markdown.
  - Tier 1 regression `--version static-hardening` → **4/4 passed**
    (report: test-aitosoft/reports/static-hardening-regression-tier1.md).
  - Live SSRF probe: static crawl of
    `https://nghttp2.org/httpbin/redirect-to?url=http://10.0.0.1/` →
    inner `success:false, status_code:0, error_message:"static-fetch:
    redirect blocked (SSRF protection)"`, HTTP 200 envelope. Exactly the
    offline-test contract, confirmed in prod.
  - Probe deviation: httpbin.org itself was 503-ing (overloaded, redirect
    never issued → probe inconclusive) and httpbingo.org 403s datacenter
    IPs. Used the nghttp2.org httpbin mirror, which issues a real 302.

## Learnings

- httpx `Response.has_redirect_location` is the right redirect predicate
  (3xx AND Location present; excludes 304).
- egress_broker validation works offline in tests when targets are IP
  literals — `getaddrinfo` resolves them locally, no DNS.
- The monitor singleton is patchable via `monitor.get_monitor` because
  api.py imports it lazily inside the handler.
