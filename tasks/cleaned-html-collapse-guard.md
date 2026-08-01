# A second markup family collapses the body — and nothing detects a collapse

**Status:** **Part 1 (the guard) is DONE, 2026-08-01. Part 2 (root cause) is
open and is bigger than this file said.** Landed, not deployed — it ships in one
image with `detector-round3-evidence-vs-inference.md`.

Two things this file asserted turned out to be wrong, and both were load-bearing:

1. **The guard cannot be an `html` → `cleaned_html` ratio.** Refuted by
   measurement, twice over. The fixture's *healthy* control padded to 73 KB
   produces 261 bytes of `cleaned_html` — ratio 0.0036, **byte-identical to the
   collapsed page's** — because `len(html)` is dominated by inline CSS that
   cleaning strips by design. Real captures agree: `accountor.com`'s cookie wall
   is 99,649 bytes of HTML and 230 of `cleaned_html`, and is not a defect. And
   the `unterminated-comment` shape returns 74,523 bytes of `cleaned_html`
   *containing the contact details* while still producing zero markdown, so a
   `cleaned_html` ratio is blind to an entire mechanism. The shipped guard
   compares **visible text characters in, markdown characters out** — same unit
   on both sides, which is also MAS's unit.
2. **The root cause was not "probably already found".** That was an inference
   from one fixture. Enumerated through the browser: **four** shapes lose the
   whole body, by **three** distinct mechanisms, all deterministic. See part 2.
**Priority:** High. This is the *second* instance of a silent whole-body loss in
one month, and the first one (`<noscript>`) ran undetected for 3½ months across
406 pages and 70 hosts at HTTP 200 `success: true`.
**Effort:** S (guard) + unknown (root cause, bounded by the fixtures).
**Risk:** low for the guard; the root-cause fix touches the parse path, so it
needs the same fixture discipline `done/noscript-collapses-body-to-empty-markdown.md`
used.
**Evidence:** `tmp/mas-repo-messages/07-from-us-243-host-rescrape.md` §1 and its
33-row appendix.

## What MAS measured

After `0.9.2-failure-class`, 35 of their 70 `empty_*` hosts recovered. **33 did
not**, and 32 of those arrived with a full body that vanished before markdown
existed:

| | min | median | max |
|---|---:|---:|---:|
| `html` | 44,308 | 95,451 | 361,900 |
| `cleaned_html` | 68 | 194 | 804 |
| `markdown` | 1 | 1 | 1 |

They then split the population by experiment rather than by argument, changing
one field (`delay_before_return_html` 2.0 → 10) on three hosts:

| host | 2.0 | 10 | verdict |
|---|---|---|---|
| `revisol.fi` | 361,900 / 242 / 1 | 598,937 / **101,091** / **21,921** | theirs — captured pre-hydration |
| `apteam.fi` | 73,970 / 96 / 1 | **73,970 / 96 / 1** | **ours** |
| `flvi.fi` | 73,450 / 91 / 1 | **73,450 / 91 / 1** | **ours** |

`apteam.fi` and `flvi.fi` returned **byte-identical** `html` across two visits
forty minutes apart with a five-times-longer wait, and `cleaned_html` unchanged
to the byte. Same input, same output. Timing cannot produce that. A 73 KB body is
being reduced to ~90 bytes deterministically, inside our cleaning path.

MAS ruled their own content-filtering config out by measurement, one knob at a
time (their §1 table): `word_count_threshold` is inert even at 1,000, `only_text`
changes nothing, `css_selector` produces a different fingerprint, and
`excluded_tags` reproduces it exactly **but they do not send it**. That leaves
our parse.

## Two pieces of work. Do them in this order.

### 1. The guard — DONE 2026-08-01

`deploy/docker/aitosoft_collapse_guard.py`, wired into `api.py`'s result loop.
Pinned by `test-aitosoft/test_collapse_guard.py` (22 offline) and by
`test_fixture_origin.py` end to end through the browser.

**What it measures, and why not the obvious thing.** The rule this file proposed
— `len(html) > ~20 KB and len(cleaned_html) < ~1 KB` — fires on healthy pages.
Measured, not argued: the fixture's healthy control padded to 73 KB gives 261
bytes of `cleaned_html`, the same 0.0036 ratio as the collapsed page, because the
padding is inline CSS and cleaning strips it. Real customer captures sit in the
same place — `accountor.com`'s cookie wall is 99,649 → 230 → 125 and is fine.

