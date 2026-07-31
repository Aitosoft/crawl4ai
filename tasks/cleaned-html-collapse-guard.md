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

What to do when it fires is a contract question, and MAS's stated principle
answers most of it — *"a tag is advisory; `success: false` is structural"*, from
their Q1 answer. The default we should propose is the same shape as everything
else we shipped on 2026-07-30: `success: false` with a `failure_class` and the
content still attached, so their logic decides. **`render_error` is the honest
class** — this is our pipeline losing a body the origin served correctly, and the
classification bias in `aitosoft_failure_class.py` says unrecognised failures are
ours. Confirm with MAS rather than assuming; the question is in
`tmp/mas-repo-messages/08-*`.

Consider whether recovery is worth adding *after* the guard works: `html2text`
over the raw rendered HTML — the conversion `aitosoft_static_mode` already uses,
which survived the `<noscript>` case untouched — turns a detected collapse into
degraded-but-real content. Cheap, reuses what we ship, and mirrors the
static-fallback decision. Do not bundle it with the guard; ship detection first
and decide recovery on its numbers.

### 2. The root cause — enumerate offline before fetching anything

An earlier draft of this task opened with "one production `/crawl` per host". Try
the offline route first; it is likely to be faster *and* it produces a better fix.

`test_noscript_body_collapse.py` already has the right shape: it parameterises
over markup **shapes** (`NESTED`, `SINGLE`, `UNCLOSED`, `UPPERCASE`,
`WITH_ATTRS`) against fixed surrounding content. Extend that idea into an
enumeration of the whole family and run each shape through
`LXMLWebScrapingStrategy._scrap` (`crawl4ai/content_scraping_strategy.py:650`):

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
(`tasks/fixture-origin.md` explains why that distinction matters). One request,
save the `html`, add the host to `TEST_SITES_REGISTRY.md`, never again. MAS may
also be able to supply it — they now store `cleaned_html` for degenerate captures
and re-scrape these hosts naturally, so asking costs neither side a request.

## Verification

- Offline suite in the shape of `test_noscript_body_collapse.py`: the two
  fixtures must produce real `cleaned_html`, and a healthy fixture must be
  untouched by the repair.
- The guard: assert it fires on the pre-fix fixtures and does **not** fire on any
  Tier 1 capture. Record the Tier 1 ratios in the test as the evidence for the
  thresholds.
- Tier 1 regression 4/4.
- Do not re-hit `apteam.fi` or `flvi.fi` after the fixture capture.

## Open with MAS

They are fixing their capture wait for the `revisol.fi` half and will send us the
residual — the part `apteam.fi` and `flvi.fi` belong to. That residual sizes this
task properly, but it does not gate it: two reproducible hosts are enough to
start, and the guard is worth building whatever the count turns out to be. See
also `tasks/challenge-interstitial-resolve.md`, which proposes handling their
timing half on our side adaptively instead of by a global sleep.
