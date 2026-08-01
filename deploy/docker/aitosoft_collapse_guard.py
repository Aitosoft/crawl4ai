"""
Aitosoft: detect a capture whose body vanished between the browser and the
markdown — the silent whole-body loss.

Why this exists
---------------
Twice now a markup shape has made our parse discard an entire page while every
signal we report stayed green. The `<noscript>` case ran **3.5 months across 406
pages and 70 hosts** at HTTP 200 / ``success: true`` / one character of
markdown, and we only learned about it because MAS eventually noticed the
one-character pages in their own corpus. Chasing markup families one at a time
is a losing game — every WordPress plugin can mint another — so this module
detects the *consequence* instead of the causes.

What it measures, and why not the obvious thing
-----------------------------------------------
The obvious guard is ``len(cleaned_html) / len(html)``, and it is wrong twice
over. Both refutations are measurements, not arguments (2026-08-01):

1. **It fires on healthy pages.** ``len(html)`` is dominated by inline CSS and
   JS, which cleaning strips by design. The fixture origin's *healthy* control
   padded to 73 KB of inline ``<style>`` yields 261 bytes of ``cleaned_html`` —
   a ratio of 0.0036, identical to the collapsed page's. Real captures agree:
   `accountor.com`'s cookie-wall shell is 99,649 bytes of HTML and 230 bytes of
   ``cleaned_html`` (0.0023) and is not a defect at all.
2. **It is blind to a whole mechanism.** The `/collapse/unterminated-comment`
   shape comes back with 74,523 bytes of ``cleaned_html`` — *containing the
   contact details* — and still produces zero markdown, because the content sits
   inside an unterminated comment. Any ``cleaned_html``-sized guard passes it.

So the guard compares **visible text characters in the rendered HTML** against
**markdown characters out**. Text on both sides: the same unit, which is also
the unit MAS's own ``DEGENERATE_CAPTURE_CHARS = 500`` floor is written in. The
unit hazard that runs through this whole area — HTML *bytes* vs markdown
*characters* — is handled by never crossing it.

The healthy distribution the thresholds were measured against
-------------------------------------------------------------
37 distinct real captures stored under ``test-aitosoft/artifacts/`` (the four
Tier 1 hosts plus talgraf and monidor), whitespace-normalised on both sides:

    population                       n   visible chars   markdown/visible
    ------------------------------  --  --------------  -----------------
    healthy content pages           31       739–34,172       1.311–2.400
    cookie-wall / JS shells          5                0    (nothing to lose)
    challenge interstitial           1               58              1.000
    ------------------------------  --  --------------  -----------------
    collapsed (fixture, 4 shapes)    4        1,135–1,138        0.000

Markdown is normally *longer* than the visible text it came from — markdown
syntax adds characters. The lowest healthy ratio in the corpus is **1.311**;
every collapse is **0.000**. The thresholds below sit in a gap of two orders of
magnitude, which is why this guard can be shipped at all.

Note the two non-content populations, because they are what a careless guard
gets wrong. A cookie wall has **zero** visible text: nothing was lost, the page
genuinely had nothing on it, and that is the detector's business, not ours. The
``MIN_VISIBLE_TEXT_CHARS`` floor is what keeps those out.

Deliberately not detected
-------------------------
- **Partial loss.** A capture that keeps 2,000 markdown characters out of 40,000
  has lost most of a page, but no threshold separates that from a page with a
  lot of boilerplate. `MAX_MARKDOWN_CHARS` keeps us strictly inside the region
  MAS already calls degenerate, so a false positive cannot tell them a page they
  are happily using is broken.
- **Content swallowed into a `<script>`.** `/collapse/unclosed-script` puts the
  whole document inside a script element; ``_visible_text`` strips script blocks
  (it must — real pages carry hundreds of KB of inline JS, and counting it would
  wreck the ratio), so the guard sees zero visible text and stays quiet. That
  shape is the pre-parse repair's job, not the guard's. Recorded here rather
  than forgotten: `test_collapse_guard.py` pins it as a known blind spot.

The wire status
---------------
A detected collapse is served as **HTTP 200 with result-level
``success: false``** and ``failure_class: render_defect``. MAS's retry branch is
``retryableStatuses.includes(response.status)``, evaluated before the body is
parsed (their message 09) — so the 200 is what makes this cost zero retries, and
the class name is what we debug from. Ours, permanent, not worth retrying.
Content stays attached: a tag is advisory, ``success: false`` is structural.

See tasks/cleaned-html-collapse-guard.md.
"""

from __future__ import annotations

import re
from typing import Optional