So the guard compares **visible text characters in the rendered HTML** against
**markdown characters out**. Text on both sides, which is also the unit MAS's
`DEGENERATE_CAPTURE_CHARS = 500` is written in — the unit hazard is handled by
never crossing it. Whitespace is collapsed first; `monidor.com`'s interstitial
measures 506 raw "visible" characters and 58 once normalised, and counting raw
would have fired the guard on a challenge screen.

**The healthy distribution the thresholds were measured against** — 37 distinct
real captures under `test-aitosoft/artifacts/` (the four Tier 1 hosts plus
talgraf and monidor), zero live requests. `test_thresholds_clear_every_real_capture`
re-derives it on every run, so the constants cannot drift away from the evidence:

| population | n | visible chars | markdown/visible |
|---|---:|---:|---:|
| healthy content pages | 31 | 739–34,172 | **1.311–2.400** |
| cookie-wall / JS shells | 5 | 0 | *nothing to lose* |
| challenge interstitial | 1 | 58 | 1.000 |
| collapsed (fixture, 4 shapes) | 4 | 1,135–1,138 | **0.000** |

Markdown is normally *longer* than the text it came from — markdown syntax adds
characters. The gap between the lowest healthy page (1.311) and every collapse
(0.000) is two orders of magnitude, which is the only reason this is shippable.
Thresholds: `MIN_VISIBLE_TEXT_CHARS = 500` (below the smallest real content page
at 739, far above the interstitial at 58), `MAX_MARKDOWN_CHARS = 500` (MAS's own
floor, so the guard can only fire on captures they already discard),
`MAX_MARKDOWN_TO_VISIBLE_RATIO = 0.10` (13× below the lowest healthy page).

The markdown test runs first — it is the cheap one and it screens out every
healthy page, so the 9 ms visible-text pass never runs on the path that matters.

**Two things it deliberately does not catch**, both recorded in tests rather than
left to be rediscovered: partial loss (no threshold separates it from a page with
a lot of boilerplate), and content swallowed into a `<script>`, where the visible
text measures zero and the capture is indistinguishable from an empty page. The
second is `unclosed-script`, and it belongs to part 2.

### The transport — ANSWERED 2026-07-31, IMPLEMENTED 2026-08-01

We asked MAS whether the taxonomy needed a non-retryable "ours and permanent"
class. Their answer (message 09 §1), read out of their client code rather than
their documentation:

**The class name is not the lever. The wire status is, and it is the only thing
that is.** Their retry branch is
`RETRY_CONFIG.retryableStatuses.includes(response.status)`, evaluated *before* the
body is parsed. `failure_class` is received, logged, and otherwise unread. Their
full table:

```
2xx            -> results[0] returned.  envelope `success` is never read
504            -> NOT retried; 2 consecutive on a host pivots it to static
429            -> long backoff spanning an ACA scale-out
500 / 502 / 503 -> retried 3x, 1s / 2s / 4s
anything else  -> failure, no retry
```

**So: serve a detected collapse in an HTTP 200 envelope with result-level
`success: false`.** That is the `savaterra.fi` shape they verified end to end in
the same run — a 200 envelope carrying a result-level 403 and
`failure_class: origin_blocked` tripped their check cleanly and cost zero
retries. Do **not** put it behind 500/502/503, which is what `render_error` maps
to today via `http_status_for`.

The class name is ours to choose and should still say what happened, because it
is what we debug from and what they may eventually branch on. A distinct
`render_defect` — ours, permanent, not retryable — is worth adding for exactly
that reason, but understand it buys diagnosis, not behaviour: **the 200 does the
work.**

> **A defect this uncovered, and it is ours to fix in the same change.** MAS
> noticed that `render_error` is "sometimes the retryable one and sometimes not".
> They are right, and the mechanism is worse than they could see:
> `aitosoft_static_mode.py:316` returns `failure_class: RENDER_ERROR` inside a
> **200** — static mode never raises, which is its pinned contract — while full
> mode's identical class goes out at **500** through `http_status_for`. Same
> class, opposite retry behaviour, decided by `render_mode` and documented
> nowhere. Fix it here rather than adding a third meaning on top of it: put the
> permanence distinction in the vocabulary, map it in one place, and pin both
> render modes to the same wire status for the same class.

