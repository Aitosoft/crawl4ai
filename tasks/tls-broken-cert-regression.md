# Verify + resolve: broken-cert sites likely fail in full mode since v0.9.2

**Status:** Open (created 2026-07-17 from the repo audit)
**Priority:** High — silent crawl failures on SME sites are exactly MAS's use case
**Effort:** S. **Risk:** none (investigation + env/doc change).

## Problem

`AITOSOFT_CHANGES.md` (ignore_https_errors note) and a config.yml comment
claim broken-cert sites still crawl because `ignore_https_errors` defaults
true at the Playwright-context level. **Both are stale post-0.9.2:**
upstream's egress broker (`deploy/docker/egress_broker.py:192`,
`enforce_egress`) forces `ignore_https_errors = False` on every /crawl
browser config unless `CRAWL4AI_ALLOW_INSECURE_TLS=true` — and that env var
is not set on the Container App (verified 2026-07-17: env is only
CRAWL4AI_API_TOKEN, ENVIRONMENT, LOG_LEVEL, MAX_CONCURRENT_REQUESTS,
GUNICORN_BIND).

Static mode is unaffected (its httpx client uses `verify=False`), so the
failure signature would be: full render of a broken-cert site fails, static
fallback of the same site works.

## Plan

1. Find a known broken-cert Finnish SME site (or stand one up via a test
   endpoint like badssl.com — expired.badssl.com is fine for the mechanism
   check and is not a customer site).
2. Crawl it in full mode against prod. If it fails with a TLS error:
   - Decide: set `CRAWL4AI_ALLOW_INSECURE_TLS=true` on the Container App
     (restores documented v0.8.x behavior; we're a single-tenant internal
     service, MITM risk accepted) — or keep verification and notify MAS
     that broken-cert sites now require `render_mode: "static"`.
3. Either way, fix the stale claim in AITOSOFT_CHANGES.md and the config.yml
   comment, and record the decision here.
4. If the env var route is chosen: `az containerapp update -n crawl4ai-service
   -g aitosoft-prod --set-env-vars CRAWL4AI_ALLOW_INSECURE_TLS=true`
   (additive — does not touch other env vars).

## Progress

- 2026-07-17: Task created from audit finding. Not yet verified against a
  live broken-cert site (audit was code-reading only).
