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

**The instrument exists as of 2026-07-31 — phase 1 costs zero live requests.**
`tasks/done/fixture-origin.md` shipped these routes, all at HTTP 202 and all
with the resolve delay as an argument:

| Route | Serves |
|---|---|
| `/challenge/resolve-after/{s}` | interstitial → content by DOM rewrite |
| `/challenge/resolve-by-nav/{s}` | interstitial → content by top-level navigation (also forensics §1's `page.content()` race) |
| `/challenge/never` | the control — waiting longer must not rescue it |
| `?marker=robot-suspicion\|checking-browser\|none` | which family, or none at all |

`test_fixture_origin.py` already pins both halves of the premise: at a 0.1 s
capture wait the interstitial is what we store (`origin_blocked`, status 202);
at MAS's 2.0 s a challenge that resolves in 0.5 s gives the real page — **at the
same 202**. So the shape is confirmed reproducible; what phase 1 still owes is
the number, against the real families. Use the fixture to settle every
mechanism question (does a longer wait help? does the nav race lose the
capture? does an adaptive wait beat a global one?) and spend live requests only
on "do these specific hosts behave like the fixture".

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

## Phase 1 — the experiment, and it needs **no live sites at all**

An earlier draft of this task proposed six page loads against MAS's customer
hosts. That was wrong, and the reason it was wrong generalises: the question
"does our pipeline capture the interstitial instead of the page it becomes" is a
question about **our pipeline**, and it is answerable against an origin we
control.

**The instrument is built. Do not build it again** — `tasks/done/fixture-origin.md`
shipped on 2026-07-31 and `test-aitosoft/fixture_origin.py` is in the tree. The
routes are the ones in the table at the top of this file, and the resolve delay
is a path argument in seconds, so a sweep over waits is a loop, not new code:

```python
production_path.crawl(
    fixture_origin.url("/challenge/resolve-after/2.5", marker="robot-suspicion"),
    delay_before_return_html=2.0,          # MAS's current value
)
```

`test_fixture_origin.py` already pins the two endpoints of that sweep — a 0.1 s
wait against a late resolve stores the interstitial, and a 2.0 s wait against a
0.5 s resolve stores the real page, both at HTTP 202. **The premise is settled;
phase 1 owes the shape of the curve between them, and four numbers:**

| Question | How | Why it decides something |
|---|---|---|
| Where does the capture start winning? | Sweep resolve delay against `delay_before_return_html`; both routes | This is the number MAS is holding their design for |
| Does `resolve-by-nav` differ from `resolve-after`? | The two parametrized routes, same grid | A top-level navigation replaces the execution context — forensics §1's `page.content()` race. If nav loses captures that DOM-rewrite keeps, a global wait cannot fix it and the adaptive shape is forced |
| What does a wall cost? | `/challenge/never` at the candidate waits | The control. If waiting longer taxes hosts it can never rescue, that is the whole argument against a global number, in seconds |
| Does an adaptive re-capture beat a global wait? | Detect-then-re-capture (phase 2's shape) vs a raised global value, same grid | Phase 2's go/no-go |

Run everything through the **full production path** (`production_path.crawl` —
`aitosoft_entry` + `api.handle_crawl_request`, MAS's V14 config) and record
`status_code`, `failure_class`, `len(html)`, `len(cleaned_html)`,
`len(markdown)`, elapsed. Units: `html`/`cleaned_html` are HTML **bytes**,
`markdown` is markdown **characters** — MAS's `DEGENERATE_CAPTURE_CHARS = 500`
is the second one, and mixing them has already cost a round trip.

**Read the result against MAS's actual position** (their message 09 §6, so the
number lands in the frame they will read it in):

- Their current `delay_before_return_html` is **2.0**. The change they refuted
  was 2.0 → 0.1, not a raise.
- Their own `raw://` measurement says **2.0 tolerates a paint up to roughly
  3–5 s**. So a curve that only starts winning past ~5 s is a finding about
  *their* config; one that wins below it is a finding about *ours*.
- They have **not** shipped a global wait and will not until this lands either
  way. They had already concluded the replacement must fix the 180 s hang
  **without shortening the paint window** — so per-host or adaptive, not a bigger
  global number. An adaptive result is the one they can use.

**The result is decisive in both directions and neither branch costs a page load:**

- If we capture the resolved content already → the hypothesis is dead, this task
  closes, and `residential-egress-retry-path.md` keeps its 31-host population.
- If we capture the interstitial → that is a real defect in our capture timing,
  worth fixing whatever vendor is on the other end, and phase 2 proceeds.

### Done when

1. The numbers and the curve are in this file, with the grid that produced them.
2. A **phase-2 go/no-go** is written down, with its reason — including "no" and
   why, which is a real outcome here and closes the task.
3. `waa-eval-2026-07-30-forensics.md` **§10c** (HTTP 202 — the code that is not a
   page status) carries the result. That section exists; append, do not create.
4. `residential-egress-retry-path.md`'s population is re-derived. Today it says
   31, of which 23 are challenge hosts held on exactly this answer. Write the new
   number into that file's update block whichever way it goes — the task is on
   hold *for this*, and Tero was last told "three".
5. **Nothing is deployed.** Phase 1 touches no production code.

### What phase 1 deliberately does *not* establish

That **this** vendor's challenge resolves for us. Only a live host shows that.
Do not spend one to find out — MAS re-scrapes these hosts naturally, so if phase 2
ships, their next sweep is the confirmation, at zero marginal traffic. If a live
probe ever becomes genuinely necessary, it is a separate decision with Tero, not
a step inside this task.

Vendor identification is likewise deferred. `d1rozh26tys225.cloudfront.net` is a
CloudFront distribution over an S3 bucket (verified 2026-07-31: `server:
AmazonS3`, wildcard `*.cloudfront.net` certificate, no owner information in TLS or
headers), so the asset host identifies nothing. The page markup would — and MAS
may be able to supply one from a stored capture without either side making a
request. Ask before fetching.

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
