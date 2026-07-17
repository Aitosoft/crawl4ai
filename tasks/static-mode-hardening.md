# Static-mode hardening (SSRF redirect gap + robustness bundle)

**Status:** Open (created 2026-07-17 from the repo audit)
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