Content stays attached either way — *"a tag is advisory; `success: false` is
structural"*.

**Shipped as described.** `render_defect` is in the vocabulary; `http_status_for`
is the single mapping site and `server.py` now routes **both** render modes
through it via `_crawl_response`, so a class can no longer mean two things. The
permanence distinction lives in `NON_RETRYABLE_CLASSES`, separate from
`ORIGIN_CLASSES` — `render_defect` is entirely our fault *and* must not be
retried, and conflating those two ideas is what produced the original defect.

> **One more defect fell out of the fix, and it was ours and unshipped.**
> Routing static mode through the shared mapping turns its result-level
> `bad_request` — an egress-broker refusal of a redirect hop, whose own comment
> says *"MAS must never retry it"* — into a **500, retried 3×**. Static mode's
> unconditional 200 had been making that true by accident. `bad_request` is now
> in `NON_RETRYABLE_CLASSES` and pinned by
> `test_an_ssrf_refusal_is_not_retryable`. Worth noting how it was found: not by
> the 151 passing tests, but by reading every `failure_class` static mode can
> emit before changing what happens to them. A "route both through one function"
> change is exactly the shape that breaks the cases the function never saw.

Consider whether recovery is worth adding *after* the guard works: `html2text`
over the raw rendered HTML — the conversion `aitosoft_static_mode` already uses,
which survived the `<noscript>` case untouched — turns a detected collapse into
degraded-but-real content. Cheap, reuses what we ship, and mirrors the
static-fallback decision. Do not bundle it with the guard; ship detection first
and decide recovery on its numbers.

### 2. The root cause — ENUMERATED 2026-08-01. Four shapes, three mechanisms.

**The enumeration is done and it refuted this section's premise.** Every shape
below was run through `ProductionPath.crawl` at `?bytes=73000` (apteam.fi's
size), twice each, zero live requests. Four lose the whole body; the other
seventeen come back intact. All four are **deterministic** — byte-identical
`html` and `cleaned_html` across two visits — which is the property that told MAS
`apteam.fi` and `flvi.fi` were ours.

| shape | html | cleaned_html | markdown | visible | mechanism |
|---|---:|---:|---:|---:|---|
| `unclosed-noscript` | 74,568 | 50 | 0 | 1,135 | raw-text re-serialization |
| `unclosed-script` | 74,545 | 50 | 0 | **0** | raw-text re-serialization |
| `deep-nesting` | 80,145 | 50 | 0 | 1,135 | libxml2 depth limit |
| `unterminated-comment` | 74,535 | **74,523** | 0 | 1,138 | content inside a comment |
| *healthy control* | 74,513 | 1,516 | 1,227 | 1,135 | — |

Read the table before planning the fix; three of its rows contradict something
this file used to say.

- **"The root cause is probably already found" was an inference from one
  fixture, and it is wrong.** `unclosed-noscript` is one of four. Two of the
  others have nothing to do with `<noscript>` or with raw text at all.
  `apteam.fi`'s fingerprint (73,970 / 96 / 1) is consistent with *at least two*
  of these rows, so which one it is remains **unknown** — do not write it down
  as solved.
- **`deep-nesting` is size-dependent**, which is why the enumeration had to run
  padded. It is harmless at 1.5 KB and fatal at 73 KB. A session that enumerated
  against the unpadded route would have found three shapes and called it four.
- **`unterminated-comment` keeps its `cleaned_html` intact** — 74,523 bytes,
  contact details present — and still produces no markdown. Any repair aimed at
  the parse will miss it; the loss is in markdown generation.
- **`unclosed-script` is invisible to the guard** (`_visible_text` strips script
  blocks, and must). It is the one member where the root-cause fix is the *only*
  instrument. Pinned as today's silent behaviour by
  `test_a_body_swallowed_into_a_script_is_still_silent`.

The measured set lives in `fixture_origin.BODY_SWALLOWING_SHAPES` /
`GUARD_BLIND_SHAPES`, and `test_no_markup_shape_swallows_the_body` is
parameterised over the complement, so a shape that stops collapsing fails the
suite rather than quietly leaving the set.

