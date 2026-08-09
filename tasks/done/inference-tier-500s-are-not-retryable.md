# A structurally-intact non-page is not "blocked", and 500 buys three retries of nothing

> **CLOSED UNFIXED 2026-08-09. The measurement below is sound; the fix it argues
> for is refuted by the only corpus that could refute it, and building it would
> have caused the exact harm this repo's taxonomy exists to prevent.**
>
> This file asks to mark small structurally-intact pages **permanently** dead
> (`unrenderable_content` / `render_defect` at 200, non-retryable). It names
> `www.ktth.fi`, the `laatutrio.fi` apex paths and `www.mi.com/fi` as members.
> **MAS checked them against 117,000 stored pages
> (`tmp/mas-repo-messages/40-…` §2) and three of the four are transient:**
> `www.ktth.fi` returned **14,542 characters of real content on 2026-04-17**,
> and the `laatutrio.fi` apex paths yielded **21,234 and 14,564 chars on
> 2026-08-08** — the day this file called them deterministic. `mi.com/fi` has
> been attempted exactly once ever, which is absence of evidence.
>
> So the population is not permanently unrenderable, and the proposed change
> converts a recoverable miss into **silent permanent loss on live sites**. MAS
> asked us not to build it and recommended the effort go to the `desc` cap
> instead. Their words: *"the cost you are trying to remove is ours, it is
> small (~1.5 % of a batch's wall clock), and the fix carries a risk of silent
> data loss that is much larger than the saving."* Agreed, and it is the right
> call — **this is the second time a cost-hygiene item of ours has been argued
> down by the consumer whose cost it was.**
>
> **PDFs, which this file absorbed, are also settled and also not ours to fix:**
> MAS is removing them at dispatch (their extension blocklist gates which links
> they *offer* the agent, never which URLs they *fetch* — that is the defect,
> and it is theirs).
>
> **Four findings inside survive the refutation and have been rehomed. Do not
> mine this file for them; go to the durable copy:**
>
> 1. **`browser_manager.py:1123-1128` silently downgrades `chrome_channel:
>    "chromium"` to the headless shell, so our browser suite has never run
>    production's browser — and CI never runs `test-aitosoft/` at all.** Now a
>    CLAUDE.md Key Findings row, `TESTING.md`'s arm64 section, and the comments
>    at `fixture_origin.py` `DOWNLOAD_KINDS_THAT_REFUSE_TO_RENDER` and
>    `test_fixture_origin.py`'s download test. **Re-measured on both arms
>    2026-08-09: 4 of 5 download kinds identical, `pdf-inline` alone diverges,
>    and the 174-byte viewer shell reproduces byte-for-byte on this arm64
>    machine at zero live traffic.** The fixture work §7 argues for is still
>    valid and still unbuilt; it is *test* work, and it did not need this file's
>    classification change to be worth doing.
> 2. **`response_headers` is the FIRST redirect hop and there is no final-hop
>    equivalent field.** Now a CLAUDE.md row beside the `redirected_status_code`
>    one. This is the finding most likely to bite someone who never reads this
>    file.
> 3. **`unrenderable_content` has fired zero times in production, ever.** Folded
>    into the corrected CLAUDE.md download row and the `aitosoft_failure_class.py`
>    comment. The class is correct for the four kinds it covers; it simply does
>    not cover PDFs, and CLAUDE.md said otherwise for a week.
> 4. **`PDFContentScrapingStrategy` is reachable from an untrusted request body**
>    and does a blocking `requests.get` on the event loop, bypassing
>    `validate_url_destination` and the pinning proxy. Latent (our only client is
>    trusted and token-gated), but it is a real hole in upstream's boundary —
>    tracked in `tasks/file-upstream-prs.md`.
>
> **One correction this file made that outlives it, and it belongs to item 7:**
> `render_error` is **not** in `NON_RETRYABLE_CLASSES`
> (`aitosoft_failure_class.py:129-133`), so `tasks/README.md`'s item 7 as written
> would have saved **zero** of batch 1's 18 events. Items 6 and 7 were listed as
> independent and were not.
>
> **What would re-open this:** a page in this class that MAS can show has *never*
> succeeded across a meaningful number of attempts. One attempt is not evidence.

**Status:** CLOSED UNFIXED 2026-08-09 (was: open; item 6 in `tasks/README.md`)
**Size:** was S for the classification change; XS for the fixture, which survives
**Gate:** none
**Upstream PR candidate:** the fixture finding, probably not. The `is_blocked` signature
question, maybe — see §5

---

## 0. The class, in one line

Our anti-bot detector's **tier-3 structural inference** says "blocked" for any small page
with little visible text and no content elements. When the origin's status is 200 the
inference cannot map to `origin_blocked`, so it falls through to `render_error` → **HTTP
500 → MAS retries 3×** → each retry costs us a playwright leg *and* a patchright leg for a
guaranteed-identical result.

**These pages are not blocked. They are not pages.**

---

## 1. Size, from three workloads and two instruments

| workload | inference-tier 500s | of total 500s |
|---|---|---|
| segment 2 (2026-08-06, 50 co) | 12 events, 2 domains | — (deflated at the time) |
| segment 5 (2026-08-08, 318 co) | **54 events, 7 hosts** | **78 %** of 69 |
| batch 1 (2026-08-09, 200 co) | **16 events, 3 hosts** | **89 %** of 18 |
| 14-day total | **~100 events of 119 `render_error`, 36 URLs** | **84 %** |

Batch 1 is the population that matters most: it is the **known-resolving, already-scraped
cohort**, which is the only one that resembles the real sweep (MAS makes this point
themselves in `38-…` §3, and it cuts against their own earlier baselines as much as ours).
On that cohort the class is **16 of 1,364 requests = 1.2 %**.

**MAS's own 500 count is 4 low.** They reported 14; two of our instruments independently
say **18** (`ContainerAppHTTPLogs | where StatusCode == "500"`, and
`failure_class=render_error` in the console logs). Every repeated URL got a **fourth**
attempt they did not list. That is a 29 % undercount of the wire cost and it changes the
PDF arithmetic below. **Tell them.**

---

## 2. The three members of the class, with verbatim evidence

All three are `failure_class=render_error status=200`, all fired the patchright tier, all
logged `STILL blocked`.

### (a) PDFs — the new one, and the one our record was wrong about

```
2026-08-09 10:34:39,178 - api - WARNING - RESULT FAILURE:
  url=https://parikkalanvalo.fi/wp-content/uploads/2026/05/pava-vuosikertomus-2025_web.pdf
  failure_class=render_error status=200
  error=Blocked by anti-bot protection: Structural: minimal_text, no_content_elements (174 bytes, 0 chars visible)
```

**`page.goto` succeeded.** `[FETCH] ✓ 3.47s`. We captured 174 bytes of HTML. Real Chrome
(`chrome_channel: chrome`, installed by the Dockerfile) ships the **PDFium viewer**, so it
renders a PDF inline into a shell instead of downloading it.

**The 174 bytes, verbatim — and there is no `<embed>` in them:**

```html
<!DOCTYPE html><html><head>
    <link rel="stylesheet" href="chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/pdf_embedder.css">
  </head>
  <body>


</body></html>
```

The `<embed type="application/pdf">` lives in the viewer's **shadow DOM** and never
reaches `page.content()`. **A fix keyed on `<embed>` would never fire** — an earlier draft
of this analysis proposed exactly that. The only PDF-identifying token in the capture is
the `chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/` stylesheet.

Then `antibot_detector.py:429-456` tier 3: 174 B is under `_STRUCTURAL_MAX_SIZE`; `<body>`
**is** present (so the `render_defect` no-body path is correctly skipped); `visible_len =
0` → `minimal_text`; `content_elements = 0` (`_CONTENT_ELEMENTS_RE` at `:296-298` is
`<(?:p|h[1-6]|article|section|li|td|a|pre)`, and the shell has none) → two signals ⇒
blocked. `classify_error_text` then matches `_INFERRED_BLOCK_RE`, the effective status is
**200** so no status branch fires, it returns `None`, and `classify_result` falls through
to `render_error` → 500.

**Cost, counted directly from the logs, not modelled:**

```
admits=8  fetches=32  completes=16  patchright=8  resultFailure=8
```

**8 wire requests, 32 navigations, ~236 s of render slot, for two documents that can never
succeed.** The shape is deterministic: `3.4 s + 3.2 s` (playwright + its `1/1` anti-bot
retry) then `11.4 s + 11.3 s` (patchright + its retry) = ~29.5 s per attempt, eight times.

14 days, every `.pdf` that reached us: **12 events, 3 URLs, 2 hosts** (`parikkalanvalo.fi`
×2 docs on 08-09, `www.turkusteve.com` on 08-06), always exactly 4 attempts, always
`render_error`. **12 of 12 `.pdf` requests failed; 0 succeeded.** That is **0.33 % of
3,584 `/crawl` requests** and ~272 s of render slot per 14 days.

### (b) Un-hydrated shells

```
www.ktth.fi    Structural: minimal_text, no_content_elements (265 bytes, 0 chars visible)
www.mi.com/fi  Structural: minimal_text on small page (3066 bytes, 29 chars visible)
```

`ktth.fi` is the same two-signal branch. `mi.com/fi` is the **one-signal** branch
(`:455`, `signal_count == 1 and html_len < 5000`) and is the most interesting case in the
whole class: **`www.mi.com/global`, `/global/about/`, `/global/about/founder/` and
`/global/about/social` all succeeded in the same window, same host, same replica pool.**
So the failure belongs to that one page, not to mi.com refusing us. It is the classic
un-hydrated SPA shell — **and that is exactly why a permanence verdict here is the least
defensible part of this task.**

### (c) Apex stubs — the original evidence

`laatutrio.fi` served `187 bytes, 20 chars visible` on **9 URLs, 31–35 events**, every
attempt, while `https://www.laatutrio.fi` rendered fine in 3.90 s. Also
`www.kattoconsulting.fi` (1,482 B / 0 chars), `www.lahdenrakenneteras.fi` (57 B at 200),
`www.sammio.fi` (161 B), `neco.fi`, `www.skanno.fi`, `kubler.fi` (15 B ×8),
`nieminen.lol` (83 B ×8).

---

## 3. What our own record got wrong, and why it matters

**`unrenderable_content` has fired zero times in production, ever.** 30-day query:
`unrenderable=0`. Its trigger phrase `Download is starting` appears **16 times, all on
2026-08-01T16:09** — the vCard incident that motivated the class, on revision `--0000033`,
**the day before the class shipped**. Since 2026-08-02: zero.

CLAUDE.md's Key Findings row says inline `application/pdf` "behaves exactly like
`Content-Disposition: attachment`". **That is false in production**, and
`tasks/done/download-navigation-is-not-a-render-error.md:27-30` said so at the time:

> This also answers the file's own open PDF question: **yes**, on Playwright's bundled
> Chromium. Production runs real Chrome, which ships a PDF viewer, so the inline-PDF row
> could differ there; the attachment rows cannot.

The caveat was written, published, and then read as settled by everyone downstream —
including the CLAUDE.md row, which dropped it. **Fix that row.**

### The fixture blind spot, and it is fixable today

`test-aitosoft/fixture_origin.py:605-648` serves five download kinds including
`pdf-inline` (real, valid PDF bytes, `Content-Type: application/pdf`, **no** disposition
header). `test_fixture_origin.py:691-728` asserts 200 + `unrenderable_content` +
`"Download is starting"` for all five, and passes. The fixture even defines a tripwire —
`DOWNLOAD_KINDS_THAT_REFUSE_TO_RENDER` with a comment at `:619-624` naming *"a real-Chrome
PDF viewer"* as the live candidate — and concluded we could not check it here.

**We can. The blocker was our own code, not the architecture.**
`crawl4ai/browser_manager.py:1126-1127`:

```python
if self.config.chrome_channel and self.config.chrome_channel != "chromium":
    browser_args["channel"] = self.config.chrome_channel
```

a Windows workaround that **silently drops `channel="chromium"`**, so `chrome_channel:
"chromium"` gives you Playwright's *headless shell* — a different binary with no PDF
viewer and no extensions, which downloads. Playwright's **full** Chromium build (`channel="chromium"`
explicitly, new headless) carries the same PDF extension as real Chrome and produces the
**byte-identical 174-byte capture and the identical reason string on this arm64
machine**, verified twice independently.

