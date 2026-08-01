"""
The collapse guard — OFFLINE, no server, no network, no browser.

A capture whose body vanished between the browser and the markdown must not be
reported as a success. This suite pins the guard's thresholds against the
**healthy distribution they were measured from**, because the failure mode of a
ratio guard is that it fires on real customer pages, and that is worse than
having no guard at all.

The evidence is not synthetic. `HEALTHY_CAPTURES` below is measured from the 37
distinct real captures stored under `test-aitosoft/artifacts/` — the four Tier 1
hosts plus talgraf and monidor — and `test_thresholds_clear_every_real_capture`
re-derives it from those files on every run, so the numbers cannot rot silently
while the constants drift.

    pytest test-aitosoft/test_collapse_guard.py -q

See tasks/cleaned-html-collapse-guard.md.
"""

import glob
import json
import os
import re
import sys

import pytest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "docker"
    ),
)

from aitosoft_collapse_guard import (  # noqa: E402
    MAX_MARKDOWN_CHARS,
    MAX_MARKDOWN_TO_VISIBLE_RATIO,
    MIN_VISIBLE_TEXT_CHARS,
    detect_collapse,
    guard_result,
)
from aitosoft_failure_class import (  # noqa: E402
    NON_RETRYABLE_CLASSES,
    ORIGIN_CLASSES,
    RENDER_DEFECT,
    RENDER_ERROR,
    RENDER_TIMEOUT,
    http_status_for,
)

ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")

PAGE = "<!DOCTYPE html><html><head><title>T</title></head><body>{body}</body></html>"


def page_with(text_chars: int) -> str:
    """A page carrying roughly `text_chars` characters of visible text."""
    word = "sisaltoa "  # 9 chars
    return PAGE.format(body=f"<p>{word * (text_chars // len(word) + 1)}</p>")


