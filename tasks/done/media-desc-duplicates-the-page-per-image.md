# One page produced a 232 MB response, four times, and every instrument said success

> **IMPLEMENTED 2026-08-09. Option (a1): `MEDIA_DESCRIPTION_MAX_CHARS = 200` plus a
> 3-line truncation in `find_closest_parent_with_useful_text`
> (`crawl4ai/content_scraping_strategy.py`), pinned by
> `test-aitosoft/test_media_desc_cap.py` (6 tests). Offline suite 312 green.**
>
> **The diagnosis survived completely.** Every headline number on thermokon
> reproduced to the byte on an independent re-derivation: 1,160 entries, 19
> distinct `desc`, longest 154,798 chars, 1,104 sharing it, `media` 231,708,619
> bytes, `html` 2,323,376, `cleaned_html` 989,759, markdown 761,365, `links`
> 176,671. So did the cap ladder, the minified-vs-pretty mechanism, the
> `<video>`/`<audio>` inertness, the jpond 4,689 × 6, and the ~2.0× corpus
> fan-out (508 images → 1,012 entries; and thermokon's 1,160 entries are exactly
> **580 distinct images**, confirming the file's guess).
>
> **Eight things did not survive. Four are corrections, one is a new hole in the
> file's own coverage claim, and one settles its largest stated uncertainty.**
>
> 1. **The cap does NOT bound a media entry — only `desc`.** The file promised to
>    enumerate the amplifier for every media type and did (`<picture>` is covered,
>    `<audio>` is inert, **`<track>` produces no media entry at all** — there is
>    no `.//track` loop). It then missed two paths that *are* on the wire and are
>    **not** touched by capping that function: **`media.tables`** (123,365 B on
>    thermokon, byte-identical in both arms; `table_extraction` defaults to a real
>    `DefaultTableExtraction`, so production extracts on every request) and
>    **`alt`**, which `add_variant` copies into every variant exactly as it copies
>    `desc` — measured, one `<img>` with a 50,000-char `alt` and 5 srcset entries
>    gives 300,879 B of media from a 50,244 B document. Both are **linear in the
>    document**, so neither can reach the 433× regime and neither justifies more
>    code today. **But "media entries are now bounded" is false, and the upstream
>    PR must not claim it.** Recorded in the code comment.
> 2. **`grumblo.com` is the same mechanism — the file's largest uncertainty, now
>    settled.** One plain `httpx` GET (no crawler, dev-container egress, recorded
>    in `TEST_SITES_REGISTRY.md`): on the **static** HTML alone, 272 images carry
>    **1,524,174 chars of `desc` — 88 % of a 1,732,603-byte `media` payload** — 60
>    of them sharing one 24,293-char string, and the cap takes it to 107,772 B
>    (16×) with `cleaned_html` byte-identical. The rendered DOM production saw is
>    necessarily larger. So **n ≥ 2 confirmed, not "n=3 consistent-with"**, and one
>    of the two *succeeded* — which is the case no instrument on either side counts.
> 3. **"The walk can and does reach `<html>`" is refuted.** Never once, in 78 real
>    captures or any synthetic: lxml leaves `html.text` as `None`, so the
>    conjunction cannot fire there. Observed stopping tags: `div` 753, `section`
>    56, `body` 19, `article` 11, `tr`/`table` 8+8, `h5` 12, `td` 4, `p` 4,
>    `header` 4. This matters only if anyone builds the "skip if root" companion
>    §4 rejects — and it makes that companion *weaker* still.
> 4. **The corpus is 78 captures, not 68, and the pathological population is
>    undercounted.** 19 of 78 walk to `<body>`, not 12 of 68 — **12 jpond plus 7
>    accountor**, which the file misses entirely; and it is 12 of 16 jpond
>    captures, not all of them. Proportions hold: a 200-char cap changes **65/78
>    (83 %)**, a 500-char cap **61/78**.
> 5. **"The cap is faster" is right in direction and wrong in instrument, and the
>    real win is somewhere the file never looked.** Its 1.563 → 1.398 s was a
>    single shot inside its own noise. Over 9 interleaved reps `scrap()` gains
>    ~8 % (1.485 → 1.366 s, permutation p = 0.0014) — real, but small, because the
>    walk still builds each ancestor's `text_content()` before the slice. **The
>    actual win is serialization: `json.dumps` of that `media` goes 0.655 s →
>    0.002 s, 330×.** Say that instead.
> 6. **Its own cap ladder mixes two units.** "200 → 535,381" is images-only;
>    the table's 535,435 is whole-`media` (the 54-byte delta is the
>    `videos`/`audios`/`tables` keys). Same 54 in "42,860 image bytes" vs 42,914.
>    Also "the capture is 2,152,629 bytes" is its **character** count; the file is
>    2,165,928 bytes. Pick a unit before quoting either.
> 7. **§1's whitespace figures are properties of one synthetic, not of the bug.**
>    "45,324 B vs 11,714,724 B from the same 74 KB document" did not reproduce; a
>    300-image / 68 KB catalogue gives **7,081,164 B pretty vs 135,864 B minified,
>    52×**, with `desc: None` on all 900 entries in the minified arm. **The
>    mechanism claim is exactly right and is the strongest PR argument there is** —
>    just do not quote those two numbers as if they were the bug's.
> 8. **The shipped figure is 538,747, not 535,435.** The `"..."` truncation marker
>    costs 3 bytes per entry — 3,312 on thermokon — so the ratio is **430×**, not
>    433×. Kept anyway: upstream's own truncation idiom
>    (`preprocess_html_for_schema`) marks, and a snippet that is visibly cut beats
>    one that is silently short.
>
> **On the one real decision, (a1) vs (a2): (a1), and the file's own two
> verification asks both came back in its favour.**
>
> - **(ii) `_with_defaults` DOES deep-copy per instance** — `async_configs.py:69`
>   and `:91` are both `copy.deepcopy`, verified by `id()` comparison across two
>   constructed configs and by mutating one and reading the other. So (a2) was
>   **safe** on the axis the file worried about, and nobody should re-litigate it.
> - **(i) is what decides it, and it is stronger than the file knew.**
>   `scraping_strategy` is on `UNTRUSTED_FIELD_ALLOWLIST["CrawlerRunConfig"]`, and
>   `UNTRUSTED_ALLOWED_TYPES` contains exactly two scraping strategies:
>   `LXMLWebScrapingStrategy` and `PDFContentScrapingStrategy`. Patching the
>   **class** therefore closes every client-reachable path that can produce an
>   image `desc`; an *injected default* would simply be replaced by a client-sent
>   strategy object. MAS confirms they send none — but "the hole is shut" beats
>   "the hole is unused", and production being byte-identical to the upstream PR is
>   worth more than avoiding a merge surface in a file we already patch.
>
> **Two smaller things worth carrying:**
>
> - The cap sits inside the shared walker, so it also truncates the
>   `<video>`/`<audio>` `description`. Verified inert: `MediaItem` has no such
>   field and pydantic's `extra='ignore'` drops it at `MediaItem(**vid)`. The one
>   way it could ever reach the wire is `async_webcrawler.py:848-854`'s raw-dict
>   branch, reachable only via a custom scraping strategy returning a dict, which
>   is not a thing our deploy or the untrusted boundary allows.
> - **`crawl4ai/utils.py:1330` holds a second, independent, uncapped copy of the
>   same walker.** Confirmed dead — its only in-tree caller is a commented-out
>   line at `crawl4ai/legacy/web_crawler.py:232`, it is not exported, and the test
>   that references it calls a method that does not exist. Not a live hole; the
>   bug still lives there if anything ever re-enables it.
>
> **Two of §5's uncertainties are answered by MAS
> (`tmp/mas-repo-messages/40-…`):** they do not read `media` at all, per-field, so
> the cap needs no contract note; and their client timeout is **210,000 ms applied
> per attempt**, so the 216 s was ~6 s of overshoot they cannot explain either.
>
> **§3(c), the response-size guard, is deliberately NOT built.** MAS's answer was
> "ship the cap, we need nothing else", the two known hosts are both this
> mechanism, and a guard is a wire guard not a memory guard by the file's own
> §3(c) reasoning. What is left uncovered is named in correction 1 above — plus
> one thing found during the second-opinion pass that changes §3(c) from
> *unnecessary* to *parked*:
>
> **`media.tables` is the same defect class, on by default, and superlinear in an
> attribute value rather than in the document.** `CrawlerRunConfig.table_extraction`
> defaults to a real `DefaultTableExtraction`, and `crawl4ai/table_extraction.py`
> does `headers.extend([text] * colspan)` / `row_data.extend([text] * colspan)`
> with `colspan = int(cell.get("colspan", 1))` — **unvalidated, straight from the
> page**. Measured 2026-08-09:
>
> | input | result |
> |---|---|
> | `<th colspan="50000">` on a **4,624-byte** page | **4,504,226 bytes** of `media` JSON (the same markup at 10⁷ is ~900 MB) |
> | `<td colspan="2000000">` | wire payload unchanged (rows truncate at `max_columns`) but **peak RSS +91 MB from 905 bytes of HTML in 0.12 s** — invisible to every instrument |
> | `colspan="auto"` | `int()` raises, the whole table is silently dropped at `success: true` |
>
> **Not built, and that is the right call today** — it needs pathological markup
> while the `desc` bug fired on ordinary catalogue HTML, and building it here is
> precisely the elaboration failure CLAUDE.md principle 7 names. It is also an
> upstream defect in its own right. But it means the honest sentence is "the
> response body is still unbounded", not "the cap fixed response size".
>
> **§4's "drop `media` entirely" rejection had its premise flip and the conclusion
> still holds.** It was rejected on "we do not know whether MAS reads it"; MAS has
> now answered per-field that they never read any of it. So dropping the field is
> live and is *simpler* than capping. Still cap: the cap keeps a general contract
> for a general library, is what goes upstream, keeps every image's `src`/`alt`/
> `score` for any future consumer, and needs no MAS contract note — whereas
> dropping is a wire-schema change for a 430× that the cap already delivers.
>
> **Evidence-hygiene note:** `thermokon_rendered.html`, cited throughout, **is not
> in the repo** — it lives in a session scratchpad and the 231,708,619 headline is
> not re-derivable from a clean clone. The *mechanism* is: the new test file
> reproduces it synthetically, and `grumblo.com`'s numbers above came from a page
> anyone can re-fetch. Same family as `guard-corpus-is-not-in-the-repo.md`.

