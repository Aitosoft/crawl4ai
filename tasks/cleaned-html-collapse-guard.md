# A second markup family collapses the body — and nothing detects a collapse

**Status:** **Part 1 (the guard) DONE and DEPLOYED 2026-08-01. Recovery on guard
fire DONE 2026-08-02, shipped with
`done/download-navigation-is-not-a-render-error.md`. What is left of this file
is repair 1, scoped to `unclosed-script` — the one shape that is still silent.**
Part 1 shipped in one image with `done/detector-round3-evidence-vs-inference.md`,
`done/challenge-interstitial-resolve.md` phase 2 and
`done/render-500-window-2026-07-31.md`'s S half.

> **What the implementing session found wrong, 2026-08-02.** Read this before
> the rest; two of the three would have shipped as defects.
>
> 1. **"Recovery reuses the converter `aitosoft_static_mode` already ships" is
>    true of the converter and false of the pipeline, and the difference is the
>    whole feature.** Static mode does not call html2text on the HTML — it calls
>    `_strip_hidden_decoys()` first, which `decompose()`s every `noscript`. On an
>    unclosed `<noscript>` Chromium has re-serialized the whole document *inside*
>    that element, so BeautifulSoup deletes the page: **1,265 characters -> 0**,
>    measured. It reproduces `strip_noscript()`'s failure by a different route.
>    Recovery calls `HTML2Text` directly and deliberately skips the decoy strip,
>    which costs us hidden-decoy email obfuscation (the roadscanners.com class)
>    on recovered pages. Pinned by `test_recovery_must_not_reuse_static_modes_pipeline`.
> 2. **The obvious acceptance bar opens a new silent-loss channel.** The first
>    draft accepted a recovery on MAS's degenerate floor alone, arguing symmetry:
>    treat a recovery exactly as the normal path would treat the same output. A
>    review refuted it by measurement — a page with 41,408 characters of visible
>    text recovering **599** goes out green (599 > 500) and 40,809 characters
>    vanish with no signal on either side. The two paths are **not** symmetric:
>    here the guard has *already proved* the collapse, and declining to use
>    evidence we hold is not consistency. A recovery must now clear the ratio
>    floor as well. No new constant; every genuine recovery ever measured sits
>    10-28x above it.
> 3. **"The item that returns customer data, and it returns it on the shapes we
>    can already see" overstates what is known** (`tasks/README.md` said this).
>    Recovery is measured on **fixtures**. Which mechanism the 9 production URLs
>    hit is still unknown — this file's own part 2 says `apteam.fi`'s fingerprint
>    fits at least two rows. Real-traffic yield is somewhere in 0-9 of 9 and is
>    unmeasured. The honest reason to ship it is this file's *second* argument:
>    it is a **free mechanism classifier**, and the yield is then a measurement
>    rather than a claim.
>
> The measurement in §"Recovery is measured" was re-derived independently and
> **reproduces to the character**, including the byte-identical 1,265. It stands.

**The 2026-08-02 scope cut in this file ("do repair 1, park 2 and 3") was
written before the recovery numbers existed and is superseded.** The new
sequence is at the end of §"Recovery is measured". The cut's *reasoning* still
holds; what changed is that a cheaper instrument turned out to cover two of the
three repairs.

**MAS's half of this task got smaller in the same image, by accident.** Phase 2
of `challenge-interstitial-resolve.md` gives the patchright retry a 10 s capture
wait, and tier 3 already marks a near-empty page blocked — so a shell that
paints within ~11.2 s is now rescued on the retry we already pay for. That is
the `revisol.fi` class (their 361,900/242/1 at wait 2.0 vs 598,937/101,091/21,921
at 10). It does nothing for `apteam.fi` and `flvi.fi`, which are byte-identical
across visits and are part 2's business.

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
33-row appendix; and, since 2026-08-02, our own production logs — see below.

## Production evidence, 2026-08-02 (the guard's first real traffic)

MAS ran ~30 prospect sites on the evening of 2026-08-01, the first real workload
revision `--0000033` has seen. Read from Log Analytics, zero live requests:

| | |
|---|---:|
| renders admitted | 336 |
| distinct URLs | 328 |
| distinct hosts | 38 |
| **`RENDER DEFECT` firings** | **12** |
| **distinct URLs affected** | **9 (2.7 %)** |
| **distinct hosts affected** | **7 of 38 (18 %)** |

Every one has the same shape: **0 characters of markdown out**, from 725–40,165
characters of visible text in. Hosts: `taitotalo.fi`, `casambi.com`, `kiesi.fi`,
`takk.fi`, `castren.fi`, `begroup.fi`, `vestra.fi`.

