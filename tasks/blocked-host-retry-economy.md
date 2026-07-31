# Hard-blocked hosts cost ~12 page loads per company

**Priority lowered 2026-07-31.** The "~12–16 page loads per company" figure below
assumed MAS retries our failures three times. Since `failure_class` shipped they
receive origin-class failures as HTTP 200 + `success: false`, which their retry
policy treats as terminal — so a blocked host now costs **~4 page loads, once**.
The remaining win is levers 1 and 3 (skip patchright on a reputation block: 4 → 2)
plus the per-host memo, and the classifier is still what
`residential-egress-retry-path.md` triggers on. Real, smaller, no longer urgent.
Re-read after `tasks/challenge-interstitial-resolve.md`, which may reclassify most
of the population out of "blocked" entirely.

**Status:** Open — ready to implement, no external input needed.
**Priority raised 2026-07-30:** `tasks/redirect-status-blinds-block-detection.md`
shipped, so every redirect-to-block host now takes this path too (measured
~13 s and 4 page loads per request, up from 1). Pinned by
`test-aitosoft/test_redirect_block_detection.py::test_blocked_result_costs_one_page_load_per_attempt`.
This is also the residual that lets a slow+blocked host still reach the 180 s
fence, because the patchright tier gets its own `total_timeout` budget.
**Priority:** Medium. Not a correctness bug; a cost, latency and politeness bug
that also makes us look worse to the blocking edge over time.
**Effort:** S-M. **Risk:** low, but see the false-negative warning below.
**Evidence:** `tasks/waa-eval-2026-07-30-forensics.md` §2a

## Problem

When an origin hard-blocks our egress IP, we spend a lot of requests proving it
repeatedly. Observed on `konecranes.com`, prod logs 2026-07-30 12:21–12:23:

Per `/crawl` request:
1. first-tier fetch (real Chrome + stealth) → 403
2. upstream anti-bot retry 1/1 → 403
3. patchright fallback fetch (undetected-chromium) → 403
4. patchright's own anti-bot retry → 403 → `[patchright] STILL blocked`

= **4 page loads, ~13 s** per request. MAS then retries (500/502/503 are
retryable on their side, 3 attempts), so one company costs **~12–16 page loads
against a host that has already said no four times.**

The logs show exactly this: eight full block cycles for `www.konecranes.com`
inside 60 seconds.

The patchright tier is the wasteful part, and we have proof it cannot help
here: httpx, real Chrome + playwright-stealth, and undetected-chromium all
receive the same Fastly 403. Two different browser engines getting identical
treatment means the decision is made on IP/ASN reputation before fingerprinting
matters. Patchright is the right tool for a *fingerprint* block; it is dead
weight for a *reputation* block.

## Direction

Three independent levers; do 1 and 2, consider 3.

### 1. Don't run patchright when the block cannot be a fingerprint block

`aitosoft_patchright_fallback.maybe_retry_blocked` fires whenever
`error_message` contains `"Blocked by anti-bot protection:"`. Narrow it.

A block page served by a CDN edge (Varnish/Fastly/Akamai signature in the body,
`cf-ray`/`x-served-by`/`Via` headers, `Error 54113`-style Fastly codes) with a
tiny body and no JS challenge is a reputation block. A Cloudflare *interstitial*
/ JS challenge / Turnstile page is a fingerprint block, and that is exactly what
patchright exists for.

Distinguish them and skip the retry for the first class. Halves the cost per
blocked request and removes two hits from the target.

Care: `antibot_detector` already has the pattern table (`crawl4ai/antibot_detector.py`
~55-117) — reuse it rather than writing a second classifier.

### 2. Per-host block memo (short TTL, per replica)

Once a host has hard-blocked both tiers, remember it for a few minutes and
short-circuit subsequent requests to an immediate blocked result. Bounded dict,
TTL ~5–15 min, per replica (no shared state — replicas are ephemeral and a
per-replica memo is enough to kill the retry storm within one MAS batch).

Interacts with `tasks/origin-vs-crawler-failure-classification.md`: the memoed
answer should carry the same `failure_class` so MAS stops retrying too. Without
that MAS-side change this only saves *our* page loads, not their requests —
still worth it.

**False-negative warning:** a memo is a cache of a negative result. If a host
blocks transiently (rate limit, deploy), we will keep reporting it blocked for
the TTL. Keep the TTL short, key it on host + block class, and log every memo
hit so the behaviour is attributable. Do not persist it across restarts.

### 3. Consider dropping the retry budget for known-blocked classes

`max_retries` comes from MAS (V14 sends 1). For a confirmed reputation block,
one attempt is as informative as two. This overlaps with #1; only do it if #1
proves insufficient.

## What this does NOT fix

Nothing here makes konecranes crawlable. That needs non-datacentre egress —
see `tasks/residential-egress-retry-path.md`, which depends on this task's
classifier as its trigger. This task only stops us paying 12 page loads to
learn what we knew after the first one.

## Verification

- **Do not live-test against konecranes or any known-blocked host** (site-safety
  rules; and hammering a host that already blocks us is the exact behaviour
  this task removes). Use recorded block-page fixtures — capture them once from
  the existing prod logs / the 425-byte Varnish body already observed.
- Extend `test-aitosoft/test_patchright_fallback.py` with the classification
  cases: Fastly/Varnish 403 ⇒ skip patchright; Cloudflare JS challenge ⇒ run it.
- Assert the memo expires and that a memo hit is logged with the host.
- Tier 1 regression 4/4 (none of them are blocked, so this should be a no-op
  there — that is itself the check).