**Status:** IMPLEMENTED 2026-08-09 (was: open, found 2026-08-09 reading MAS's segment 5;
substantially rewritten the same day after five research threads and a second-opinion pass
which found five load-bearing errors in the first draft)
**Size:** S
**Gate:** none. It is the only defect segment 5 surfaced that costs a customer's data
outright, the fix is ~5 lines in files we own, and it is *faster* than what we do today
**Upstream PR candidate:** yes, the seventh, and the strongest one we have — see §6

---

## 0. What happened

`https://www.thermokon.fi` was requested four times during segment 5 (2026-08-08
18:49:57, 18:53:35, 18:57:13, 19:00:52 UTC). Every one:

- rendered fine — `[COMPLETE] ● https://www.thermokon.fi | ✓ | ⏱: 7.99s`
- returned HTTP **200**, `success: true`, `failure_class` absent
- streamed **137, 136, 145, 146 MB** to the client
- ran **216 s** on the wire and ended with Envoy `ResponseFlags = DC` — the client
  gave up mid-body

Four different replicas, so it is not a replica state. The payload is ~232 MB and MAS's
client times out around 215 s, so it can never succeed. **That company is lost
deterministically, and ~565 MB of egress was spent losing it.**

Nothing in our logs says anything is wrong. `[COMPLETE] ✓`, no `RESULT FAILURE`, no
`failure_class`, no collapse-guard fire. The only surface that shows it is
`ContainerAppHTTPLogs.BytesSent`, which nothing read until 2026-08-09.

