# A second markup family collapses the body — and nothing detects a collapse

**Status:** Open — ready to start. MAS handed us two reproducible hosts.
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

### 1. The guard — because the class is unbounded and the failure is silent

Whatever `apteam.fi` turns out to be, it is the second member of a family whose
first member (`<noscript>`) we found only because MAS noticed 406 one-character
pages months later. Chasing markup families one at a time is a losing game; every
new WordPress plugin can mint another.

A body that goes from 73 KB of HTML to 90 bytes of `cleaned_html` is
structurally impossible for a healthy page. Detect it:

- Compute the ratio at the point where both numbers exist. A collapse is roughly
  `len(html) > ~20 KB` and `len(cleaned_html) < ~1 KB` — **pick the thresholds
  from the fixtures and from Tier 1's real ratios, and write down the healthy
  distribution you measured them against.** A guard that fires on real pages is
  worse than no guard.
- The unit hazard applies: `html` and `cleaned_html` are HTML bytes, `markdown`
  is markdown characters. Name the unit in the field, the log line and the test.

### The transport — ANSWERED 2026-07-31, and not the way the question was asked

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

Consider whether recovery is worth adding *after* the guard works: `html2text`
over the raw rendered HTML — the conversion `aitosoft_static_mode` already uses,
which survived the `<noscript>` case untouched — turns a detected collapse into
degraded-but-real content. Cheap, reuses what we ship, and mirrors the
static-fallback decision. Do not bundle it with the guard; ship detection first
and decide recovery on its numbers.

### 2. The root cause — enumerate offline before fetching anything

An earlier draft of this task opened with "one production `/crawl` per host". Try
the offline route first; it is likely to be faster *and* it produces a better fix.

**Start from the member the fixture origin already found (2026-07-31).** Route
`/collapse/unclosed-noscript` reproduces the *mechanism* offline and end to end:
the body is swallowed, markdown comes back empty, at HTTP 200 `success: true`.
Pinned by `test_fixture_origin.py::test_an_unclosed_noscript_still_swallows_the_body`
— invert that test when the guard ships.

> **Correction, 2026-08-01 — the size in the previous draft was wrong, and the
> way it was wrong is a trap for the guard.** That route serves a **309-byte**
> page by default, not 73 KB; the earlier "73 KB in" (and the test docstring's
> "312 KB in") quoted the *production* incidents, not the fixture. The route
> takes `?bytes=` and pads with filler that adds bytes but no visible text and no
> content elements, so `…/collapse/unclosed-noscript?bytes=73000` is what
> actually reproduces `apteam.fi`'s 73,970-byte fingerprint.
>
> This matters because the guard is a **ratio**: a 309-byte page that collapses
> is not a collapse by any threshold worth shipping, and it must not be. Size the
> thresholds against the padded route and against Tier 1's real ratios. A session
> that tunes the guard until it fires on the unpadded fixture will have built a
> guard that fires on small healthy pages — the exact failure this file warns
> about two sections up.

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

Then continue the enumeration. Each shape through
`LXMLWebScrapingStrategy._scrap` (`crawl4ai/content_scraping_strategy.py:650`)
**and** through the fixture origin:

- every element that **cannot nest or is RCDATA/CDATA** and therefore swallows
  the document when unclosed — `<title>`, `<textarea>`, `<style>`, `<script>`,
  `<iframe>`, `<plaintext>`, `<xmp>`, on top of the `<noscript>` case already fixed
- malformed comments — `<!-->`, `<!-- --`, `--` inside a comment
- libxml2's **nesting-depth limit** against deeply nested `<div>`s
- foreign content — inline `<svg>` carrying `<style>`, self-closing shapes, MathML
- an early stray `</html>` or a second `<body>`

The target fingerprint is specific and easy to test against: **~73 KB of HTML
reduced to ~90 bytes of `cleaned_html`, deterministically.** Any shape that
reproduces it is a candidate; shapes that merely truncate partially are not.

If the enumeration produces a candidate, the fix generalises `strip_noscript()`
into **one named pre-parse repair** covering the family, with one test file. That
is a better outcome than a second one-off, and a stronger upstream PR than the
`<noscript>` fix alone.

**Only if the enumeration comes up empty** do we need `apteam.fi`'s actual bytes.
In that case, do not fetch it through production: use the dev container, whose
egress is a Finnish consumer ISP rather than our shared Azure address
(`tasks/done/fixture-origin.md` explains why that distinction matters). One
request, save the `html`, add the host to `TEST_SITES_REGISTRY.md`, never again.
MAS may also be able to supply it — they now store `cleaned_html` for degenerate
captures and re-scrape these hosts naturally, so asking costs neither side a
request. Note that `apteam.fi`'s fingerprint (73,970 / 96 / 1, byte-identical
across two visits) is the same shape `/collapse/unclosed-noscript` now produces,
so it may already be reproduced — check that before spending the request.

## Verification

- Offline suite in the shape of `test_noscript_body_collapse.py`: the two
  fixtures must produce real `cleaned_html`, and a healthy fixture must be
  untouched by the repair.
- `test_fixture_origin.py::test_an_unclosed_noscript_still_swallows_the_body`
  inverted, and `test_no_markup_shape_swallows_the_body` re-parameterised over
  the full `COLLAPSE_SHAPES` set with no exclusion.
- The guard: assert it fires on the pre-fix fixtures and does **not** fire on any
  Tier 1 capture. Record the Tier 1 ratios in the test as the evidence for the
  thresholds.
- Tier 1 regression 4/4.
- Do not re-hit `apteam.fi` or `flvi.fi` after the fixture capture.
- **Do not deploy this on its own.** It ships in one image with
  `detector-round3-evidence-vs-inference.md`, and possibly with the memory-guard
  fix from `render-500-window-2026-07-31.md`. The two detector defects pull in
  opposite directions by design and their net effect is only measurable in a
  single deploy; a solo deploy here spends the measurement for nothing. Land the
  work, run Tier 1, stop.

## Open with MAS

They are fixing their capture wait for the `revisol.fi` half and will send us the
residual — the part `apteam.fi` and `flvi.fi` belong to. That residual sizes this
task properly, but it does not gate it: two reproducible hosts are enough to
start, and the guard is worth building whatever the count turns out to be. See
also `tasks/challenge-interstitial-resolve.md`, which proposes handling their
timing half on our side adaptively instead of by a global sleep.
