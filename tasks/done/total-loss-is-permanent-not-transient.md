# A capture with no document root is permanent, and we report it as retryable

**Status:** IMPLEMENTED 2026-08-06 in the same image as
`tasks/done/consent-scripts-delete-the-page.md`, which is the actual fix.
Committed 2026-08-06, **deployed 2026-08-06 as `0.9.2-consent-guard`**.
**Size:** planned S, delivered S. One branch in `classify_result`, one helper,
eight tests. **No contract-test row needed changing** — see below.

---

## What shipped, and the three questions this file asked

**"How to detect it is genuinely open."** Answered: the **capture shape**, not
the reason string. `_document_root_is_gone()` tests for the absence of a
`<body>` element in a non-empty capture, and that single test covers both
production signatures — the 15-byte bare doctype (`<html>` removed) and the
head-only capture (`<body>` removed), which the detector reports under two
*different* reason strings (`Near-empty content` vs `Structural: no <body> tag`)
purely because one is gated on HTTP 200. Keying on the reason would have needed
both strings **and** a byte-count parse to separate a 15-byte deleted root from
a 39-byte empty shell. The shape needs neither.

It sits in `classify_result` rather than `classify_error_text`, because the
latter never receives `html` — and **below** both origin branches, so a root
that vanished on a page the origin refused is still the origin's verdict to
give. Inverting that order would start reporting 403s as our own defect.

**"Does anything pin the current 500?"** No. `test_mas_contract.py` pins
`http_status_for(["render_error"]) == 500`, which is untouched, and nothing
anywhere asserted that a rootless capture *is* `render_error`. So this was a bug
fix and not a contract change on the test surface — which is the opposite of
what this file predicted, and the prediction was the right one to make.

One row did change, and it is the interesting one: `MAS_DEFECT_B_CASES`'
`norex.com` entry carried **no `html` field at all**, so it would have kept
passing while describing production wrongly. It now carries the real 15-byte
capture and expects `render_defect`. Its old label — "our own
`Crawl4AI Error:` placeholder in 15 bytes of HTML" — is the exact sentence the
`tasks/README.md` corrections list flags as having sent four sessions to the
anti-bot tier instead of to our own DOM cleanup.

**"Is `render_defect` the right name?"** Yes, and it got a sentence rather than
a silent widening. The docstring moved from "our parse lost the body" to "the
body is gone and we are the reason" — keyed on the **shape of the damage**,
which is what makes it survive the next mechanism. That is this file's own
argument for building it, so the name should carry it.

**Verified red before green:** with `aitosoft_failure_class.py` reverted, 4 of
the 8 new tests fail.

**Size:** S. One classification seam, one wire status, one contract-test row.

**Pre-agreed with MAS**, who asked for it (`tmp/mas-repo-messages/19-…` §1) and
then accepted our argument that it must not *replace* the JS fix
(`21-…` §1: *"The JS is the fix; the class is the net; only one of them returns
data."*). So the relay is already done and this does not need announcing before
it ships — but it **is** a wire-status change, so it gets the usual care.

---

## What is wrong today

A capture whose document root is gone comes back as `render_error` at **HTTP
500**, which MAS's client retries three times. That is four attempts, and under
our patchright tier each attempt is four navigations — so **16 navigations for
one URL that will do exactly the same thing every time.** Kübler paid this twice
over (two URL spellings), which is where segment 1's 32 navigations and 266 s
came from.

`render_error` means *transient, ours, try again*. Nothing about a missing
`documentElement` is transient. The taxonomy already has the right bucket:
`render_defect` — ours, **permanent**, HTTP 200, result-level `success: false`,
and already in `NON_RETRYABLE_CLASSES`. The axis the taxonomy learned on
2026-08-01 was **permanence, not ownership** (`aitosoft_failure_class.py`
docstring), and this is squarely on the permanent side.

---

## Why it is worth doing even though the JS fix removes the cause

After `consent-scripts-delete-the-page.md` ships, this class should approach
zero occurrences. So its expected value *now* is low, and I want that stated
honestly rather than dressed up.

The reason to do it anyway is the one MAS gave, and it is a good one: it
generalises to **whatever deletes a document next year for a reason neither
repo has thought of**. Our own history says that is not hypothetical — this is
the third distinct mechanism that has produced a body-shaped hole (the
`<noscript>` family, the four markup shapes in
`cleaned-html-collapse-guard.md`, and now our own JS). A class that keys on the
*shape of the damage* rather than on the cause survives all of them.

---

## The seam, and the one thing not to break

`antibot_detector`'s inference-tier reason strings are already load-bearing:
`aitosoft_failure_class.classify_error_text` reads their `Structural:` /
`Near-empty content` prefixes to decide these are ours and not the origin's, and
`test_failure_classification.py` walks every reason `is_blocked` can produce and
fails if one lands on neither side of the line. Adding a signal here follows
that established pattern rather than inventing a new one.

**The distinction that must survive.** Not everything the near-empty tier
catches is permanent:

| shape | verdict | why |
|---|---|---|
| document root gone (15 B, or no `<html>`/`<body>` in non-XML) | **permanent** → `render_defect`, 200 | no retry can rebuild a deleted root |
| near-empty but structurally intact (a JS shell that rendered nothing) | stays `render_error`, 500 | genuinely might work on another attempt |

Collapsing those two would re-open the `norex.com` inversion from the other
side. Note the irony worth carrying: **`norex.com` was this same bug** — it is
one of only two hosts in the 30-day `Near-empty content (15 bytes)` population.
The class we created to stop mislabelling it was treating a symptom of a defect
we had not found yet.

**How to detect it is genuinely open.** Keying on the reason string is what the
codebase already does and is the cheap path; keying on the capture shape (no
`<html>` element in something that is not XML/JSON) is more robust and less
coupled. I have not decided, and I do not think I should — you will be looking
at the actual call sites. Whichever you choose, `test_failure_classification.py`
is where the choice gets pinned.

---

## Things to check that I did not

- **Does anything pin the current 500?** `test_mas_contract.py` and
  `test_failure_classification.py` both encode wire-status expectations. A row
  may need changing, and a row that *needs* changing is the signal that this is
  a contract change rather than a bug fix.
- **Is `render_defect` the right name if the site's own script did the
  deleting?** The class docstring says "our parse lost the body". Ownership
  lives in the name and no longer decides the status, so the status is right
  either way — but the name may deserve a sentence in the module rather than a
  silent widening.
- **`http_status_for` already maps `render_defect` → 200** via
  `NON_RETRYABLE_CLASSES`, so the status side may need no change at all. Confirm
  before assuming there is work there.

---

## What success looks like

One log line per occurrence with the class in it (`RESULT FAILURE` already
covers failed results — `api.py:1033`), 200 on the wire, `success: false`, and
MAS's client treating it as terminal on the first attempt. If segment 2 shows
this class firing at all after the JS fix, that is interesting in its own right:
it means a mechanism we have not identified is still deleting documents.