---

## 1. The mechanism, reproduced offline

`crawl4ai/content_scraping_strategy.py:510` gives every image a `desc`:

```python
"desc": self.find_closest_parent_with_useful_text(img, **kwargs),
```

and `find_closest_parent_with_useful_text` (`:414-430`) walks **up** from the `<img>`:

```python
current = element
while current is not None:
    if (current.text
            and len(current.text_content().split()) >= image_description_min_word_threshold):
        return current.text_content().strip()
    current = current.getparent()
return None
```

**The precise trigger is sharper than "the walk reaches `<body>`", and the sharper
version is what makes the upstream PR arguable.** The stop condition is a conjunction of
two *different* things: `current.text` is the element's **direct** text node (whitespace
counts — `"\n  "` is truthy), while `current.text_content()` is the **entire subtree**
text. A grid of images has zero words, so `<div class="products">` does *not* stop the
walk; the walk continues until it reaches a container that also holds the page's prose.
Measured on a synthetic catalogue:

```
img            text=None       words=0
a              text=None       words=0
div.product    text=None       words=0
div.products   text='\n  '     words=0   <- truthy .text, 0 words -> keeps walking
body           text='\n'       words=4   <- STOPS, returns the whole page
```

Two consequences worth having:

- The scrap root is the **whole document**, not `<body>` — `:671` is `body = doc` (the
  `//body` line above it is commented out). The walk can and does reach `<html>`.
- **On minified markup the same page yields `desc: None` for every image** (no ancestor
  has a truthy `.text`); on pretty-printed markup it yields the whole page. Measured:
  **45,324 B vs 11,714,724 B of `media` JSON from the same 74 KB document, differing
  only in whitespace.** That is the single strongest "this is a bug, not a design"
  argument available, and it needs no production data.

Measured on the stored render (`thermokon_rendered.html`, 2,152,629 bytes):

| | |
|---|---|
| media entries | **1,160** |
| distinct `desc` strings | **19** |
| entries carrying the *same* 154,798-char string | **1,104** |
| `media` as JSON | **231,708,565 bytes** |
| everything else in the result combined | ~3.8 MB |

`html` is 2.3 MB; `cleaned_html` 990 KB; `markdown` 761 KB; `links` 177 KB. **`media` is
60× the rest of the result put together**, and 98 % of it is one string repeated 1,104
times.

**The amplifier, corrected.** The first draft named `:392-394` (the `<source>` loop
inside `<video>`/`<audio>`) as "a second multiplier". **It is inert on the wire** — that
path writes the key `"description"` (`:385`), `MediaItem` (`crawl4ai/models.py:361-370`)
has no such field, and pydantic's default `extra='ignore'` drops it. Verified by
execution: a `<video>` with two `<source>`s produces three `MediaItem`s all with
`desc: ""`. It costs transient CPU, never response bytes.

