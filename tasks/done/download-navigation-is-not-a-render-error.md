# A URL that downloads instead of rendering costs four renders and returns 500

**Status:** **DONE 2026-08-02**, shipped in one image with the collapse-guard
recovery. Opened the same day from production logs.

> **Three things in this file were wrong, and one of them was the causal chain.**
>
> 1. **Step 4 is the wrong function.** `classify_exception()` never runs for
>    this. Upstream's `arun` wraps its entire body in `try:`
>    (`async_webcrawler.py:256`) and returns a failed `CrawlResult` at `:742`
>    instead of re-raising, so the verdict comes from **`classify_result`**. Two
>    independent proofs: the reproduction returns a failed result, and the
>    production log line's own prefix (`Crawl request failed: …`) is built at
>    exactly one place — `server.py:933`, the *result* path. The exception path
>    would have logged `{"error": …` JSON. The patch site is unchanged, because
>    both funnel through `classify_error_text`; what changes is the test and the
>    text to match. The same wrong mechanism is asserted in
>    `aitosoft_failure_class.classify_exception`'s docstring, in `api.py`'s
>    comment and in `AITOSOFT_CHANGES.md` — corrected in the docstring, which is
>    the one a future session will read.
> 2. **`Content-Disposition: attachment` is not the trigger.** Measured through
>    the browser: an inline `text/vcard`, an inline `application/pdf` and an
>    `application/octet-stream` all raise the byte-identical
>    `Page.goto: Download is starting`. The rule is "Chromium will not render
>    this inline". A fixture varying only the header would have sized the
>    population wrong — the same unfaithful-fixture failure the padded-403 route
>    already cost us once. This also answers the file's own open PDF question:
>    **yes**, on Playwright's bundled Chromium. Production runs real Chrome,
>    which ships a PDF viewer, so the inline-PDF row could differ there; the
>    attachment rows cannot.
> 3. **"Charged four renders" undercounts.** Upstream's attempt loop retries on
>    **any** exception, not only on a detected block, so one client request at
>    MAS's `max_retries: 2` is **three** navigations. Four client requests were
>    8-12 page loads, not 4. Measured: `max_retries` 0/1/2 -> 1/2/3 origin hits.
>    That makes the fix worth more, not less — and it is checkable with zero live
>    traffic, because `crawl_stats.attempts` already ships in the envelope MAS
>    stores.
>
> Also checked, because it is the cheap lever this file did not name:
> **`accept_downloads: true` does not rescue it.** `page.goto` still raises (the
> escape hatch at `async_crawler_strategy.py:856` requires `net::ERR_ABORTED`,
> which Playwright does not emit here), and the download handler then dies with
> `Target page … has been closed`, leaving a partial file on disk. There is no
> configuration that turns this into a successful render.
**Priority:** Medium. Small population per site, but it recurs on exactly the
pages MAS crawls for — contact pages are where vCard and PDF links live — and
every occurrence is charged four renders instead of one.
**Effort:** XS for the classification. The contract question attached to it is
the part worth thinking about.
**Risk:** Low, but it touches `classify_error_text`, whose documented bias is
deliberate — read §"Why this is not just a missing pattern" before adding a line
to the table.
**Evidence:** Log Analytics, revision `--0000033`, 2026-08-01 16:09 UTC. Zero
live requests to produce it.

## What happened

One URL in MAS's 2026-08-01 evening run produced every HTTP 500 the whole run
emitted — four of them, 3 seconds apart:

```
https://www.grantthornton.fi/PeopleService/GetVCard?contentGuid=…&lang=fi

server - ERROR - server error 500 [cid=…]: Crawl request failed:
  All proxies failed: Failed on navigating ACS-GOTO:
  Page.goto: Download is starting
  Call log: - navigating to "https://www.grantthornton.fi/PeopleService/GetVCard?…",
  waiting until "domcontentloaded"
```

Four hits = one attempt plus MAS's three retries. That is the whole mechanism:

1. The endpoint answers with `Content-Disposition: attachment` (a vCard).
2. Chromium refuses to commit a navigation to a download and `page.goto` raises.
3. The text carries no `net::ERR_*`, no block marker, no timeout phrase and no
   origin status, so `classify_error_text()` returns `None`.