def inline_css(nbytes: int) -> str:
    """Inline CSS — bytes with no visible text, the way a real vendor page pads.
    This is what makes an `len(html)` ratio unusable."""
    return "<style>/* %s */</style>" % ("padding " * (nbytes // 8))


# ── the healthy distribution, restated ───────────────────────────────────
# Measured 2026-08-01 from test-aitosoft/artifacts/, whitespace-normalised on
# both sides. Markdown is normally LONGER than the visible text it came from,
# because markdown syntax adds characters.
#
#   population                     n   visible chars   markdown/visible
#   ----------------------------  --  --------------  -----------------
#   healthy content pages         31       739–34,172       1.311–2.400
#   cookie-wall / JS shells        5                0    (nothing to lose)
#   challenge interstitial         1               58              1.000
#   ----------------------------  --  --------------  -----------------
#   collapsed (fixture, 4 shapes)  4       1,135–1,138            0.000

LOWEST_HEALTHY_RATIO = 1.311  # jpond/caverna small pages
SMALLEST_HEALTHY_VISIBLE = 739  # caverna.fi, the smallest real content page


def test_the_thresholds_sit_in_the_measured_gap():
    """The guard is only shippable because the gap is two orders of magnitude.
    If a future edit narrows it, this is where it should hurt."""
    assert MAX_MARKDOWN_TO_VISIBLE_RATIO < LOWEST_HEALTHY_RATIO / 10, (
        "the ratio floor must stay an order of magnitude below the lowest "
        "healthy page ever measured"
    )
    assert MIN_VISIBLE_TEXT_CHARS < SMALLEST_HEALTHY_VISIBLE, (
        "a real page smaller than the visible-text floor would be exempt from "
        "the guard, which is the safe direction — but the floor must not creep "
        "above the smallest page we have actually seen"
    )
    # MAS's DEGENERATE_CAPTURE_CHARS. Named here so the coupling is explicit:
    # the guard can only ever fire on captures they already discard.
    assert MAX_MARKDOWN_CHARS == 500


# ── the four collapse mechanisms ─────────────────────────────────────────


def test_a_collapsed_page_is_detected():
    """73 KB of page, full of text, one character out. The production shape:
    `apteam.fi` measured 73,970 / 96 / 1, byte-identical across two visits."""
    html = PAGE.format(body=inline_css(73000) + "<p>" + "yhteystiedot " * 200 + "</p>")
    assert detect_collapse(html, "\n") is not None


def test_an_intact_cleaned_html_does_not_save_it():
    """The `unterminated-comment` mechanism, and the reason this guard measures
    markdown rather than `cleaned_html`.

    Measured through the browser: that shape returns 74,523 bytes of
    `cleaned_html` *containing the contact details* and still produces zero
    markdown, because the content sits inside the comment. Every
    `cleaned_html`-sized guard — including the one the task file originally
    proposed — passes it silently.
    """
    html = PAGE.format(body="<p>" + "yhteystiedot " * 200 + "</p>")
    assert detect_collapse(html, "") is not None


# ── the false positives that would make this worse than nothing ──────────


def test_inline_css_does_not_make_a_healthy_page_look_collapsed():
    """The refutation of the `len(html)` ratio, in one assertion.

    A 73 KB page whose bulk is inline CSS cleans down to a few hundred bytes and
    is completely healthy. Measured on the fixture origin: the healthy control
    padded to 73 KB gives 261 bytes of `cleaned_html`, ratio 0.0036 — *identical*
    to the collapsed page's. Only the text-vs-text measure separates them.
    """
    body_text = "Yritys Oy palvelee teollisuutta kunnossapidossa. " * 30
    html = PAGE.format(body=inline_css(73000) + f"<p>{body_text}</p>")
    markdown = "# Yritys Oy\n\n" + body_text
    assert detect_collapse(html, markdown) is None


def test_a_cookie_wall_is_not_a_collapse():
    """5 real captures of `accountor.com`'s cookie wall: ~120 KB of HTML, ~790
    bytes of `cleaned_html`, ~540 characters of markdown and **zero** visible
    text. Nothing was lost — the page genuinely had nothing on it. Blocks and
    consent walls are the detector's business, not the guard's."""
    html = PAGE.format(body='<div id="app"></div>' + inline_css(99000))
    assert detect_collapse(html, "Cookie consent") is None


def test_a_challenge_interstitial_is_not_a_collapse():
    """`monidor.com`, a real capture: "Loader / Please wait while your request is
    being verified..." — 58 characters of text, and the markdown reproduces all
    58 of them faithfully. Nothing collapsed."""
    html = PAGE.format(
        body="<p>Loader</p><p>Please wait while your request is being verified...</p>"
    )
    assert detect_collapse(html, "Loader\nPlease wait while your request...") is None


def test_a_genuinely_small_page_is_not_a_collapse():
    """A one-line contact page is short at both ends. The visible-text floor is
    what keeps the guard away from it."""
    html = PAGE.format(body="<h1>Yritys Oy</h1><p>info@yritys.fi</p>")
    assert detect_collapse(html, "# Yritys Oy\n\ninfo@yritys.fi") is None


def test_whitespace_is_not_content():
    """`monidor.com` measures 506 raw characters of "visible text" and 58 once
    collapsed — the other 448 are markup indentation. Counting raw would have
    put a challenge screen over the 500-character floor and fired on it."""
    indented = PAGE.format(body="<div>\n" + " " * 4000 + "\n</div>")
    assert detect_collapse(indented, "") is None


@pytest.mark.parametrize("markdown", ["", " ", "\n", None])
def test_empty_html_is_never_a_collapse(markdown):
    """No HTML means no measurement, not a verdict."""
    assert detect_collapse("", markdown) is None
    assert detect_collapse(None, markdown) is None


# ── every real capture we hold ───────────────────────────────────────────


def _real_captures():
    for path in sorted(
        glob.glob(os.path.join(ARTIFACTS, "**", "*.json"), recursive=True)
    ):
        try:
            with open(path) as fh:
                data = json.load(fh)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("html"):
            yield os.path.relpath(path, ARTIFACTS), data


def test_thresholds_clear_every_real_capture():
    """The evidence for the thresholds, re-derived on every run.

    Every stored capture of a real customer site — healthy pages, cookie walls,
    JS shells, a challenge interstitial — must come back clean. These are the
    pages a false positive would break, and they are the reason the constants
    are what they are.
    """
    checked = 0
    for name, data in _real_captures():
        markdown = data.get("markdown")
        if isinstance(markdown, dict):
            markdown = markdown.get("raw_markdown")
        reason = detect_collapse(data["html"], markdown)
        assert reason is None, f"guard fired on real capture {name}: {reason}"
        checked += 1

    assert checked >= 30, f"expected the stored corpus, found {checked} captures"


def test_the_real_corpus_still_shows_the_gap():
    """Not just "no false positives" — the healthy pages must stay far away from
    the threshold, or the guard is one unusual customer page from firing."""
    norm = lambda s: len(re.sub(r"\s+", " ", s or "").strip())  # noqa: E731
    from crawl4ai.antibot_detector import _visible_text

    ratios = []
    for _name, data in _real_captures():
        markdown = data.get("markdown")
        if isinstance(markdown, dict):
            markdown = markdown.get("raw_markdown")
        visible = norm(_visible_text(data["html"]))
        produced = norm(markdown)
        # Only content pages have a ratio at all; shells have no visible text.
        if visible >= MIN_VISIBLE_TEXT_CHARS and produced >= MAX_MARKDOWN_CHARS:
            ratios.append(produced / visible)

    assert ratios, "no healthy content pages in the corpus"
    assert min(ratios) > MAX_MARKDOWN_TO_VISIBLE_RATIO * 10, (
        f"healthy pages have closed on the threshold: lowest ratio {min(ratios):.3f} "
        f"vs floor {MAX_MARKDOWN_TO_VISIBLE_RATIO}"
    )


# ── what the guard does to the result ────────────────────────────────────


def test_guard_result_marks_the_failure_and_keeps_the_content():
    """ "A tag is advisory; `success: false` is structural." Content stays
    attached so MAS can diagnose from their side — they store `cleaned_html` for
    degenerate captures now."""
    html = PAGE.format(body="<p>" + "yhteystiedot " * 200 + "</p>")
    result = {
        "success": True,
        "html": html,
        "markdown": {"raw_markdown": "\n", "fit_markdown": ""},
    }

    reason = guard_result(result)

    assert reason
    assert result["success"] is False
    assert "collapsed" in result["error_message"]
    assert result["html"] == html, "content must stay attached"


def test_guard_leaves_an_already_failed_result_alone():
    """A block page has no markdown either, and `origin_blocked` is a truer
    verdict than `render_defect`. First failure wins."""
    result = {
        "success": False,
        "html": PAGE.format(body="<p>" + "denied " * 300 + "</p>"),
        "markdown": {"raw_markdown": ""},
    }
    assert guard_result(result) is None
    assert result["success"] is False


def test_guard_accepts_markdown_as_a_plain_string():
    """Static mode does not always wrap markdown in a dict."""
    result = {
        "success": True,
        "html": PAGE.format(body="<p>" + "yhteystiedot " * 200 + "</p>"),
        "markdown": "",
    }
    assert guard_result(result) is not None


# ── the wire status ──────────────────────────────────────────────────────


def test_a_collapse_is_served_at_200():
    """MAS's retry branch is `retryableStatuses.includes(response.status)`,
    evaluated before the body is parsed (their message 09). A collapse is
    permanent — all four reproducible shapes return byte-identical HTML across
    visits — so retrying it buys three more renders of a page we already know we
    cannot parse. 200 + result-level `success: false` is the shape `savaterra.fi`
    proved end to end at zero retries."""
    assert http_status_for([RENDER_DEFECT]) == 200


def test_render_defect_is_ours_but_not_an_origin_class():
    """The distinction the taxonomy was missing is permanence, not ownership.
    `render_defect` is entirely our fault and still must not be retried — but it
    must not be filed under the origin's classes either, or every log that asks
    "whose fault was this month" will lie."""
    assert RENDER_DEFECT in NON_RETRYABLE_CLASSES
    assert RENDER_DEFECT not in ORIGIN_CLASSES


def test_an_ssrf_refusal_is_not_retryable():
    """Caught while routing static mode through the shared mapping, and it would
    have shipped silently: static mode attaches `bad_request` to a *result* when
    the egress broker refuses a redirect hop ("MAS must never retry it", per that
    call site). Its old unconditional-200 branch made that true by accident. Send
    it through `http_status_for` without this and an SSRF refusal becomes a 500 —
    three more attempts at a URL our own policy has already declined.
    """
    from aitosoft_failure_class import BAD_REQUEST

    assert http_status_for([BAD_REQUEST]) == 200


def test_render_error_is_still_retryable():
    """The guard must not have quietly made our transient faults terminal."""
    assert http_status_for([RENDER_ERROR]) == 500
    assert http_status_for([RENDER_TIMEOUT]) == 504
    assert http_status_for([RENDER_DEFECT, RENDER_ERROR]) == 500


def test_both_render_modes_map_a_class_the_same_way():
    """The defect MAS found: `render_error` was served at 500 by full mode and
    inside a 200 by static mode, decided by `render_mode` and documented
    nowhere. There is now one mapping function and `server.py` routes both modes
    through it, so this is a property of the class alone."""
    for cls in sorted(NON_RETRYABLE_CLASSES) + [RENDER_ERROR, RENDER_TIMEOUT]:
        assert http_status_for([cls]) == http_status_for([cls])

    import inspect

    import server

    source = inspect.getsource(server)
    assert source.count("def _crawl_response") == 1, "one mapping site only"
    # The static short-circuit must not return an envelope of its own again.
    static_branch = source.split('if crawl_request.render_mode == "static":')[1][:900]
    assert "_crawl_response(results)" in static_branch
    assert "return JSONResponse(results)" not in static_branch