The **real** amplifier is `add_variant` at `:517-523`, which does
`variant = {**base_info, "src": src}` — copying the `desc` into **every srcset/`<picture>`
variant of the same image**. Measured across our stored corpus: **498 surviving images
produce 1,002 media entries (mean 2.0× fan-out)**; `jpond.fi/yhteystiedot/` is **1 image
→ 6 variants**. So thermokon's "1,160 images" is almost certainly 1,160 *variants* of
far fewer images.

### Re-running it

Drive the strategy directly against stored HTML; it needs no network:

```python
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
res = LXMLWebScrapingStrategy().scrap(url, html,
        exclude_all_images=False, image_score_threshold=2,
        image_description_min_word_threshold=1)
len(json.dumps(res.media.model_dump()))     # 231,708,619 on thermokon
```

**Do not re-measure this through `AsyncWebCrawler` with `cache_mode=None`.** That is not
"no cache", it falls through to enabled, and the first run of this investigation "proved"
`exclude_all_images` had no effect because the second arm was served from cache —
identical to the byte. Use `CacheMode.BYPASS`, or better, drive the strategy directly.

---

## 2. How big is the population — n is at least 3, and two of them SUCCEEDED

**Do not re-quote "n=1 host" or "the largest successful response is 7.5 MB". Both were
true when the first draft was written and both are now stale.**

`ContainerAppHTTPLogs` (**note: no `_CL` suffix — the `_CL` name errors**), 14 days,
`Path == "/crawl"`: 4,806 × 200, p50 206 KB, p99 2.08 MB, total 2.09 GB. **10 requests
over 5 MB**, of which 4 are thermokon.

| host | when | bytes | status | outcome |
|---|---|---|---|---|
| `www.thermokon.fi` ×4 | 2026-08-08 | 137–146 MB | 200 | **`DC`** — client gave up |
| **`www.grumblo.com`** | **2026-08-09 09:22:56** | **22.1 MB** | 200 | **succeeded, `ResponseFlags = -`** |
| `www.laplandhotels.com` | 2026-08-09 10:25:43 | 5.8 MB | 200 | **succeeded** |
| `kamerastore.com` / `www.kameratori.fi` | 2026-08-09 | ~11 pages, 1.7–4.8 MB | 200 | succeeded |
| `eu.billebeino.com` | 2026-08-09 | 3 pages, ~1.5 MB | 200 | succeeded |

All are image-catalogue sites, which is the shape this defect keys on. **Nothing logs
payload composition, so "same family" is consistent-with, not proven** for the new hosts
— `grumblo.com`'s 22 MB might be a different cause, and if it is, only a response-size
guard (§3c) bounds it.

**The new hosts changed the character of the problem.** thermokon failed loudly (`DC`).
grumblo and laplandhotels **succeeded** — MAS is already storing multi-megabyte payloads
and neither side counts them. As batches grow, the fraction of catalogue sites that fit
inside MAS's 215 s budget grows too. **The successful case is invisible to every
instrument on both sides.**

**Size drives wall time steeply,** measured across batch 1's 1,364 requests:

| bytes | n | median duration | p90 |
|---|---:|---:|---:|
| < 500 KB | 1,119 | 5,037 ms | 7,807 ms |
| 0.5–1 MB | 172 | 6,561 ms | 10,839 ms |
| 1–2 MB | 56 | 7,590 ms | 12,815 ms |
| 2–5 MB | 15 | **15,457 ms** | 31,360 ms |
| ≥ 5 MB | 2 | **30,395 ms** | 30,559 ms |

`grumblo.com` **rendered in 6.77 s but held the wire 30.4 s** — ~23 s spent serializing
and shipping after the render finished. MAS's client slot pays that, and it is ~5× the
render.

**And it is a second live instance in our own corpus, which the first draft asked for.**
12 of 68 stored captures — every `jpond.fi/yhteystiedot/` capture from the 401 KB era —
walk to `<body>` and hand a **4,689-char page body to a single image, duplicated across
its 6 srcset variants**. 28,134 of that capture's 42,860 image bytes (66 %) are one
string repeated six times. **`jpond.fi` is a Tier-1 regression host and it has been
sitting in `test-aitosoft/artifacts/` the whole time.** (CLAUDE.md principle 8, question
3, paying out again.)

### Memory — the part the first draft missed entirely

Serializing the result holds roughly **3.3× the payload in RSS simultaneously**: the
dict, the intermediate `str` from `json.dumps`, and the encoded `bytes`, all live at
once. Measured on a reconstructed thermokon shape at 1/4 scale (`/proc/self/statm`):

```
rss start                  9 MB
after building the dict   50 MB   (payload ~40 MB)
after json.dumps -> str   92 MB
after .encode()  -> bytes 132 MB
```

