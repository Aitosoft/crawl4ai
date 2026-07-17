# Verify + resolve: broken-cert sites likely fail in full mode since v0.9.2

**Status:** Done (2026-07-17). Verified — NO regression exists; no env change
made. Coordinator signed off same day: the fragility re-check is now a line
in AITOSOFT_FILES.md's upstream-sync checklist, and the antibot minimal_text
side observation got its own task (tasks/antibot-minimal-text-false-positive.md).
**Priority:** High — silent crawl failures on SME sites are exactly MAS's use case
**Effort:** S. **Risk:** none (investigation + doc change only).

## Problem (as filed — see Findings for the correction)

`AITOSOFT_CHANGES.md` (ignore_https_errors note) and a config.yml comment
claim broken-cert sites still crawl because `ignore_https_errors` defaults
true at the Playwright-context level. The 2026-07-17 audit read
`enforce_egress` (`deploy/docker/egress_broker.py:191`) forcing
`ignore_https_errors = False` on every /crawl browser config unless
`CRAWL4AI_ALLOW_INSECURE_TLS=true` (not set on the Container App) and
concluded broken-cert sites likely fail in full mode.

## Findings (2026-07-17, verified against prod)

**The audit's conclusion was wrong. There is no TLS regression.** The
original pre-0.9.2 claim ("broken-cert sites still crawl") holds in effect,
but via a different mechanism than either doc stated:

- Upstream hardcodes `--ignore-certificate-errors` +
  `--ignore-certificate-errors-spki-list` into every Chromium launch:
  `crawl4ai/browser_manager.py` `build_browser_flags()` (line ~79, used by
  the `launch_persistent_context` path) and `ManagedBrowser._build_browser_args()`
  (line ~1066, CDP path). A launch flag disables cert validation
  process-wide — the browser's network stack accepts the bad cert before
  Playwright's context-level `ignore_https_errors` is ever consulted.
- So `enforce_egress` forcing `ignore_https_errors = False` is **moot** on
  the browser path. Its flag-scrubbing (`_DANGEROUS_BROWSER_ARGS`) only
  filters caller-supplied `extra_args`, not upstream's generated launch
  flags. This applies equally to requests with and without `browser_config`
  (MAS-style requests use the same launch machinery).

### Live evidence (prod, 2026-07-17)

1. **Full mode, `https://expired.badssl.com/`** → HTTP 500, but NOT TLS:
   container logs (cid `b6fd1ec3c6c3`) show the fetch **succeeded**
   (`↓ ... ✓ 0.78s`, 490 bytes, 18 chars visible = "expired.badssl.com" —
   the real page). The 500 came from the antibot structural heuristic:
   `Blocked by anti-bot protection: Structural: minimal_text on small page`,
   then the patchright fallback fetched the same content and was flagged the
   same way → server error 500.
2. **Static mode, same URL** → HTTP 200, success, markdown
   `# expired. badssl.com` (httpx `verify=False`).
3. Both engines (pool Chrome + patchright) loaded an expired-cert page ⇒
   cert validation is off in full mode today, without
   `CRAWL4AI_ALLOW_INSECURE_TLS`.

## Decision

**`CRAWL4AI_ALLOW_INSECURE_TLS` deliberately left UNSET.** The pre-approved
plan (set it if full mode fails on the expired cert) was conditioned on a
TLS failure that does not exist; setting it would change nothing (it only
gates the already-moot context-level setting). Container App env untouched.

Docs fixed instead (both listed in this task's original plan):
- `AITOSOFT_CHANGES.md`: CORRECTION note resolved with the verified mechanism.
- `deploy/docker/config.yml`: comment now cites the hardcoded launch flags,
  not the context-level default.

## Side observation (out of scope here, flagged for triage)

Full mode returns 500 for ANY legitimately tiny page: the antibot
`minimal_text` structural heuristic (`antibot_detector.py`) flags small
low-text pages as block pages, patchright retries, still "blocked", request
fails. Static mode has no such check and returns the content. Real SME sites
are unlikely to be this small, but it is a false-positive class worth its own
task if MAS ever reports it.

Fragility note: if upstream ever drops the hardcoded
`--ignore-certificate-errors` launch flags (they are a known fingerprinting
signal — `navigator.webdriver`-class cleanups have removed such flags
before), full-mode TLS verification would silently turn ON via
`enforce_egress`, and `CRAWL4AI_ALLOW_INSECURE_TLS=true` would then be
needed. Re-check this on every upstream sync (grep
`ignore-certificate-errors` in `browser_manager.py`).

## Progress

- 2026-07-17: Task created from audit finding (code-reading only).
- 2026-07-17: Verified live against prod. No TLS regression — expired-cert
  page downloads in full mode; failure signature predicted by the audit
  (full fails / static works) does occur on expired.badssl.com but for an
  unrelated reason (antibot minimal_text false positive on tiny pages).
  Env var NOT set. Docs corrected. MAS-side evidence: none arrived this
  session (consistent — MAS would not have seen TLS failures, because there
  are none). Reported back for coordination.
