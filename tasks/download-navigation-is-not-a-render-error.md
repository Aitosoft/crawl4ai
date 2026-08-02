# A URL that downloads instead of rendering costs four renders and returns 500

**Status:** Open, not started. Opened 2026-08-02 from production logs.
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

Worth checking while you are in there, because it is the same mechanism and the
answer is not obvious from the code: **does a PDF link behave the same way?**
Chromium may render a PDF inline rather than downloading it, depending on
config. If it downloads, this class is larger than one vCard endpoint. A
`/download/{kind}` route in `fixture_origin.py` answers it offline, and there is
no reason to touch a customer's site to find out.

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

## Verification

- A `fixture_origin` route serving `Content-Disposition: attachment` (and one
  serving `application/pdf` inline, for the question above), driven through
  `production_path.crawl`, asserting the wire status is **200** and the class is
  whatever was chosen — plus a test that pins it as *non-retryable*, the way
  `test_an_ssrf_refusal_is_not_retryable` pins `bad_request`.
- Offline suite green. Tier 1 4/4 if it ships in an image.
- Zero live requests. The URL that produced this is in the log line above and
  must not be re-fetched: it is a real customer's endpoint and we already know
  exactly what it does.