**Production corroborates the magnitude independently, and it was not fitted to it.**
Each of segment 5's four thermokon requests produced a clean single-sample memory step on
its own replica: **+16.8, +14.7, +23.7, +23.9 points of 4,096 MB = ~688, 602, 971,
979 MB.** The offline estimate was ~760 MB. Two instruments, one offline and one from
production telemetry, bracket each other.

**What this does NOT show, and was wrongly claimed in an earlier draft of the analysis:**
the 232 MB responses did **not** cause segment 5's 80.9 % memory peak. That peak was on
`…-g47l6`, eleven minutes after the last thermokon request, on a replica that never
served it. All four replicas that *did* serve it peaked at 58–67 %, below the run's own
p95 of 66.1 %. **The excursions landed on idle-ish replicas, which is a statement about
luck, not about safety** — a +24-point excursion trips the 85 % guard from any baseline
≥61 %, and `render_capacity: 2` allows two at once (+48 points, tripping from ≥37 %,
against a median of 46.8 %).

---

## 3. What to do — and the first draft got the "where" wrong

### (a) Cap `desc` at 200 chars. This is the fix, and we can ship it ourselves.

Measured against the stored thermokon HTML:

| lever | time | `media` JSON | images kept | `cleaned_html` |
|---|---|---|---|---|
| baseline | 1.563 s | 231,708,619 | 1160 | 885,276 |
| **capped desc @200** | **1.398 s** | **535,435 — 433× smaller** | **1160** | **885,276, identical** |
| `image_score_threshold=7` | 0.210 s | 56 | **0** | 885,276 |
| `exclude_all_images` | 0.191 s | 56 | 0 | 743,483 (−16 %) |

Cap ladder: 1,000 chars → 1,755,301 · 500 → 984,709 · **200 → 535,381**.

**The cap is faster than what we do today** (it stops building 232 MB of strings), keeps
every image's `src`/`alt`/`score`, and leaves `cleaned_html` and the markdown MAS
actually reads **byte-identical**.

**The honest safety argument is not the obvious one.** A tempting claim — "healthy pages
have short descs, so a cap is a no-op" — is **false, measured**: a 200-char cap changes
`media` on **55 of 68** stored captures and a 500-char cap on **51 of 68**, including
accountor (33,490 → 19,972), solwers (21,304 → 10,371) and caverna (20,459 → 6,717).
Healthy pages routinely carry 400–1,400-char `div`-level descs.

The argument that actually holds is that **nothing reads the field.** Verified by
exhaustive grep across `crawl4ai/` and `deploy/`: `desc` is produced at
`content_scraping_strategy.py:510`, produced again at `utils.py:1330` inside the legacy
BeautifulSoup scraper (**which has no caller anywhere**), and appears once more as a
`tqdm(desc=...)` progress-bar label. **It is consumed nowhere.** Markdown is generated
from `cleaned_html`/`raw_html`/`fit_html`, never from `media`; image `score` is computed
at `:476-503`, before `desc` exists. So a cap is inert to markdown, scoring, filtering,
the collapse guard, `failure_class` and everything in `deploy/`. It changes only the bytes
on the wire.

**Prior art for the exact numbers, in upstream's own code:** `utils.py:3084`
`preprocess_html_for_schema(html_content, text_threshold=100, attr_value_threshold=200,
max_size=100000)`, called at `async_webcrawler.py:865` with `text_threshold=500`. Upstream
already truncates text nodes and attribute values to bound a payload. 200 and 500 are
upstream's own constants, not ours.

#### Where to put it — two defensible options, and the first draft assumed the wrong constraint

The first draft said the fix needed a deploy and MAS needed a workaround meanwhile,
because `api.py:876-880`'s `base_config` merge only fills keys whose current value is
`None` or `""` (`image_description_min_word_threshold` defaults to int `1`, so it would be
silently ignored — the `max_retries` trap again). **That is true of `base_config` and
false in general.**

**`CrawlerRunConfig` is decorated `@_with_defaults` (`async_configs.py:1329-1330`) — the
same upstream mechanism `aitosoft_entry.py:40` already uses for `BrowserConfig`.** So
`CrawlerRunConfig.set_defaults(...)` is a server-side lever this repo has been assuming it
does not have. Verified end to end through the real path: a default applies to
`CrawlerRunConfig.load(mas_body, provenance=UNTRUSTED)`, an explicit client value still
wins, and `clone()` preserves it.

- **(a1) Edit `crawl4ai/content_scraping_strategy.py` directly** — one slice in
  `find_closest_parent_with_useful_text`. It is an upstream file, but **we already patch
  this exact file** (`strip_noscript()`), so there is no *new* merge surface. Its decisive
  advantage: **what we ship is byte-identical to what we PR upstream**, so production and
  the patch can never diverge, and every code path is covered including ones added later.