So: a test-local channel override reproduces the production defect offline, at zero live
traffic. **This satisfies TESTING.md golden rule 0 outright and it is the single
highest-value thing in this file.** The two arms fail in *opposite* directions and the
production one is the dangerous one: the headless shell raises loudly, while new headless
returns HTTP 200 with an empty shell that only the inference tier catches — and
mislabels.

---

## 4. Design space

**The axis is permanence, not ownership** (`aitosoft_failure_class.py` module docstring
already says this) — and **do not re-open the inference tier's byte bounds**, which are
deliberate and were argued out in `tasks/done/detector-round3-evidence-vs-inference.md`.

### (a) Fix the classification of an inferred block at status 200

Today: inference + status 200 → `None` → `render_error` → 500 → retried.

The question is what it *should* be. Candidates, none free:

- **`unrenderable_content`** (exists, 200, in `NON_RETRYABLE_CLASSES`, already announced
  to MAS in message 12). Honest for a PDF. **Dishonest for `mi.com/fi`**, which is a real
  HTML page that failed to hydrate.
- **A new class.** Needs a MAS contract note, and MAS asked in `38-…` §7 to be told the
  string before it ships. Weigh against the `origin_blocked` inference split, which had to
  *undo* a class that meant two things.
- **Leave the class, change only retryability.** The cheapest, and it decouples "what do
  we call it" from "should MAS retry it".