Three things follow, and the third is the one that matters most.

1. **The population is larger than this file assumed.** It was sized from MAS's
   two reproducible hosts (`apteam.fi`, `flvi.fi`). One ordinary evening produced
   seven more.
2. **The guard works on real pages**, not only on fixtures. It fired on live
   customer markup, at HTTP 200 with content attached, costing zero retries. That
   was the thing part 1 had never been able to demonstrate.
3. **MAS reported the same run as clean.** They observed no issues. They were not
   being careless — a page that yields no contacts is indistinguishable, from
   their side, from a page that has no contacts. This is the identical silent
   failure mode as the `<noscript>` case that ran 3½ months. **A consumer
   reporting "no problems" is not evidence of no data loss, and must never again
   be recorded as if it were.**

Two caveats on the numbers, so nobody over-reads them:

- The 1,209 renders before the guard existed (revisions `--0000030`/`--0000031`)
  had no detection at all. If the rate held, ~30 pages were lost silently in
  those runs — an extrapolation, not a measurement. Do not quote it as one.
- ~~12 firings over 9 URLs means three URLs were requested twice…
  **unresolved and worth one query**~~ — **RESOLVED 2026-08-02 by that query.**
  One Log Analytics read, zero crawl cost. The three repeats are
  `taitotalo.fi/henkilokunta` (52 s apart), `casambi.com/category/news/` (15 s)
  and `vestra.fi/fi/palvelut` (21 s). None of those gaps is MAS's retry backoff
  (1/2/4 s), and their client does not retry a 2xx at all — so these are their
  agent revisiting a URL for its own reasons. **The 200 contract is holding as
  designed.**

The same read sizes the population, which is worth having because the ratio
floor scales with it — a 40 KB page needs 4,000 characters back before recovery
is accepted, a 725-character page needs 500:

| visible chars | URL |
|---:|---|
| 40,165 | `www.taitotalo.fi/henkilokunta` |
| 27,517 | `www.begroup.fi/be-group` |
| 21,056 | `www.vestra.fi/services` |
| 20,986 | `www.vestra.fi/fi/palvelut` |
| 20,901 | `www.takk.fi/fi/takk` |
| 20,042 | `www.takk.fi` |
| 17,264 | `casambi.com/category/news/` |
| 6,191 | `www.castren.fi/people/` |
| 725 | `kiesi.fi/uutiset-ja-artikkelit/oppaat` |

## Recovery is measured, and it changes the sequence

Line ~190 of this file already proposed it and deferred the decision: *"Consider
whether recovery is worth adding after the guard works: html2text over the raw
rendered HTML … ship detection first and decide recovery on its numbers."* The
numbers now exist.

Measured 2026-08-02 through `ProductionPath.crawl` against `fixture_origin` at
`?bytes=73000`, zero external traffic. Each shape was crawled the production way,
then the **same** returned `html` was re-converted with `crawl4ai.html2text.HTML2Text`
(`body_width=0`, `ignore_images=True`) — the converter `aitosoft_static_mode.py`
already ships and already uses:

| shape | markdown today | html2text over the same HTML | content marker | tail marker |
|---|---:|---:|:--:|:--:|
| `unclosed-noscript` | 0 | **1,265** | yes | yes |
| `deep-nesting` | 0 | **1,239** | yes | yes |
| `unterminated-comment` | 0 | 0 | no | no |
| `unclosed-script` | 0 *(guard blind, `success: true`)* | 0 | no | no |
| *healthy control* | 1,258 | 1,265 | yes | yes |

`unclosed-noscript` recovers to **1,265 characters — the same figure the healthy
control produces**. This is full recovery, not a degraded scrape.

**Re-run this before building on it.** It is one session's measurement and it is
load-bearing; the reproduction is ~40 lines (start `FixtureOrigin`, crawl
`/collapse/{shape}?bytes=73000` through `ProductionPath`, re-convert
`outcome.html`, compare against `CONTENT_MARKER` / `CONTENT_TAIL_MARKER`). If it
does not reproduce, that finding outranks everything below it.

### What this does to the three repairs

- **Repair 2 (`deep-nesting`, libxml2 depth limit) is deleted, not parked.**
  Recovery returns the full body. There is no remaining reason to touch libxml2's
  depth handling.
- **Repair 1 shrinks to one shape and keeps its urgency there.** Recovery only
  runs when the guard fires, and the guard is structurally blind to
  `unclosed-script` — that page still returns `success: true` with zero markdown.
  **`unclosed-script` is now the only silent member of the family, and repair 1
  is the only instrument for it.** It also remains the strongest of our upstream
  PRs, for the same reason as before.