- **(a2) Subclass `LXMLWebScrapingStrategy` and inject it via
  `CrawlerRunConfig.set_defaults(scraping_strategy=...)` in `aitosoft_entry.py`** — no
  upstream file touched, ~5 lines, all in files we own outright.

  Two things the implementing session must verify before choosing this, because both are
  load-bearing and neither is established: **(i)** `scraping_strategy` is on
  `UNTRUSTED_FIELD_ALLOWLIST["CrawlerRunConfig"]` (`async_configs.py:238`), so a client
  that sends its own `scraping_strategy` **silently bypasses our default** — check whether
  MAS ever sends one; **(ii)** whether `_with_defaults` deep-copies a default *object* per
  instance. `LXMLWebScrapingStrategy.__init__` holds two compiled regexes and looks
  stateless, but a single shared mutable instance across two concurrent renders on a
  `render_capacity: 2` replica is a real bug class, and "it looks stateless" is not a
  measurement.

**My read is (a1)**, on the strength of production == PR and no client-override hole. But
(a2) is genuinely defensible and I would not overrule an implementing session that
verified (i) and (ii) and preferred it. **Whichever is chosen, say in the file why.**

### (b) `exclude_all_images: true` — available to MAS today, and still the wrong answer

It is in `UNTRUSTED_FIELD_ALLOWLIST["CrawlerRunConfig"]` (`async_configs.py:259`), so MAS
can set it right now with no deploy of ours. Verified offline: `media` 231,708,619 → **56
bytes**.

**It is not free.** `_scrap` removes every `<img>` from the tree before processing
(`:702-707`), so `cleaned_html` drops 885,276 → 743,483 chars (−16 %) and the markdown
loses image alt text. Measured on our own captures the loss is 2.5–7.7 %. For contact
extraction that is very likely irrelevant — but it is *their* content contract, and (a)
costs them nothing at all. **Useful only as an emergency mitigation if (a) somehow cannot
ship.**

### (c) A response-size guard — the backstop, still worth building, but not first

`limits.max_body_bytes` (10 MiB, `config.yml:39`) bounds the **request**: it is consumed
by `governor.max_body_bytes_from_config` → `BodySizeLimitMiddleware`
(`governor.py:29-62`), which reads `scope["headers"]` for `content-length` on the inbound
request and 413s. **Nothing anywhere bounds the response.**

**Do not reach for the proxy — that lever does not exist.** Researched and refuted: there
is **no nginx directive that rejects or truncates an oversized upstream response**
(`client_max_body_size` bounds requests; `proxy_buffer_size` rejects oversized *headers*
only), and Envoy's `per_connection_buffer_limit_bytes` is a **soft flow-control
watermark**, not a rejection threshold. Same shape as the `--memory 8.0Gi` note: verify
the cheap lever exists before building an argument on it.

**There is a free place to measure.** `server.py:925/:929/:1009` construct
`JSONResponse(results)`, and Starlette's `Response.__init__` **already materializes
`.body`** — so `len(resp.body)` in `_crawl_response` is O(1) with **zero extra copies**.
Every other candidate (`len(json.dumps(...))` in `api.py`) costs a full extra copy of a
payload that is the problem.

**But that only prevents the transfer, not the peak** — the ~3.3× RSS has already been
allocated by the time `.body` exists. **(c) is a wire guard, not a memory guard**, which
is the argument for doing (a) first and the argument for (c) existing at all.

**The design to copy is Scrapy's**, which Firecrawl, trafilatura and eventually curl all
converged on independently (`scrapy/settings/default_settings.py:296-301`):
`DOWNLOAD_MAXSIZE = 1 GiB`, `DOWNLOAD_WARNSIZE = 32 MiB`, **two thresholds — a hard cap
that aborts and a separate warn level that only logs**, per-request overridable, `0`
disables. The warn/kill split is the same instinct as our `COLLAPSE RECOVERED` /
`RENDER DEFECT` and `CONSENT DECLINED` counters: **see the population before refusing
it.** Our p99 is 2.08 MB and the largest *successful* response is now 22.1 MB, so a warn
level around 10 MB and a kill around 50 MB is far outside observed healthy traffic. **Do
not set either near p99.**

Still open and deliberately not decided: **what class.** It is not the origin's fault and
it is not transient. Closest to `render_defect` — ours, permanent, must not be retried —
but that class currently means "no `<body>`", and widening a class to mean two things is
exactly what the `origin_blocked` inference split had to undo. A new class needs a MAS
contract note, and **MAS asked in `38-…` §7 to be told the string before it ships.**

**If you only do one thing, do (a).** It removes the cause and the memory excursion; (c)
only catches whatever the next cause turns out to be.

---

## 4. Options talked out of

