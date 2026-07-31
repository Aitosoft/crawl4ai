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

### 2. The root cause

Fixtures first, then offline. `apteam.fi` and `flvi.fi` return byte-identical
HTML, so **one production `/crawl` per host is enough forever** — save the `html`
field to `test-aitosoft/fixtures/` and never hit them again. Same recipe as
`kiertopakkaus.fi`; add both to the burned-hosts table in
`TEST_SITES_REGISTRY.md`.

Then reproduce against `LXMLWebScrapingStrategy._scrap`
(`crawl4ai/content_scraping_strategy.py:650`) and bisect the HTML to the region
that kills it, exactly as the `<noscript>` diagnosis did. Note the shape of the
existing bug for orientation without letting it anchor you: `<noscript>` failed
because it **cannot nest**, so the outer element never closed and libxml2
swallowed the rest of the document. The same "never closes" property belongs to
every RCDATA/CDATA-ish element — `<title>`, `<textarea>`, `<style>`, `<script>`,
`<iframe>` under HTML4 parsing — and also to malformed comments and to libxml2's
nesting-depth limit. That is a list of places to look, not a diagnosis.

If the fix generalises, prefer generalising `strip_noscript()` into one named
pre-parse repair with one test file over adding a second independent hack. It is
already an upstream-PR candidate; a second one-off is not.

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