- **Repair 3 (`unterminated-comment`) stays parked**, unchanged: recovery does
  not help, and the guard already reports it truthfully.

### The sequence, replacing the 2026-08-02 cut

1. ~~**Recovery on guard fire.**~~ **DONE 2026-08-02.** Lives in
   `aitosoft_collapse_guard.py`, which is 100 % ours — no new divergence from
   upstream's parser, nothing extra to merge forever. Ships as a free mechanism
   classifier; the customer data it returns on real traffic is a measurement we
   do not have yet (see the correction at the top of this file).
2. **PRICED AND REJECTED, 2026-08-05. Do not re-open — read this before
   anything else in this file.** The pricing was done and the answer is **no**:
   `content_source="raw_html"` dissolves nothing that is still open, so it does
   **not** delete repair 1, and it must not be flipped as a default.

   Measured through the browser against `fixture_origin` at `?bytes=73000`,
   zero external traffic:

   | shape | markdown, cleaned | markdown, raw | verdict |
   |---|---:|---:|---|
   | `unclosed-noscript` | 1 | **1250** | prevented — but recovery already fixes it |
   | `deep-nesting` | 1 | **1226** | prevented — recovery already fixes it |
   | `unclosed-script` | 1 | **1** | **unchanged** |
   | `unterminated-comment` | 1 | **1** | **unchanged** |
   | healthy control | 1259 | 1250 | — |

   **The asymmetry is structural, not incidental, and that is the whole
   result.** The two shapes raw_html saves are lost at *tree construction*,
   where libxml2 (`content_scraping_strategy.py:668`) and Python's
   `html.parser` (`html2text/__init__.py:37`) legitimately differ. The two it
   cannot save are lost at the **tokenizer**: `CDATA_CONTENT_ELEMENTS ==
   ('script','style')` and comment discarding are HTML5 spec behaviour that
   both parsers implement identically. **No choice of parser rescues
   `unclosed-script`.** The claim in `tasks/README.md` that it would "probably"
   help `unclosed-script` too was false.

   It also rescues markdown *only*: `cleaned_html` is still ~50 bytes on every
   collapsed shape, so `links`, `media`, `metadata` and `fit_markdown` are
   unchanged.

   **One of the two cited measurements was not about this at all.** The index
   cited "two independent measurements" agreeing the quality cost is small. The
   second — "median 0.91× across 59 stored captures" — reproduces numerically
   (0.919, n=61) but measures `HTML2Text(ignore_images=True)`, the *recovery
   converter*, and the 9 % gap is dropped images. It is neither independent of
   nor about `content_source`. The real figure is **1.002** (n=61, min 0.999,
   max 1.156 — talgraf, and its +1,103 chars are 11 image links, not text).

   **And there is a contact hazard that argues against flipping it even where
   it works.** 14 of 61 captures lose a word boundary on an email:
   `**UB Corporate Finance Oy**ubcf@unitedbankers.fiSuomi:` — lxml re-serializes
   `</p>\n<p>` while Chromium's raw HTML has `</p><p>`, and inside a `<td>`
   html2text emits no break. A regex extractor reads `ubcf@unitedbankers.fiSuomi`.
   It appeared on the one host in our corpus that has a contact table, which is
   exactly the page type MAS crawls. Whether it matters depends on whether their
   extractor is regex- or LLM-based — one question in a relay, unasked so far.

   Corpus caveat for whoever re-checks: `test-aitosoft/artifacts/` holds 140
   files but only **61 distinct captures across 7 URLs on 6 hosts**, five of
   which are the Tier 1 set. "66 stored captures" overstated the breadth.

   Reachability, if it is ever wanted per-request: MAS **can already set it
   themselves** — `DefaultMarkdownGenerator` is in `UNTRUSTED_ALLOWED_TYPES`
   and `markdown_generator` is in the `CrawlerRunConfig` allowlist
   (`async_configs.py:193,237`), so it needs no code from us. `config.yml`
   cannot express it (`api.py:831-835` only fills `None`/`""` fields, and
   `markdown_generator` defaults to a live instance).

   The one thing still worth considering separately is the guard's own
   suggestion at `aitosoft_collapse_guard.py:305-318` — have `recover_markdown()`
   use the seam instead of bare `HTML2Text`, which keeps the guard firing (so the
   mechanism classifier survives) and gives recovered pages citations. Cosmetic,
   and a different decision.

   *Original framing, kept for the record:* This is the principle-7 question
   nobody asked, and the review that found it is right that it was missing from
   both task files.

   `DefaultMarkdownGenerator` takes a documented
   `content_source: "raw_html" | "cleaned_html" | "fit_html"`
   (`crawl4ai/markdown_generation_strategy.py`). Recovery rejected it *as the
   fallback* on "fewer moving parts over malformed markup", which is a fine
   reason and a small question. The large question is the other one: generating
   markdown from raw HTML would mean **the collapse never happens** for the
   noscript and deep-nesting families — deleting the guard's largest population
   instead of catching it, and probably `unclosed-script` with it.

   It is not free — `cleaned_html` exists to strip nav and boilerplate, so every
   page's markdown would grow — but the cost looks far smaller than anyone would
   guess, and it is **measurable offline in an hour** against the 66 stored
   captures. Two independent measurements already exist and agree:

   - raw-html markdown vs the stored normal-path markdown is **0.9988–1.0066**
     on 5 of 6 hosts, and 1.161 on `talgraf.fi`;
   - plain html2text over the same stored `html` is a **median 0.91×** the
     stored markdown length across the 59 captures that have real markdown
     (min 0.76 on `jpond.fi`, max 0.98).

   Six hosts is not enough to change every page on. It *is* enough to say this
   deserves an hour before anyone writes a pre-parse repair, because if it holds
   it deletes repair 1, repair 3 and most of the guard's reason to exist.