- **Raise `image_description_min_word_threshold`.** The first draft rejected this after
  testing **one point (3)** and seeing `media` grow 231.7 → 236.7 MB. That reasoning
  sampled the monotonic-increase region of a function with a cliff, and the conclusion
  was right for the wrong reason. The full shape, measured: raising the threshold makes
  the walk climb **higher** before stopping (thermokon: 3 → 236,743,931; **50 →
  243,447,317, +5 %**; accountor 33,495 → 109,332 and caverna 20,459 → 78,489 at 50),
  until the threshold exceeds the page's total word count, at which point the walk
  exhausts and returns `None` and `media` collapses. **So there IS a cliff and it does
  work** — but it is still the wrong lever, for four measured reasons:
  1. **No principled bound.** thermokon needs **≥ 17,680** — that value is
     `max(len(ancestor.text_content().split()))` and scales with page word count. Corpus
     maxima: thermokon 17,691, solwers 11,253, caverna 2,069, accountor 1,397. **10,000
     would not have fixed thermokon.** Any constant is a guess against the next page.
  2. **It is slower on ordinary pages**, because the walk now always runs to the root:
     solwers **2.30×** (0.021 → 0.047 s), caverna 1.66×, accountor 1.63×; `text_content()`
     chars scanned on solwers goes **31,518 → 18,733,659 (594×)**. On 600 images injected
     into solwers's deepest real container: **0.054 → 1.844 s, 34×**.
  3. **`scrap()` is called synchronously from `async def aprocess_html`**
     (`async_webcrawler.py:832`) — `ascrap()` with `asyncio.to_thread` exists at
     `content_scraping_strategy.py:222-234` and is **unused** — so that extra time blocks
     the event loop of a replica running 2 concurrent renders.
  4. **The untrusted boundary does no type checking at all.** The field is allowlisted and
     untouched by `_clamp_untrusted` (`:293-311`, which only handles `page_timeout`,
     `wait_for_timeout`, `max_scroll_steps`, `viewport_*`). Verified: `int`, `float`,
     `inf`, `str`, `bool`, `None`, `list` and `10**400` all pass through untouched. A
     wrong *type* then gives either a `TypeError` swallowed at `:375` → **every image
     silently vanishes at `success: true`**, or on a page with `<video>`/`<audio>` (`:385`,
     no `try`) an escape to `:1013` → `Crawl4AI Error: This page is not fully supported`
     — the `norex.com` shape, client-triggerable.

  **Making an unvalidated unbounded client integer load-bearing on every request, with
  silent-total-image-loss as its failure mode, to avoid a five-line server-side cap, is
  the wrong trade.**
- **Skip `desc` when the ancestor found is `<body>`/`<html>`.** The most *targeted*
  signal, and measured it changes exactly one host in our corpus (jpond 42,914 → 1,880)
  leaving the other 67 byte-identical. **Rejected because it is not robust and the
  failure was measured:** on a synthetic 300-image catalogue it takes `media` 11,714,724
  → 45,324, but adding **one `<div id="page">` wrapper** — the single most common idiom
  in WordPress, Bootstrap and every theme framework — **defeats it completely** (back to
  11,714,724) while the char cap holds in both cases. We also cannot check thermokon's
  actual ancestor tag, so the root check might not even have fixed the reported incident.
  It is a fine *companion* to the cap (it removes a value meaningless by construction) but
  never a substitute.
- **`image_score_threshold=7`.** Provably total — the score has exactly seven `+1`
  components (`:477-500`) under a `<=` test at `:502`, and it short-circuits **before**
  the walk, so it is also the fastest (0.210 s). Rejected: it empties `media.images`
  entirely, which is the same content-contract change we rejected `exclude_all_images`
  for, without even that flag's honesty about what it does.
- **Deduplicate identical `desc` strings** (intern, or a `desc_id` reference). 1,104 of
  1,160 are byte-identical so it would also fix the size. Rejected: it changes the wire
  schema for every consumer to work around a value that should never have been 154 KB.
  Cap the value.
- **Stop copying `desc` into every srcset variant** (`:517-523`). Cuts ~half at the
  measured 2.0× mean fan-out. Not a fix — half of 232 MB is 116 MB — and it makes the wire
  shape ragged (some variants with `desc`, some without). Worth naming in the PR as the
  amplifier the cap has to survive.