4. `classify_exception()` falls through to its default — `RENDER_ERROR`.
5. `http_status_for` maps `render_error` to **500**, which MAS retries 3×.

Three of the four renders were guaranteed waste before they started. The same
URL will do the same thing on every visit, forever.

## Why this is not just a missing pattern

`aitosoft_failure_class.py` documents its default deliberately:

> Unrecognised failures classify as `render_error` (ours, 500, retryable), not
> as an origin class. Getting it wrong in that direction costs wasted renders
> and is loud. Getting it wrong the other way tells MAS a healthy company site
> is permanently broken, silently.

That bias is correct and must not be weakened. This case is not an argument
against it — it is a case that has *left* the unrecognised set: "Download is
starting" is a complete, unambiguous statement about what the URL is. So the
work is to recognise it, not to change what happens to things we do not
recognise.

The axis the taxonomy learned on 2026-08-01 applies directly here:
**permanence, not ownership** (`NON_RETRYABLE_CLASSES`). This failure is nobody's
*fault* — the origin is healthy and we are working correctly — and it is
absolutely permanent.

## The decision this needs, which is why it is a task and not a one-liner

Which class does a download URL get? The vocabulary today has no member that
means *"the origin answered correctly, with something that is not a web page"*.
Three candidates, none obviously right:

| candidate | argument for | argument against |
|---|---|---|
| `origin_http_error` | already non-retryable, already 200, no contract change at all | it is a lie — the origin did not error, it served a file successfully |
| a new class (`unrenderable_content`?) | says what actually happened; MAS may want to branch on it | a new class is a contract change; message 09 says they read the *status*, not the class, so it buys diagnosis only |
| `render_defect` | ours, permanent, already wired | wrong meaning — nothing collapsed in our parse, and blurring it costs the one class that currently means something precise |

**Recommendation, not a decision: the middle one.** The wire status is the
contract and all three give 200, so the choice is purely about what our own logs
and MAS's stored corpus say a year from now — and that is exactly the case where
an honest name is worth a cheap contract addition. But a new class should be
*announced*, not discovered, so if it ships before the next relay it ships as
`origin_http_error` with a comment, and gets renamed when MAS has been told.
Whoever implements: pick one, write down why, and say if you disagree with this.

### DECIDED 2026-08-02: a new class, `unrenderable_content`, shipped as such

Agreeing with the recommendation on the class and **disagreeing with the
fallback** — it does not ship as `origin_http_error` pending a relay. Three
reasons, in order of weight:

1. **`origin_http_error` is the module's own documented failure mode running
   backwards.** `aitosoft_failure_class.py`: *"Getting it wrong the other way
   tells MAS a healthy company site is permanently broken, silently."* A working
   vCard export is a healthy site. This repo has already paid for that lesson
   once, as `norex.com` — our own placeholder page reported to the customer as
   the origin blocking us.
2. **A measurement the file did not have makes it worse than "a lie".** Upstream
   leaves `status_code` unset when the navigation never commits, so the result
   carries `status_code: null`. `origin_http_error` with a null status is a lie
   *visible in the one field MAS was promised holds the origin's real final
   status*.
3. **A new class value is additive, and `tasks/README.md`'s own rule is that
   additive changes ship and get announced.** No new field, no changed status, no
   changed meaning for an existing value; MAS's retry branch keys on the wire
   status and `failure_class` is received, logged and unread (their message 09).
   Holding it back would be letting a relay block a deploy, which is the coupling
   that already dropped the `fodbar.fi` field from a finished image.

It is in `NON_RETRYABLE_CLASSES` and deliberately **not** in `ORIGIN_CLASSES`:
the axis is permanence, not ownership, and here the answer to "whose fault" is
*nobody's*.

