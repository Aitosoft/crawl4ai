# The challenge family may be a capture-timing bug, not an egress block

**Status:** Open — **experiment first, feature second.** Nothing may be built
before phase 1 produces a number.
**Priority:** Highest of the open work. It is cheap, it is the only thing that
can retire `residential-egress-retry-path.md` for free, and MAS is about to
change their capture config across ~15,000 companies partly because of it.
**Effort:** S (phase 1), M (phase 2, only if phase 1 says yes). **Risk:** none
in phase 1.
**Evidence:** `tmp/mas-repo-messages/07-from-us-243-host-rescrape.md` §2, §4, §5;
`tasks/waa-eval-2026-07-30-forensics.md` §1, §8b, §8d.

## The observation that started this

MAS re-scraped their 243 affected hosts against `0.9.2-failure-class` and found
(their §5) that **36 of 243 responses carried origin status `202`, and 100 % of
them came from the challenge families.** Not one `empty_*` or `blockpage_*` host
ever returned 202. Within that population the same 202 was serving four
different things: a challenge screen (19), a block page (4), the real site (10),
and an empty body (3).

A single status code that answers with the interstitial *and* with the real
content is the signature of a **JS challenge that resolves into the real page**.
AWS documents exactly this shape for its WAF Challenge action: HTTP **202**, a
JavaScript interstitial, a token, and then *the challenge script resubmits the
original request*
(<https://docs.aws.amazon.com/waf/latest/developerguide/waf-captcha-and-challenge-actions.html>).
Blackwall/BotGuard — resold transparently by European hosting providers, which
would explain a whole cohort of Finnish SME sites acquiring a challenge in the
same month — has the same interstitial-then-redirect shape.

## The hypothesis

**We capture the interstitial instead of the page it turns into.**

MAS's V14 config is `wait_until: "domcontentloaded"` + `delay_before_return_html:
2.0`. A challenge that runs JS, obtains a token and resubmits the request needs
the page to *navigate again* after `domcontentloaded`. Two seconds may or may not
be enough, which is precisely the observed pattern: the same 202 returning an
interstitial on some hosts and real content on others.

Three independent observations already fit it and were previously read another
way:

- Forensics §1: `delay_before_return_html: 2.0` was the trigger for
  `maitokolmio.fi`'s `page.content()` race — because *a navigation commits after
  domcontentloaded*. That is the same mechanism seen from the failure side.
- Forensics §8d: 5 of 5 challenge hosts probed from our Azure egress returned
  clean content. Read then as "the challenge was withdrawn". It reads at least as
  well as "the challenge resolved before we captured".
- MAS §2: `challenge_all` hosts came back 108/117 clean while `challenge_partial`
  came back 25/54 clean — a per-page rather than per-host split, which is what a
  race produces and what a standing IP block does not.

**If the hypothesis holds, 23 of the 31 hosts currently reported `origin_blocked`
are recoverable with a wait, at zero cost, and the residential-proxy case shrinks
to the 4 hosts serving a hard 403 template.**

If it does not hold, we have spent one session and closed a hypothesis that would
otherwise have kept re-appearing.

## Phase 1 — the experiment (no code)

Against **3 hosts**, chosen from the 23 `robot-suspicion` hosts in MAS's
`origin_blocked` list, **2 requests each** (see site-safety below).

| Cell | `wait_until` | `delay_before_return_html` | Asking |
|---|---|---|---|
| 1 | `domcontentloaded` | 2.0 | reproduce MAS's result — do we get the interstitial? |
| 2 | `networkidle` | absent | does the challenge resolve if we let it? |

Record for every cell: `status_code`, `redirected_status_code`, `failure_class`,
`len(html)`, `len(cleaned_html)`, `len(markdown)`, elapsed, and whether the body
carries `robot-suspicion`.

Also capture **one full interstitial body** and answer, from the markup, the
question the forensics record has been unable to answer since §8e: **which vendor
is this?** Grep the stored HTML for `awswaf`, `token.awswaf.com`, `botguard`,
`blackwall`, `challenge-platform`, and for whatever script fetches
`d1rozh26tys225.cloudfront.net`. The asset host is a CloudFront distribution over
an S3 bucket (verified 2026-07-31: `server: AmazonS3`, `*.cloudfront.net` cert,
no owner information in TLS) so it identifies nothing by itself — the page markup
will.

Phase 1 is done when the report says either "cell 2 returns the real page" or
"cell 2 returns the interstitial too", with the vendor named or explicitly
recorded as still unidentified.

### Site safety — read before running

These are customer sites MAS has classified `challenge`, and
`TEST_SITES_REGISTRY.md` carries a standing rule against live-testing them. This
task is a **deliberate, bounded exception** of the same kind already logged for
the WAA eval: 3 hosts, 2 hits each, six page loads total. Do not extend the
matrix "while we are here". Add the hosts and hit counts to the burned-hosts
table in `TEST_SITES_REGISTRY.md` in the same session, and prefer hosts MAS has
already re-hit this week over fresh ones.

## Phase 2 — the feature, only if phase 1 confirms

The naive fix is to raise `delay_before_return_html` globally. **Do not propose
that.** MAS is already considering 10 s on their side; at ~120,000 fetches per
sweep that is ~267 render-hours of added browser time landing on replicas whose
measured capacity is 2 concurrent renders. A global sleep pays the cost on every
page to rescue a small minority.

The shape that fits what we already have is **detect-then-re-capture, inside the
same render**:

1. Capture as today (`domcontentloaded` + whatever the client asked for).
2. Run the checks we already own — `antibot_detector.is_blocked`'s challenge tier
   (shipped 2026-07-30) and the collapse ratio from
   `tasks/cleaned-html-collapse-guard.md`.
3. If either fires *and* wall-clock budget remains, wait and re-capture rather
   than returning the interstitial. Bounded, logged, at most once.

This is the same settle-and-retry idea already in our `_capture_html` patch, so
it lands in code we own and does not widen the upstream delta. It also costs
nothing on the ~97 % of pages that capture cleanly first time.

Open design questions for phase 2, to be answered with phase 1's data, not now:
how long to wait, whether `networkidle` is safe as a second attempt on sites with
long-polling, and whether the re-capture should be attempted for the collapse
class as well as the challenge class.

## What this does *not* cover

The 4 hosts serving an 80,671-byte `403 - Forbidden` template are a Block action,
not a Challenge action. No amount of waiting resolves those. They belong to
`residential-egress-retry-path.md` and are the honest denominator for it.

## Interaction with MAS

Their §1 conclusion — that `revisol.fi` needed 8 more seconds — is the same
mechanism seen on a non-challenge host, and their planned fix (raise the capture
wait) would work but would tax every page. Phase 1's result decides whether we
can offer them an adaptive fix instead. **Send the finding before they roll their
config change out**, not after. Their decision, their repo; ours is to make sure
they have the 202 evidence first.

## Verification (phase 2)

- Offline: a fixture serving an interstitial that turns into content must produce
  the content; one that never resolves must still produce `origin_blocked`.
- Assert the re-capture is bounded and cannot push a request past the wall-clock
  fence — this is the exact failure mode `done/render-retry-unbounded-hang.md`
  paid for.
- Assert the happy path never re-captures (a counter in the response or the log).
- Tier 1 regression 4/4 with wall-clock recorded, to prove the happy path did not
  get slower.