> **Correction, 2026-08-01 — the size in the previous draft was wrong.
> VERIFIED and acted on.** The route serves **309 bytes** by default (measured;
> now 1,477 after the content page grew), not 73 KB — the earlier "73 KB in" and
> the test docstring's "312 KB in" quoted the *production* incidents. `?bytes=`
> pads with inline CSS that adds bytes but no visible text.
>
> The warning was right and it earned its keep twice. Every enumeration run and
> every threshold in the shipped guard is sized at `?bytes=73000`, and
> `test_fixture_origin.COLLAPSE_BYTES` makes that the default for the whole
> suite. Had it not been: `deep-nesting` **does not collapse at 1.5 KB and does
> at 73 KB**, so an unpadded enumeration would have missed a root cause outright
> — not merely mis-sized a threshold.

> **A second instrument gap — FIXED 2026-08-01.** `fixture_origin.CONTENT_HTML`
> rendered to ~140 markdown characters (measured; the file said 149), *below*
> MAS's `DEGENERATE_CAPTURE_CHARS = 500`, so the healthy control every route
> leans on was already degenerate by the customer's own floor.
>
> It now renders **1,227 markdown characters over 1,135 of visible text** —
> above 500 on both sides of the unit boundary. Pinned by
> `test_the_healthy_control_is_not_degenerate`, which fails if anyone trims it
> back. This mattered exactly as predicted: the guard's visible-text floor is 500
> characters, and sized against the old control it would have been tuned to fire
> on healthy small pages.
>
> On the unit, since this file's own line was wrong: 500 is **markdown
> characters** and the shipped collapse ratio is markdown characters per
> **visible-text character** — both text. HTML *bytes* appear nowhere in the
> guard, which is the whole point of §1.

The mechanism corrects this section's plan, so read it before enumerating:

> `test_noscript_body_collapse.py` reports the `UNCLOSED` shape **fixed**, and it
> is telling the truth about libxml2 — given the raw string, libxml2 auto-closes
> the element and the body survives. Chromium does the opposite. An unclosed
> `<noscript>` puts its parser into raw-text mode, so the rest of the document —
> `</body></html>` included — is serialized *inside* the element, and
> `strip_noscript()` then correctly removes the element and takes the page with
> it. The bug is in what the browser hands us, not in what libxml2 does with it.

Two consequences:

- **Enumerate through the browser, not only through `LXMLWebScrapingStrategy`.**
  A shape that is harmless to libxml2 can be fatal after Chromium re-serializes
  it, and the pure-function suite will report it green. Add each candidate as a
  `/collapse/{shape}` entry in `fixture_origin.COLLAPSE_SHAPES` (a dict entry
  plus a parametrize case) and run it through `production_path.crawl`. Keep the
  libxml2-level test too — the two disagreeing *is* the signal.