# `_visible_text` is the detector's own body-text approximation: it takes the
# <body>, drops <script> and <style> blocks, strips tags. Reused rather than
# reimplemented so "what a human would see" has one definition in this codebase —
# the detector's challenge tier and this guard must agree about what counts as
# text on a page, or the two will disagree about the same capture.
#
# It is an Aitosoft addition to `antibot_detector.py` (commit c628b59), not
# upstream's, so this is our own seam and not a private-API coupling to a fork
# point. `test_collapse_guard.py` fails loudly if it moves.
from crawl4ai.antibot_detector import _visible_text

# ── thresholds (see the measured distribution in the module docstring) ────

#: How much visible text the browser must have handed us before an empty
#: markdown counts as a *loss* rather than an empty page. Below the smallest
#: healthy capture in the corpus (739 chars) and far above the challenge
#: interstitial (58). Pages under this are the detector's business.
MIN_VISIBLE_TEXT_CHARS = 500

#: How little markdown counts as "nothing came out". This is MAS's own
#: ``DEGENERATE_CAPTURE_CHARS``, deliberately: the guard can only fire on
#: captures they already treat as degenerate, so at worst it re-labels something
#: they were discarding anyway. It can never contradict their floor.
MAX_MARKDOWN_CHARS = 500

#: Markdown characters per visible-text character. Healthy pages measure
#: 1.311–2.400; observed collapses measure 0.000. At 0.10 the guard sits 13x
#: below the lowest healthy observation.
MAX_MARKDOWN_TO_VISIBLE_RATIO = 0.10

_WHITESPACE_RE = re.compile(r"\s+")


def _text_len(value: Optional[str]) -> int:
    """Length in **text characters**, whitespace-collapsed.

    Normalising is not cosmetic. `monidor.com`'s challenge interstitial measures
    506 raw characters of "visible text" and 58 once collapsed — the other 448
    are markup indentation. Counting raw would have put a challenge screen over
    the 500-character floor and made the guard fire on it.
    """
    if not value:
        return 0
    return len(_WHITESPACE_RE.sub(" ", value).strip())


def markdown_text_of(result: dict) -> str:
    """The raw markdown out of a result dict, whichever shape it is in.

    ``markdown`` is a dict for full mode (``raw_markdown`` / ``fit_markdown``)
    and a plain string in some static-mode paths.
    """
    markdown = result.get("markdown")
    if isinstance(markdown, dict):
        return markdown.get("raw_markdown") or ""
    return markdown or ""


def detect_collapse(html: Optional[str], markdown: Optional[str]) -> Optional[str]:
    """Return a human-readable reason if this capture lost its body, else None.

    ``html`` is what the browser handed us; ``markdown`` is what we produced
    from it. Both are compared as text characters — see the module docstring for
    why this is not a ``cleaned_html`` ratio.

    The markdown test comes first on purpose. It is the cheap one — markdown is
    an order of magnitude smaller than the HTML it came from — and it screens out
    every healthy page, so the visible-text pass (9 ms on the largest real
    capture we hold, 720 KB) only ever runs on captures that already look
    degenerate. This guard costs nothing on the path that matters.
    """
    produced = _text_len(markdown)
    if produced >= MAX_MARKDOWN_CHARS:
        return None

    visible = _text_len(_visible_text(html or ""))
    if visible < MIN_VISIBLE_TEXT_CHARS:
        # Nothing substantial was on the page to begin with. An empty capture of
        # an empty page is not a collapse — it is a block, a cookie wall or a
        # shell, and those are classified elsewhere.
        return None

    if produced > visible * MAX_MARKDOWN_TO_VISIBLE_RATIO:
        return None

    return (
        f"content collapsed in our parse: {visible} chars of visible text in the "
        f"rendered HTML, {produced} chars of markdown out "
        f"(ratio {produced / visible:.3f}, floor {MAX_MARKDOWN_TO_VISIBLE_RATIO})"
    )


def guard_result(result: dict) -> Optional[str]:
    """Apply the guard to one result dict, mutating it if the body was lost.

    Returns the reason when it fires, None otherwise. Successes only: a result
    that already failed has a truer failure class than this one, and a block
    page legitimately has no markdown.
    """
    if not result.get("success"):
        return None

    reason = detect_collapse(result.get("html"), markdown_text_of(result))
    if reason is None:
        return None

    # Content stays attached — `html` and whatever markdown there is are exactly
    # what MAS needs to diagnose this from their side, and they now store
    # `cleaned_html` for degenerate captures. `success: false` is the structural
    # part; the class is the documentation.
    result["success"] = False
    result["error_message"] = reason
    return reason