3. **Repair 1, scoped to `unclosed-script`** — if #2 does not delete it. Priced
   against how often that shape actually appears; recovery is the classifier for
   that and it is live. `RENDER DEFECT … recovered 0 chars` is the
   comment/script family, `COLLAPSE RECOVERED` is the noscript/nesting family,
   and a *non-zero* count under `RENDER DEFECT` is a partial recovery, which is
   a third thing nobody has seen yet.
4. Repair 3: parked. Repair 2: closed.

**Worth stating plainly because it is nowhere else:** `strip_noscript()` — our
own pre-parse repair for the *nested* `<noscript>` case — is what **creates**
the `unclosed-noscript` loss, per CLAUDE.md's own key finding. So recovery is a
fallback compensating for one of our repairs, and both now ship. That is
defensible (the nested case ran 3.5 months across 406 pages; the unclosed case
is now recovered) but it is the kind of arrangement that looks accidental to a
fresh reader, and #2 above would dissolve it.

### Two design points recovery had to decide, not inherit — both decided

- **A recovered page goes out as `success: true` with the recovered markdown.**
  Option B — keep `success: false` and attach it — buys nothing: MAS's client
  reads `success` and would discard the content we just rescued. Shipping it as
  a success is the entire point, and it narrows `render_defect` to its true
  meaning: *we lost the body and could not get it back.* Both shapes are HTTP
  200 either way, so **no retry behaviour changes** and this is additive from
  MAS's side.

  The corollary the file did not state, and it matters: a **partial** recovery
  is not attached either. On a failed result the markdown is *evidence* — it is
  what our parse produced — and overwriting it with something we have just
  declined to call a success destroys that for no gain, since MAS reads
  `success` and stops. The character count goes in the log line instead.
- **No `markdown_source` / "this came from the fallback" field in this image.**
  It is a contract change and the name is MAS's to pick, exactly like the
  `fodbar.fi` field. Logged on our side under its own token
  (`COLLAPSE RECOVERED`, deliberately *not* a substring of `RENDER DEFECT`, so
  the two populations stay countable apart across images), to be mentioned in
  the next relay. This file's own rule: no unannounced contract changes in an
  image about something else.

### What recovery does NOT fix, recorded so it is not rediscovered

- `cleaned_html` is left as our parse produced it, `fit_markdown` stays empty
  (no content filter ran) and `links` stays whatever the collapsed parse
  produced — usually nothing. That is the same shape `aitosoft_static_mode`
  already returns for every static capture MAS consumes, so it is not a new
  thing for their client, but a recovered result is genuinely less complete than
  a healthy one.
- `handle_stream_crawl_request` calls neither `guard_result` nor
  `classify_result`, so "the guard runs on every successful result" is only true
  of `/crawl`. MAS does not use streaming (message 09), so this is a note, not a
  task.
- Upstream's own seam — `DefaultMarkdownGenerator(content_source="raw_html")` —
  produces an **identical** recovery (measured) and would additionally fill
  `markdown_with_citations` and use full mode's markdown dialect. It was not
  chosen because recovery runs on markup we already know is malformed and the
  fewer lines of upstream machinery that touch it the better. Recorded because
  it is the better-looking option and the next session should not have to
  re-derive that the yield is the same.

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