- `strip_noscript()` is not wrong and should not be reverted; a pre-parse repair
  that excises an unclosed raw-text element has to decide what is *inside* it,
  and Chromium's answer is "everything". The repair needs to bound the region
  (e.g. re-attach content that follows the document's real `</body>`), not stop
  removing it.

The enumeration itself is done (the table above): all 21 candidates from the
original list ran, through the browser and at size. The seventeen that survive
are pinned by `test_no_markup_shape_swallows_the_body` and cost nothing to keep.

**What is left is the repair, and it is now three repairs, not one.** The single
"generalise `strip_noscript()` into one named pre-parse repair" plan only covers
the first mechanism:

1. **Raw-text re-serialization** (`unclosed-noscript`, `unclosed-script`) — the
   pre-parse repair, bounding the region rather than excising to the end of the
   document. `strip_noscript()` is not wrong and must not be reverted; it needs
   to re-attach what follows the document's real `</body>`. Generalises to any
   unclosed raw-text element, so this is still the strongest upstream PR.
2. **libxml2's nesting-depth limit** (`deep-nesting`) — nothing to do with the
   parse *repair*; it is a parser option (`huge`/depth) or a pre-parse depth
   flattening. Different fix, different test, and it is size-triggered so its
   test must be padded.
3. **Content inside an unterminated comment** (`unterminated-comment`) — the
   `cleaned_html` is *intact*, so no pre-parse repair touches it. The loss is
   downstream, in markdown generation. This one may not be worth fixing at all;
   price it against how often an unterminated comment appears in the wild before
   writing code.

Sequence them; do not bundle. Each one gets its shape out of
`BODY_SWALLOWING_SHAPES` and its case into `test_no_markup_shape_swallows_the_body`,
and the guard stays as the net underneath.

**`apteam.fi`'s bytes are still worth having, and the reason changed.** The old
plan said fetch them only if the enumeration came up empty. It came up *over*-full
instead: 73,970 / 96 / 1 is consistent with at least two rows of the table, so
the bytes are now what tells us **which mechanism to fix first** rather than
whether one exists. Ask MAS before spending a request — they store `cleaned_html`
for degenerate captures and re-scrape these hosts naturally, so it costs neither
side anything. If they cannot, use the dev container (Finnish consumer ISP egress,
not our shared Azure address — `tasks/done/fixture-origin.md`): one request, save
the `html`, add the host to `TEST_SITES_REGISTRY.md`, never again.

## Verification

Part 1, done 2026-08-01 — **192 tests, zero live requests**:

- `test_collapse_guard.py` — 22 offline. Thresholds asserted against the
  measured gap; every one of the 37 stored real captures asserted clean, and
  `test_the_real_corpus_still_shows_the_gap` fails if healthy pages ever close on
  the threshold rather than merely clearing it.
- `test_fixture_origin.py` — 40, browser-driven.
  `test_an_unclosed_noscript_still_swallows_the_body` **inverted** into
  `test_a_swallowed_body_is_reported_as_a_defect`, parameterised over the three
  detectable shapes: `success: false`, `failure_class: render_defect`, **HTTP
  200**, content still attached. `test_no_markup_shape_swallows_the_body`
  re-parameterised over the complement of the measured swallowing set — the
  original "no exclusion" wording assumed the root cause was fixed, which it is
  not, so the exclusion is now a *measured* set with a test that fails if a
  member stops collapsing.
- `test_a_body_swallowed_into_a_script_is_still_silent` — the blind spot, pinned
  rather than left to be rediscovered.
- Full offline suite 152, `pre-commit run --all-files` clean, secret check exit 1.

Still owed:

- **Tier 1 regression 4/4** — not run this session; needs a live server and four
  live requests, and this image is not deploying yet. Run it with #4's work in
  the shared image, not twice.
- Do not re-hit `apteam.fi` or `flvi.fi`.
- **Do not deploy this on its own.** It ships in one image with
  `detector-round3-evidence-vs-inference.md`, and possibly with the memory-guard
  fix from `render-500-window-2026-07-31.md`. The two detector defects pull in
  opposite directions by design and their net effect is only measurable in a
  single deploy; a solo deploy here spends the measurement for nothing.

**A note for whoever runs Tier 1 on the shared image.** The guard has never seen
a live page. Its evidence is 37 stored captures of the four Tier 1 hosts, which
is the same population Tier 1 re-fetches — so a Tier 1 run is a genuine check
that the corpus still describes the live sites, not a formality. If the guard
fires on any of the four, do not tune the threshold to silence it: that is either
a real collapse on a real customer page or a false positive, and both are worth
more than a green run.

## Deliberately NOT in this image — two items `tasks/README.md` folds into #3

Both are real and both are agreed with MAS. Neither is in this file's own scope,
and each is a separate contract change; three of those in one image is how a
measurement gets spent for nothing.

- **Flipping envelope `success` to the aggregate.** Agreed 2026-07-31. But MAS's
  message 09 says plainly that for 2xx the envelope `success` **is never read** —
  they take `results[0]`. So the flip buys no behaviour, while breaking a pinned
  contract (`test_static_mode.py:257` asserts `envelope["success"] is True` with
  all results false) in the same image that already changes static mode's wire
  status. Do it on its own, where a surprise is attributable.
- **The `fodbar.fi` field** — "content was present despite the origin status".
  Cheap, and the measurement is now sitting right there in
  `aitosoft_collapse_guard` (visible text vs markdown, already computed). But it
  is a *new field* in the contract and the name is ours to choose, so it should
  go out with message 10 rather than arrive unannounced in an image about
  something else.

## Open with MAS

They are fixing their capture wait for the `revisol.fi` half and will send us the
residual — the part `apteam.fi` and `flvi.fi` belong to. That residual sizes this
task properly, but it does not gate it: two reproducible hosts are enough to
start, and the guard is worth building whatever the count turns out to be. See
also `tasks/challenge-interstitial-resolve.md`, which proposes handling their
timing half on our side adaptively instead of by a global sleep.