### (b) The content-type route, and why it is harder than it looks

The obvious fix — read the response content-type and classify non-HTML as
`unrenderable_content` — has **three problems, all measured**:

1. **`response_headers` is the FIRST redirect hop, not the final.**
   `async_crawler_strategy.py:878-886` walks `redirected_from` back to the earliest
   response and assigns `response_headers = first_resp.headers`. There is **no final-hop
   headers field anywhere** (`models.py:331-345`, `:148`). Measured on our own fixture:
   `/download/pdf-inline` → `application/pdf` ✓, but `/redirect-to/download/pdf-inline` →
   `text/html; charset=utf-8` ✗. **So the check silently no-ops on any PDF reached through
   `http→https` or `apex→www`** — and MAS's agent constructs URLs it never saw. This is
   the documented `status_code` / `redirected_status_code` trap, one field over, and we
   have been bitten by it before.
2. **The class is not PDF-specific.** An `image/png` URL produces the identical defect:
   419 bytes, `Structural: minimal_text, no_content_elements`, `is_blocked=True` — and its
   shell has **no** `chrome-extension://` marker. So content-type is the more general
   signal and must cover `image/*`, while any extension-marker or `<embed>` check is
   PDF-only. (There were **0** image URLs in 14 days of logs, so the population today
   really is PDFs.)