- **Reject an ancestor containing many `<img>` descendants** ("this is a grid, not a
  caption"). Semantically the most correct signal — it is exactly what "nearby text"
  means. Rejected: an xpath count per walk step is O(subtree) per image, i.e. **O(n²) on a
  catalogue page**, so the pathological input becomes the pathological cost.
- **Raise our wall-clock fence, or `timeout_keep_alive`.** Nothing timed out on our side —
  the crawl finished in 8 s and the fence never fired. The 216 s is serialization and
  transfer of a payload that should not exist. **Anything that makes the transfer more
  likely to complete makes this worse** — and grumblo.com is the proof: it completed.
- **Ask MAS to raise their client timeout.** Same objection, and it would turn a
  216-second failure into a ~370-second success carrying 232 MB into their storage.
- **Drop `media` from the response entirely.** Tempting and probably harmless — but
  message 14 established they take the whole DOM deliberately and we were wrong once
  already about what they discard (`result.html`). Ask before removing; cap regardless.
- **Bound it at the ingress (nginx / Envoy / ACA).** Refuted by research, see §3c. The
  directive does not exist.

---

## 5. What I am least sure of

- **Whether MAS reads `desc`.** Nothing in this repo can answer it, and
  `deploy/docker/c4ai-doc-context.md:3529` documents the field to them. It decides whether
  (a) needs a contract note or is invisible. **Ask in the next relay** — they asked in
  `38-…` §7 to be told deltas in advance, so this is owed anyway.
- **Whether `grumblo.com`'s 22.1 MB is this mechanism.** It is a catalogue site and it
  fits, but nothing logs payload composition and I did not fetch the page. If it is a
  *different* cause, (a) does not touch it and only (c) does. **Do not present n=3 as
  three confirmed instances of this bug.**
- **Whether the `<source>` inertness holds for every media type.** I verified `<video>`
  with two `<source>`s produces `desc: ""`. I did not enumerate `<picture>`, `<audio>` and
  `<track>` separately.
- **The 3.3× RSS amplification** is measured on a synthetic of the right shape, not the
  real payload, and Python's string representation shifts it: my filler was ASCII, and a
  Finnish page with non-Latin-1 characters makes the intermediate `str` 2× larger than the
  final `bytes`, pushing the factor toward 4–5×. The production step measurements
  (600–980 MB) are the better number.
- **Whether 216 s is MAS's client timeout.** Consistent across four attempts, well under
  ACA's 240 s ingress timeout, and `DC` means the downstream closed — so it is theirs. We
  asked in `36-…` §8 and **the answer is in message 37, which is not on disk** (see §7).
- **Whether the corpus generalises.** 68 captures but only **5 distinct hosts**, all
  Tier-1 Finnish B2B sites, and **not one product catalogue among them**. "The cap changes
  55/68 captures" is trustworthy; "healthy traffic maxes at 43 KB of `media`" is 5 hosts,
  not a population.

---

## 6. The upstream PR — stronger than the first draft rated it

The first draft argued "this value is too big". The research turned up a better argument
that needs **no numbers from our production corpus at all**:

**No comparable extractor manufactures an image description by walking the DOM upward.**

| tool | per-image output | description field |
|---|---|---|
| Firecrawl | flat `images?: string[]` of resolved URLs | **no** — alt text not even collected |
| Scrapy | `ImagesPipeline` stores files | **no** text metadata at all |
| trafilatura | `handle_image()` copies exactly `src`, `alt`, `title`, verbatim | **no** |
| mozilla/readability | images survive inside the `content` HTML string | **no image array at all** |
| unstructured | `image_path` / `image_base64` / `image_mime_type` | **no text description** |
| **html2text** (the converter we already ship) | `alt = attrs.get("alt") or self.default_image_alt` | **no** |

**The conventional answer is that an image's description is its `alt` attribute** —
author-supplied, bounded by the markup, empty if absent. crawl4ai's `desc` has no
precedent, and the unbounded version appears to be unique.

Pair that with upstream's **own** documented contract — `docs/md_v2/core/link-media.md:571`
describes `desc` as *"a snippet of nearby text or a short description"*, and illustrates it
with an ellipsised whole-page-nav string, so **the bug is visible in upstream's own
documentation example** — and the PR writes itself. The whitespace measurement from §1
(45 KB vs 11.7 MB from the same document, differing only in indentation) is the clincher.

**Blast radius, verified: zero.** No file in `test-aitosoft/` references `media` or `desc`
in any assertion, and **`test_mas_contract.py` contains no `media`/`desc`/`image`
reference at all** — `desc` is not part of any pinned contract. Upstream's own tests
(`tests/async/test_content_extraction.py:45-48`,
`tests/regression/test_reg_content.py:262-311`) assert only that `src`/`alt`/`type`/`score`
keys exist and that hero scores beat icon scores. A cap keeps the key and its type. None
can fail.

---

## 7. Two process notes for whoever picks this up

**Messages 34 and 37 are missing from `tmp/mas-repo-messages/`** (29 and 30 too). `37-…`
is where MAS answered the six asks in `36-…` §8 — including whether their client timeout
is 215 s, what they decided about `exclude_all_images`, and **whether to bundle a
deploy**. `38-…` leaks fragments of it (their "media suppression without
`exclude_all_images`" counter-proposal was `37-…` §3). **Ask Tero to re-relay 34 and 37
before any deploy decision** — the bundle answer is currently unknowable from this repo.

**MAS's `37-…` §3 counter-proposal is answered by (a), better than by what they asked
for.** They want `media` suppressed without losing `cleaned_html` to
`exclude_all_images`. The `desc` cap gives them exactly that — 433× smaller `media`,
`cleaned_html` byte-identical, every image's `src`/`alt`/`score` retained — and it costs
them nothing and requires no change on their side. **Tell them the cap value and the
field before it ships**, per their `38-…` §7 ask.