**A second mapping site fell out of the change, and it was latent.**
`api.py`'s exception handler gated its 200-envelope branch on
`_exc_class in ORIGIN_CLASSES` rather than on `http_status_for` — exactly the
"one class, two wire statuses" defect MAS found in July, in the one place the
2026-08-01 fix did not reach. It could not fire, because no
non-retryable-but-not-origin class could reach that handler; `unrenderable_content`
can. Now `if http_status_for([_exc_class]) == 200:`, which is behaviour-identical
today. The `ORIGIN FAILURE` log token is kept for origin classes (Log Analytics
queries key on it) and a sibling `TERMINAL FAILURE` covers the rest.

**Not built, and worth saying to MAS rather than building:** `render_mode:
"static"` would fetch that vCard's body with httpx and hand them the actual
contact card — the very data they were crawling the page for. That is a
client-side routing decision, not ours to make, and they already have the
mechanism (they auto-pivot to static after 2 consecutive 504s per host). Mention
it in the next relay alongside the new class.

## Sizing, honestly

One URL in 328. That is the entire direct evidence, and it is thin — do not
inflate it. What makes it worth an XS task rather than a backlog note is the
multiplier and the population it sits in: MAS crawls contact and people pages by
design, vCard exports are a standard feature of exactly those pages on
professional-services sites, and each hit is charged 4× at the moment capacity
is most likely to be tight. At sweep scale that is the difference between a
rounding error and a visible slice of the render budget.

If the next sweep shows zero further instances, close this file. One data point
that never repeats is a data point, not a defect.

## Verification — done 2026-08-02, zero live requests

- `fixture_origin.py` `/download/{kind}`, five kinds in a `DOWNLOAD_KINDS` table
  (`vcard`, `vcard-inline`, `pdf-attachment`, `pdf-inline`, `octet-stream`) so a
  new shape is a dict entry, never a new route. The PDF is a real, structurally
  valid one-page file built by hand — the inline case asks whether Chromium
  hands it to a viewer, and a malformed file would answer a different question.
  `DOWNLOAD_KINDS_THAT_REFUSE_TO_RENDER` is a measured set: a kind that starts
  rendering fails the suite rather than quietly leaving it.
- `test_a_download_is_not_a_retryable_server_error`, parameterised over all five,
  through `production_path.crawl`: HTTP **200**, `success: false`,
  `failure_class: unrenderable_content`. Run at `max_retries=2` on purpose —
  at the default of 0 the error text reads `Unexpected error in _crawl_web …`
  and at 1+ it reads `All proxies failed: …`, so a test at the default would
  have pinned a wrapper production never produces.
- `test_a_download_costs_a_page_load_per_retry_round` pins the multiplier from
  both sides — the origin's own hit count and `crawl_stats.attempts`.
- `test_a_download_url_is_recognised_in_every_wrapper` runs all three wrapper
  shapes through the pure classifier; `test_the_download_signal_does_not_weaken_
  the_unrecognised_default` pins that the bias is untouched.
- The URL that produced this is in the log line above and was **not** re-fetched:
  it is a real customer's endpoint and we already know exactly what it does.

## If the next sweep shows zero further instances

This file's own instruction was to close it then, and that still holds for the
*population* argument — but not for the code, which stays either way. The class
is now countable: `RESULT FAILURE: url=… failure_class=unrenderable_content` in
Log Analytics, and the render cost per occurrence is `max_retries + 1`, not 1.

> **That log line had to be added, and finding out why was the best catch of the
> review.** A first draft of this section claimed the class was "measurable"
> because it is a `failure_class` value. It was not: **nothing logged a failed
> result's class at all.** These URLs were only ever visible because they
> produced a 500, and `server.py` logs 500s — the
> `Crawl request failed: … Download is starting` line is literally how the
> defect was found. So moving a class to 200 also moves it out of our logs, and
> `unrenderable_content` was about to be the first class we shipped with no
> server-side counter.
>
> Generalise it, because it will happen again: **every time this taxonomy moves
> a class off 5xx, it deletes that class's only log line.** `api.py` now emits
> `RESULT FAILURE` for every failed result, which closes the hole for the whole
> family — origin blocks and origin 4xx included, and those had been unlogged on
> the result path since the taxonomy shipped. `OVERNIGHT_PLAYBOOK.md`'s
> `ORIGIN FAILURE` row was describing a token that almost never fires.