3. **It must be an allowlist of known-unrenderable types, never a `!= text/html` test.**
   `application/xhtml+xml` renders fine. A missing Content-Type must not fire (browsers
   sniff). An origin serving `application/pdf` for an HTML error page is fine either way —
   Chrome renders it as a PDF regardless, so `unrenderable_content` stays behaviourally
   honest.

**The conventional design, for reference** — every comparable tool does the same three
checkpoints, cheapest first: URL extension before any I/O (Firecrawl checks
`.endsWith(".pdf")` and never touches the browser); Content-Type allowlist on the response
(Crawlee: `text/html`, `text/xml`, `application/xhtml+xml`, `application/xml`,
`application/json`, extensible, **with `request.noRetry = true`** — our permanence axis
under another name); magic bytes, because headers lie (Firecrawl sniffs `%PDF` in a
1024-byte window; `unstructured` and Tika both rank magic bytes **above** the asserted
Content-Type). Nobody uses HEAD for this — an extra round trip that can still lie.

### (c) Where the check has to go, and why it is two changes not one

`is_blocked` (`antibot_detector.py:489`) is called at `async_webcrawler.py:546` inside the
retry loop and again at `:674`. `antibot_detector.py` is **already ours** (371 lines
changed vs `upstream/develop`), so there is no new merge surface — **but its signature is
`(status, html)`**, so a content-type check cannot go there without changing it. That is
the part worth thinking about before writing code.

And **if `is_blocked` simply returns False, the result becomes `success: true` with 174
bytes and no markdown** — a green empty page, the exact silent-loss shape this repo keeps
getting bitten by. **Suppressing the retry and classifying the result are two separate
changes**, and doing only the first is worse than doing nothing.

The patchright leg is **already open as item 7** (`_is_blocked` at
`aitosoft_patchright_fallback.py:163` gates on the block-marker string rather than
classified permanence). Note the README's framing of item 7 is wrong on one point:
`render_error` is **not** in `NON_RETRYABLE_CLASSES` (`aitosoft_failure_class.py:129-133`),
so "gate the retry on classified permanence" as written would have saved **zero** of batch
1's 18 events. **Items 6 and 7 are coupled and the README presents them as independent.**
Measured cost of the useless patchright leg: 6.7 s → 22.7 s per attempt, ≈290 s of render
slot in batch 1 alone.

---

## 5. Options talked out of

- **Build a bespoke PDF fix now.** Rejected. PDFs are **12 % of the class this file
  describes** and 0.33 % of requests. The permanence axis covers them for free, needs no
  headers, no content-type and no browser-version-dependent marker. Building a separate
  content-type path first spends the budget on the smaller subset and creates a second
  mechanism this task then has to reconcile with.
