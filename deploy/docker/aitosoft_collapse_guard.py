"""
Aitosoft: detect a capture whose body vanished between the browser and the
markdown — the silent whole-body loss — and, where possible, get it back.

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

Recovery
--------
Detecting the loss does not return the data. Since 2026-08-02 a fire is
followed by a **second opinion**: the same rendered ``html``, re-converted with
``crawl4ai.html2text`` — the converter ``aitosoft_static_mode`` already ships
and already serves to MAS. Measured through the browser at 73 KB, twice, and
re-derived independently before this shipped:

    shape                  markdown today   html2text over the same html
    --------------------  ---------------  -----------------------------
    unclosed-noscript                   0    1,265  (byte-identical to the
                                                     healthy control's)
    deep-nesting                        0    1,239  (content complete; the
                                                     markdown table loses its
                                                     separator row)
    unterminated-comment                0        0
    unclosed-script                     0        0   (guard-blind anyway)
    healthy control                 1,258    1,265

So two of the three shapes the guard can see come back whole, and this costs
**no** new divergence from upstream's parser: recovery lives in this file, which
is 100 % ours.

Two things about that, because both are easy to get wrong:

- **Recovery must NOT reuse ``aitosoft_static_mode``'s pipeline, only its
  converter.** That module runs ``_strip_hidden_decoys()`` first, which
  ``decompose()``s every ``script``/``style``/``noscript``/``template``. On an
  unclosed ``<noscript>`` Chromium has re-serialized the whole document *inside*
  the element, so BeautifulSoup then deletes the page — measured, 1,265 -> 0.
  It reproduces ``strip_noscript()``'s failure by a different route. Calling
  ``HTML2Text`` directly is deliberate.

  It does **not** cost us the hidden-decoy protection, and an earlier draft of
  this note claimed it did. Measured: full mode's own path
  (``LXMLWebScrapingStrategy`` + ``DefaultMarkdownGenerator``) emits the
  ``oe_displaynone`` decoy address and a ``display:none`` honeypot too — only
  *static* mode strips them. Recovery is compared against the path it replaces,
  which is full mode's, so it introduces no new decoy channel. Stated plainly
  because as written it read like a regression someone would try to "fix".
- **A recovery must clear BOTH floors — the degenerate floor and the ratio —
  and neither is a new threshold.** The first draft accepted on
  ``MAX_MARKDOWN_CHARS`` alone, on the argument that recovery should treat its
  output exactly as the normal path would. A review refuted that with a
  measurement, and the refutation is the whole reason this file exists:

      visible text        41,408
      markdown from parse      0   -> guard fires, ratio 0.000
      recovered              599   -> 1.4 % of the body

  Under the degenerate floor alone that page goes out **green**, because 599
  clears MAS's 500 — so 40,809 characters vanish with no signal on either side.
  That is a *new* silent-loss channel opened by the fix for silent loss, and it
  breaks the guard's own safety invariant (see ``MAX_MARKDOWN_CHARS`` below:
  "the guard can only fire on captures they already discard").

  The symmetry argument was wrong because the two paths are not symmetric: on
  the normal path we have no evidence of loss and genuinely cannot separate a
  short page from a stripped one, while here **the guard has already proved the
  collapse**. Declining to use evidence we hold is not consistency.

  Cost of the second clause, measured: every genuine recovery observed sits at
  ratio 1.067–1.081 (fixture shapes) and 1.313–2.787 (42 stored real captures),
  i.e. 10–28x above the 0.10 floor. It rejects nothing that has ever been
  measured as a good recovery.

  Be precise about which clause does what, because the docstring blurred it
  once: any recovery that clears ``MAX_MARKDOWN_CHARS`` is already one the guard
  could not flag, so the *first* clause is what makes acceptance self-consistent
  and the *ratio* clause carries the entire weight of the 599-of-41,408 case.

  And know its limit. The ratio is recovered **markdown** characters over
  **visible text** characters, and markdown carries link URLs that are not
  visible text — a 200-link navigation over 1,289 visible characters recovers
  12,580. So on a link-heavy page a partial recovery can clear 0.10 on nav
  alone. The clause is a floor against catastrophic partials, not a completeness
  measure; nothing here can detect partial loss, which is the guard's documented
  blind spot and remains one.

The wire status
---------------
An unrecovered collapse is served as **HTTP 200 with result-level
``success: false``** and ``failure_class: render_defect``. MAS's retry branch is
``retryableStatuses.includes(response.status)``, evaluated before the body is
parsed (their message 09) — so the 200 is what makes this cost zero retries, and
the class name is what we debug from. Ours, permanent, not worth retrying.
Content stays attached: a tag is advisory, ``success: false`` is structural.

A **recovered** capture goes out as an ordinary success carrying the recovered
markdown. Option B — ``success: false`` with the recovery attached — buys
nothing, because MAS's client reads ``success`` and would discard the content we
just rescued. Both shapes are HTTP 200 either way, so no retry behaviour
changes; this is additive from their side. It also narrows ``render_defect`` to
its true meaning: *we lost the body and could not get it back.*

What a recovered result does NOT carry, stated so nobody reads more into it than
is there: ``cleaned_html`` is left as our parse produced it (it is the evidence),
``fit_markdown`` stays empty (no content filter ran), and ``links`` is whatever
the collapsed parse produced, i.e. usually nothing. That is the same shape
``aitosoft_static_mode`` already returns for every static capture MAS consumes,
so it is not a new thing for their client to handle.

See tasks/cleaned-html-collapse-guard.md.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
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

# Upstream's vendored html2text — the same converter `aitosoft_static_mode`
# serves to MAS today, so recovery introduces no second markdown dialect and no
# new dependency. Reused as the CONVERTER only, never as static mode's pipeline;
# see the module docstring for the measurement that makes that distinction
# load-bearing.
from crawl4ai.html2text import HTML2Text

logger = logging.getLogger(__name__)

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


def _collapse_reason(visible: int, produced: int) -> Optional[str]:
    """The verdict, from the two character counts alone.

    Split out from `detect_collapse` so the recovery path can reuse the visible
    count it already paid for instead of running `_visible_text` twice over the
    same 720 KB.
    """
    if produced >= MAX_MARKDOWN_CHARS:
        return None

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


def detect_collapse(html: Optional[str], markdown: Optional[str]) -> Optional[str]:
    """Return a human-readable reason if this capture lost its body, else None.

    ``html`` is what the browser handed us; ``markdown`` is what we produced
    from it. Both are compared as text characters — see the module docstring for
    why this is not a ``cleaned_html`` ratio.

    **The verdict only.** ``guard_result`` is the production path and does not
    call this — it needs the visible-text count for recovery, so it inlines the
    same two steps rather than paying for ``_visible_text`` twice on a 720 KB
    page. This is kept as the pure, side-effect-free form, which is what the
    threshold evidence in ``test_collapse_guard.py`` is asserted against.
    """
    produced = _text_len(markdown)
    if produced >= MAX_MARKDOWN_CHARS:
        return None
    return _collapse_reason(_text_len(_visible_text(html or "")), produced)


def recover_markdown(html: Optional[str], base_url: str = "") -> str:
    """A second opinion on the same rendered HTML, via html2text.

    Deliberately **not** ``aitosoft_static_mode._fetch_static_one``'s pipeline —
    only its converter. See the module docstring: that pipeline's
    ``_strip_hidden_decoys()`` deletes the whole page for the ``<noscript>``
    family, which is the family recovery exists for.

    Also deliberately not upstream's own seam, and the alternative is recorded
    because it is the better-looking one: ``DefaultMarkdownGenerator`` takes a
    documented ``content_source="raw_html"`` and
    ``generate_markdown(input_html=…)`` would produce **exactly the same
    recovery** (measured: 1,227 normalised characters either way on every
    fixture shape) while additionally filling ``markdown_with_citations`` and
    using full mode's own markdown dialect. It was not chosen because recovery
    runs on markup we already know is malformed, and the fewer lines of upstream
    machinery that touch it — link extraction, citation building, filter
    dispatch — the smaller the chance the fallback needs a fallback. Reconsider
    if a recovered page's formatting ever turns out to matter to MAS; the
    yield is identical, so nothing hangs on it.

    Never raises: html2text has parser edge cases and this runs on markup we
    already know is malformed. A failure here means "no recovery", which leaves
    the caller exactly where it was.
    """
    if not html:
        return ""
    try:
        converter = HTML2Text(baseurl=base_url)
        converter.body_width = 0  # no hard-wrap, same as static mode
        converter.ignore_images = True  # MAS does not use images
        return converter.handle(html)
    except Exception as exc:  # pragma: no cover — edge cases, not a code path
        logger.warning("[collapse-guard] html2text recovery failed: %s", exc)
        return ""


@dataclass(frozen=True)
class GuardVerdict:
    """What the guard found, and whether the body came back.

    Truthy, so a call site that only asks "did it fire" reads the same as it did
    before recovery existed. Deliberately without a ``__str__`` returning the
    reason: a verdict that formats as its reason invites `"%s" % verdict` in a
    log line, and then "recovered" and "lost" print identically, which is the one
    thing the two log tokens exist to keep apart.
    """

    reason: str
    recovered: bool
    recovered_chars: int


def guard_result(result: dict) -> Optional[GuardVerdict]:
    """Apply the guard to one result dict, mutating it if the body was lost.

    Returns the verdict when it fires, None otherwise. Successes only: a result
    that already failed has a truer failure class than this one, and a block
    page legitimately has no markdown.

    Two outcomes when it does fire:

    - **Recovered** — html2text got the body back and cleared MAS's degenerate
      floor. The result keeps ``success: true`` and carries the recovered
      markdown. This is the outcome that returns customer data.
    - **Not recovered** — ``success: false``, and the caller tags it
      ``render_defect``. Content stays attached: ``html`` and whatever markdown
      there is are exactly what MAS needs to diagnose it from their side, and
      they store ``cleaned_html`` for degenerate captures. ``success: false`` is
      the structural part; the class is the documentation.
    """
    if not result.get("success"):
        return None

    # The markdown test comes first on purpose, and `_collapse_reason` checking
    # it again is not redundancy — this early return is the whole optimisation.
    # Markdown is an order of magnitude smaller than the HTML it came from, and
    # this screens out every healthy page, so the visible-text pass (9 ms on the
    # largest real capture we hold, 720 KB) and the recovery behind it never run
    # on the path that matters.
    produced = _text_len(markdown_text_of(result))
    if produced >= MAX_MARKDOWN_CHARS:
        return None

    html = result.get("html")
    visible = _text_len(_visible_text(html or ""))
    reason = _collapse_reason(visible, produced)
    if reason is None:
        return None

    recovered = recover_markdown(html, result.get("url") or "")
    recovered_chars = _text_len(recovered)
    if _is_a_real_recovery(visible, recovered_chars):
        _attach_markdown(result, recovered)
        return GuardVerdict(reason, True, recovered_chars)

    # A partial recovery is NOT attached. The markdown on a failed result is
    # evidence — it is what our parse produced — and overwriting it with
    # something we have just declined to call a success would destroy that
    # without helping MAS, whose client reads `success` and stops there. The
    # character count goes in the log line instead, where it is the diagnostic.
    result["success"] = False
    result["error_message"] = reason
    return GuardVerdict(reason, False, recovered_chars)


def _is_a_real_recovery(visible: int, recovered: int) -> bool:
    """Both floors, and the ratio one is the load-bearing half.

    ``MAX_MARKDOWN_CHARS`` alone would let a 599-character rescue of a 41,408-
    character page out as a success — above MAS's degenerate floor, so they use
    it, so 40,809 characters are lost silently. See the module docstring: the
    guard has already proved this page collapsed, which is exactly the evidence
    the normal path does not have, and it is why recovery is held to the
    stricter bar.
    """
    return (
        recovered >= MAX_MARKDOWN_CHARS
        and recovered > visible * MAX_MARKDOWN_TO_VISIBLE_RATIO
    )


#: Markdown variants the normal pipeline fills that a recovery cannot. Blanked
#: rather than left alone, and that distinction is the point: an *empty*
#: ``markdown_with_citations`` says "we did not produce one", while the collapsed
#: parse's leftover — one character, sitting next to 1,266 characters of
#: recovered ``raw_markdown`` — is a contradiction inside a single object, with
#: every signal green. That is precisely the failure shape this module exists to
#: prevent, so it must not be reintroduced one field to the left. Caught in
#: review, 2026-08-02.
_STALE_ON_RECOVERY = ("markdown_with_citations", "references_markdown", "fit_markdown")


def _attach_markdown(result: dict, markdown: str) -> None:
    """Put the recovered markdown where MAS reads it, and blank what it invalidates.

    MAS reads ``raw_markdown``; static mode has always served them
    ``{"raw_markdown": …, "fit_markdown": ""}``, so this is a shape their client
    already consumes. The other variants are cleared rather than filled: no
    content filter ran, and no citation pass ran, so claiming either would be a
    lie. ``cleaned_html`` and ``links`` are deliberately *not* touched — those are
    what our parse produced, i.e. the evidence, and they do not contradict the
    recovery, they explain it.

    Whatever shape the result already used is the shape the recovery lands in.
    A result with **no** ``markdown`` key is a real possibility —
    ``CrawlResult.model_dump`` emits it only when ``_markdown`` is set — and it
    gets the dict, because a client reading ``markdown.raw_markdown`` would break
    on a bare string and that is the expensive direction.
    """
    existing = result.get("markdown")
    if isinstance(existing, str):
        result["markdown"] = markdown
        return

    if not isinstance(existing, dict):
        result["markdown"] = {"raw_markdown": markdown, "fit_markdown": ""}
        return

    existing["raw_markdown"] = markdown
    for key in _STALE_ON_RECOVERY:
        if key in existing:
            existing[key] = ""
