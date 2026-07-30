# `antibot_detector` misses the challenge family that dominates Finnish SME crawling

**Status:** Open — implement the two measured signatures now; vendor
identification needs one stored HTML sample from MAS (asked for; not blocking).
**Priority:** High. It is a prerequisite for Q3's `blocked_suspect` being worth
anything, and MAS is about to gate a 15,000-company sweep on that field.
**Effort:** S. **Risk:** medium — this is block detection, where a false
positive costs a good page and a false negative poisons the corpus.
**Evidence:** MAS's corpus scan of 117,323 stored pages, `tmp/crawl4ai-reply-2.md` §3,
and `tmp/crawl4ai-affected-hosts.txt`.

## Problem

MAS scanned their entire corpus with our pattern list. It found **22 pages, of
which only 2 are genuine block pages.** The other ~15 are Shopify storefronts
whose accessibility skip-link points at `/pages/access-denied` — matched by our
Tier-2 `Access\s+Denied` pattern.

The signature that actually dominates is **not in our list at all**:

| body signature | pages in MAS corpus |
|---|---|
| `robot-suspicion.svg` (asset host `d1rozh26tys225.cloudfront.net`) + "Checking the site connection security" | **371** |
| "Checking your browser. This will only take a few seconds…" | 29 |
| our entire Varnish/Fastly/Incapsula/Access-Denied family, genuine hits | **2** |
| **total challenge pages stored as content** | **402** |

That is ~170× more common than everything we currently detect, across
**155 companies — 80 of which have a challenge screen as their entire captured
website.**

MAS's methodological note is worth carrying: their first scan used only our
pattern list, returned "2 affected pages", and nearly concluded the whole
redirect-block problem was negligible. Our list is borrowed from an Anglo-CDN
world and has a Finnish-market blind spot. Assume the same shape of gap exists
elsewhere in the detector.

## What to do

### 1. Add the two measured signatures

- `robot-suspicion` (the asset filename is the stable token; the CloudFront host
  `d1rozh26tys225.cloudfront.net` is a second, weaker one)
- `Checking the site connection security`

`Checking your browser` is **already** in `_TIER2_PATTERNS`, gated on
`_TIER2_MAX_SIZE = 10000`. Check whether MAS's 29 pages exceed that gate — if
so, the pattern is right and the size gate is what silenced it. Do not raise the
gate blindly; it exists to stop articles about bot-blocking matching.

### 2. Fix the Shopify `Access Denied` false positive

`/pages/access-denied` in a skip-link is not a block page. Tighten the Tier-2
`Access Denied` pattern so a bare URL path or link text does not match — require
it in a heading/title context, or exclude matches that occur only inside an
`href`. MAS's 15 false positives are the test cases.

### 3. Do not guess the vendor

Search did not identify what serves `robot-suspicion.svg`. Match the literal
signatures MAS measured rather than inventing a vendor family — a wrong vendor
guess produces a wrong pattern shape. We have asked MAS for one full stored
challenge HTML so a later session can identify it and generalise properly.

**Note we could not reproduce it live on 2026-07-30**: `magicad.com`
(classified `challenge_all`, 4/4 pages) returned clean content through both
static (12,304 B) and full (15,982 B) mode from our Azure egress. So the
challenge is **not** unconditionally applied to our IP — it is intermittent, or
was rolled back. That is consistent with MAS's `vaskisepat.fi` recovering on its
own. It also means **you cannot verify this against a live host**; use MAS's
stored bodies as fixtures.

## Verification

- Offline fixtures only, built from MAS's stored bodies (ask via Tero). Never
  live-test a host classified as blocked or challenged.
- Assert: the 371-page signature is detected; the Shopify skip-link case is
  **not**; existing Tier 1/2/3 cases are unchanged.
- Extend `test-aitosoft/` rather than upstream's tests — the pattern set is
  where our market knowledge lives and it will keep diverging from upstream's.
- Tier 1 regression 4/4.

## Downstream dependency

`blocked_suspect` in the Q3 preflight endpoint
(`tasks/preflight-batch-endpoint.md`) is only as good as this list. MAS said it
plainly: *"a preflight that misses the dominant failure is worse than none,
because it licenses the delete."* Do not ship the preflight before this.

---

## Implemented 2026-07-30

**1. The two measured signatures.** Both added to `_TIER1_PATTERNS`
(`crawl4ai/antibot_detector.py`): `robot-suspicion` and
`d1rozh26tys225.cloudfront.net`. Tier 1 because a hyphenated asset filename is
not prose — it cannot appear in real content, so no size or status gate is
needed and the 371-page family is caught however the vendor pads the page.
No vendor was guessed; the literals MAS measured are matched as literals.

**2. A third root cause, found while wiring the above.** The tier-2 list is only
ever evaluated on 4xx/5xx (`is_blocked`: the 403/503 branch, then
`status_code >= 400`). Challenge interstitials are overwhelmingly served with
**HTTP 200** — so `Checking your browser` had *never once been consulted for the
pages it was written for*. That, not `_TIER2_MAX_SIZE`, is what silenced MAS's
29-page family; the size gate was never reached. Answers the question the task
asked us to check, from the code rather than from their page sizes.

Closed with a new `_CHALLENGE_PATTERNS` tier, checked at **any** status:
`Checking the site connection security`, `Checking your browser`,
`<title>Just a moment`. Deliberately tiny — interstitial wording only, no
generic block phrases and no CAPTCHA-class markers, because a false positive
here now costs a real page.

**3. Two gates on that tier, not one.** The obvious gate (`_TIER2_MAX_SIZE`) is
not sufficient, and the test suite caught it: a 40-paragraph Finnish article
*about* bot protection, quoting every phrase in the list, is 8.2 KB — under the
10 KB gate. Size cannot separate a challenge screen from an article that
mentions one. Added `_CHALLENGE_MAX_VISIBLE_TEXT = 1500`: a real interstitial is
a few hundred characters of visible prose. Both gates now apply.

**4. The Shopify false positive.** `Access\s+Denied` →
`<(?:title|h[1-3])[^>]*>[^<]{0,60}Access\s+Denied`. Keeps the genuine Akamai
page (`<TITLE>Access Denied</TITLE><H1>Access Denied</H1>`, one of MAS's 2 true
positives) and drops navigation-link text. Real 403s lose nothing: the 403/503
branch already flags any non-data HTML body without consulting this pattern.

**Verified** — `test-aitosoft/test_antibot_challenge_detection.py`, 15 tests:
challenge family detected at 200/403/429/503/None and on a padded 20 KB page;
Shopify storefront clean at 200 and 404; Akamai and title-only Access Denied
still caught; the 8 KB and 20 KB articles clean; Cloudflare/Incapsula tier 1 and
the JSON-response exemption unchanged.

**Fixture provenance, stated plainly:** synthesised from the signatures MAS
measured, not from their stored bodies — those had not arrived. Live
verification is impossible by construction (§8d: `magicad.com`, classified
`challenge_all`, served clean content to our egress the same day) and would
burn requests against hosts already classified as blocked.

**Still open:** the request in §8e for one full stored challenge HTML. With it,
a later session can identify the vendor and generalise the pattern properly
instead of matching artefacts. Until then this is coverage, not understanding.