- **Adopt upstream's PDF support.** `crawl4ai/processors/pdf/` ships `PDFCrawlerStrategy`
  + `PDFContentScrapingStrategy`. Rejected on five independent grounds, any one
  sufficient: it needs `pypdf`, an optional extra **not in our image** (`Dockerfile:144`
  installs `deploy/docker/requirements.txt`, 16 lines, no pypdf); `crawler_strategy` is an
  `AsyncWebCrawler` **constructor** argument, so it is whole-crawler not per-request;
  `PDFContentScrapingStrategy._get_pdf_path` does a **blocking `requests.get(url,
  stream=True, timeout=(20, 600))`** and `async_webcrawler.py:832` calls `scrap()`
  **synchronously on the event loop** (`ascrap()` exists and is unused) — a 600 s blocking
  call on a `render_capacity: 2` replica, `resolve_and_pin` an order of magnitude worse;
  that `requests.get` **bypasses `validate_url_destination` and the pinning egress proxy
  entirely**; and MAS does not want PDF *content* anyway — `pdf` has always been in their
  `BLOCKED_EXTENSIONS`.
  **Worth flagging separately:** `PDFContentScrapingStrategy` is in
  `UNTRUSTED_ALLOWED_TYPES` and `scraping_strategy` is in
  `UNTRUSTED_FIELD_ALLOWLIST["CrawlerRunConfig"]` (`async_configs.py:194`, `:238`), so that
  blocking, proxy-bypassing fetch is **reachable from a request body**. Our only client is
  trusted and token-gated, so this is latent rather than live — but it is a genuine hole
  in upstream's own untrusted boundary and a candidate for both an upstream report and a
  one-line tightening in `aitosoft_trust.py`.
- **Key on `<embed type="application/pdf">`.** Would never fire — shadow DOM, §2a.
- **Key on the `chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/` stylesheet.** It is
  the only PDF marker in the capture and it does work today, but it is a Chrome extension
  ID: PDF-only (misses `image/*`), and it silently stops matching if Chrome changes the
  viewer. Acceptable as a *fixture assertion*; not as production classification.
- **Do nothing, because MAS is fixing it at dispatch.** They said in `38-…` §4 that their
  `BLOCKED_EXTENSIONS` gate never ran on the dispatch path and that fixing it is small and
  theirs. **But it had not shipped as of batch 1:** their `aitosoft-edge` has been on
  `v0970-dispatch-egress-guards` since 2026-08-08 09:36, and at 10:34 on 08-09 both PDF
  URLs were still dispatched and still retried 4× each. So "MAS is fixing it" is an
  intention, not an observed fact. **One line in the next relay, not a code change** — and
  worth noting their fix removes the *PDF* subset only, leaving (b) and (c).
- **Make the inference tier less eager / re-open its byte bounds.** Explicitly rejected,
  and the record already settled it: the bounds are deliberate, and
  `tasks/done/detector-round3-evidence-vs-inference.md` plus the `norex.com` history
  explain why. The defect is not that the tier fires; it is what the *verdict maps to*.

---

## 6. What I am least sure of

- **Whether `mi.com/fi` belongs in this class at all.** A 3,066-byte shell serving 29
  visible chars is plausibly a *timing* failure a retry can genuinely fix, unlike a
  187-byte apex stub or a PDF. **Making it permanent converts a retryable transient into a
  silent permanent loss**, which is the exact direction the taxonomy exists to prevent
  (`aitosoft_failure_class.py`'s "Classification bias" section). It is also the best test
  case available, because the same host's `/global*` pages succeeded in the same window.
  **If the design cannot separate (a)+(c) from (b), ship only (a)+(c).**
- **Whether the 4th attempt is MAS's retry ladder or something else.** Every repeated URL
  got exactly 4, and MAS reports 3 retries. 1 + 3 = 4 fits, but I did not confirm it
  against their client config and they only listed 3.
- **Whether `is_blocked`'s signature can take a content-type without disturbing its other
  ~8 call sites.** I read the two in `async_webcrawler.py`; I did not enumerate the rest.
- **Whether the new-headless channel override is stable across Playwright versions.** It
  reproduced twice on this machine at Chromium 145. The viewer is an extension, and
  extension loading in headless has changed before. **Assert the reason string, not the
  byte count** — 174 is the current shell, not a contract.
- **The exact 14-day inference-tier count.** "~100 of 119" comes from classifying reason
  strings, and `laatutrio.fi`'s events were counted as 31 in one query and 35 in another
  (`36-…` §4a says 35). The 84 % figure is robust to that; a precise count is not.

---

## 7. If you only do one thing

**Land the fixture.** It costs no live traffic, it needs no classification decision, and
it converts our single most consequential unverified production claim into a test — one
that the repo explicitly believed was untestable here. Everything else in this file is a
judgment call about permanence that will be better made with the reproduction in hand.