> **SUPERSEDED 2026-08-02 (same day, later) by §"Recovery is measured".** The cut
> below was written before anyone measured what html2text does to these shapes.
> Recovery covers `deep-nesting` outright (repair 2 is closed, not parked) and
> `unclosed-noscript` outright, which leaves repair 1 needed for
> **`unclosed-script` alone** — where the argument below is still exactly right
> and is now the whole argument. Repair 3 is unaffected. Kept because the
> reasoning is reusable and because a cut that gets narrowed by a measurement,
> rather than by a free session, is the process working.
>
> **Scope cut, coordinator 2026-08-02: do repair 1. Repairs 2 and 3 are parked.**
>
> Repair 1 earns its place on two grounds that the others do not share. It is a
> **genuine upstream bug** and the strongest of our four pending PRs — an
> unclosed raw-text element making Chromium serialize the rest of the document
> inside it is not specific to us. And `unclosed-script` is the one shape the
> shipped guard is **structurally blind to**: `_visible_text` strips script
> blocks (correctly), so it measures 0 visible characters and no text-ratio guard
> can ever fire on it. For that shape the root-cause fix is the only instrument
> we have, which is not true of the other three.
>
> Repairs 2 (`deep-nesting`, libxml2 depth limit) and 3 (`unterminated-comment`)
> are parked because **the guard already catches both and tells MAS the truth**:
> HTTP 200, `success: false`, `failure_class: render_defect`, content attached.
> They keep their previous capture, do not retry, do not delete. That costs
> accuracy on an unknown-sized population — it does not cost data, which is the
> thing that made this task urgent in the first place. Repair 3's own text
> already said it may not be worth doing.
>
> **What un-parks them:** MAS's residual empty-capture count (asked for in
> message 10 §7.3) showing the population is large, or `apteam.fi`'s bytes
> landing on repair 2's mechanism specifically. Both arrive for free from their
> side; neither is worth a request from ours.

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
  200**, content still attached. (That name no longer exists — recovery split it
  on 2026-08-02 into `test_a_swallowed_body_is_recovered` and
  `test_an_unrecoverable_collapse_is_reported_as_a_defect`. Kept here as the
  history of what shipped on 2026-08-01.) `test_no_markup_shape_swallows_the_body`
  re-parameterised over the complement of the measured swallowing set — the
  original "no exclusion" wording assumed the root cause was fixed, which it is
  not, so the exclusion is now a *measured* set with a test that fails if a
  member stops collapsing.
- `test_a_body_swallowed_into_a_script_is_still_silent` — the blind spot, pinned
  rather than left to be rediscovered.
- Full offline suite 152, `pre-commit run --all-files` clean, secret check exit 1.

Recovery, done 2026-08-02 — **zero live requests**:

- `test_collapse_guard.py` — the four fixtures that used to pin "collapsed and
  stays collapsed" are all 100 % recoverable, so they were rewritten rather than
  patched: `test_guard_result_recovers_a_lost_body` (the win),
  `test_a_body_html2text_cannot_read_either_is_still_a_defect` (the net),
  `test_a_partial_recovery_must_not_become_a_silent_success` (the review's
  41,408/599 case), `test_a_recovery_must_clear_both_floors` (the rule at its
  corners), `test_recovery_must_not_reuse_static_modes_pipeline` (the
  `_strip_hidden_decoys` trap), `test_recovery_never_runs_on_a_healthy_page`
  (cost).
- `test_fixture_origin.py` — `test_a_swallowed_body_is_reported_as_a_defect`
  **split**, because 2 of its 3 shapes now recover. `RECOVERABLE_SHAPES` is a
  third measured partition next to `BODY_SWALLOWING_SHAPES` and
  `GUARD_BLIND_SHAPES`; the shapes did **not** move out of
  `BODY_SWALLOWING_SHAPES`, because they still swallow the body — moving them
  would have made `test_no_markup_shape_swallows_the_body` assert a green path
  for a page that is still collapsing underneath.
- Both assertions check `CONTENT_TAIL_MARKER`, not only `CONTENT_MARKER`: a
  recovery that returned the heading and stopped is exactly how the `<noscript>`
  loss hid for 3.5 months.
- Cost measured: html2text is 2.6 ms on the largest fixture (80 KB) and 26 ms on
  the largest real capture we hold (`solwers.com`, 721 KB), and it only runs
  after the guard has fired.

Still owed:

- Do not re-hit `apteam.fi` or `flvi.fi`.

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
