"""
Nested <noscript> must not discard the page body — OFFLINE, no server, no network.

Regression for the fifth WAA root cause (2026-07-30): full mode returned HTTP
200, success:true and markdown of exactly one character for 406 pages across 70
hosts in MAS's corpus. `<noscript>` cannot nest; a WordPress lazy-load plugin
emitted a nested one around the GTM block, the outer element was therefore never
closed, and libxml2 swallowed everything after it.

Reference case https://www.kiertopakkaus.fi/ measured on prod rev 0000030:
312,628 B rendered HTML -> 97 B cleaned_html -> 1 B markdown. Excising that one
region alone recovered 47,310 B.

Fixtures only. Do NOT live-test kiertopakkaus.fi — it took 4 requests during the
investigation (tasks/noscript-collapses-body-to-empty-markdown.md).

    pytest test-aitosoft/test_noscript_body_collapse.py -q
"""

import pytest

from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy, strip_noscript

# The 6-line minimal reproduction from the task file, parameterised on the
# <noscript> region so every shape runs against identical surrounding content.
PAGE = """<html><head><title>T</title></head><body>
{ns}
<h1>Yhteystiedot</h1><p>Puhelin 010 123 4567, sahkoposti info@example.fi</p>
<div><p>Toinen kappale oikeaa sisaltoa.</p></div>
</body></html>"""

GTM = '<iframe src="about:blank"></iframe>'

# Shape emitted by the lazy-load plugin: an outer <noscript> whose closing tag
# is consumed by the inner element, so the outer one is never closed.
NESTED = f"<noscript>{GTM}<noscript>{GTM}</noscript>"
SINGLE = f"<noscript>{GTM}</noscript>"
UNCLOSED = f"<noscript>{GTM}"
UPPERCASE = f"<NOSCRIPT>{GTM}<NOSCRIPT>{GTM}</NOSCRIPT>"
WITH_ATTRS = f'<noscript data-lazyloaded="1">{GTM}<noscript>{GTM}</noscript>'


def cleaned(html: str) -> str:
    return (
        LXMLWebScrapingStrategy()
        .scrap("https://x/", html, word_count_threshold=1)
        .cleaned_html
    )


@pytest.mark.parametrize(
    "label,region",
    [
        ("nested", NESTED),
        ("single", SINGLE),
        ("unclosed", UNCLOSED),
        ("uppercase", UPPERCASE),
        ("with_attrs", WITH_ATTRS),
        ("absent", ""),
    ],
)
def test_body_survives_every_noscript_shape(label, region):
    """The defect: `nested` yielded 42 B — '<html><head><title>T</title></head></html>'
    — while every other shape yielded 187 B. All shapes must now keep the body."""
    out = cleaned(PAGE.format(ns=region))
    assert "Yhteystiedot" in out, f"{label}: heading lost"
    assert "info@example.fi" in out, f"{label}: contact lost"
    assert "Toinen kappale" in out, f"{label}: trailing content lost"


def test_nested_and_single_produce_the_same_body():
    """The nesting must stop being observable at all — that is the fix, as
    opposed to special-casing the nested shape."""
    assert cleaned(PAGE.format(ns=NESTED)) == cleaned(PAGE.format(ns=SINGLE))


def test_noscript_only_page_stays_empty():
    """Correct behaviour, not a regression: we render with JavaScript enabled,
    so <noscript> content is by definition not what the page showed. A page
    whose *only* content is inside <noscript> is genuinely empty."""
    out = cleaned(
        "<html><head><title>T</title></head><body>"
        "<noscript><p>Enable JavaScript</p></noscript></body></html>"
    )
    assert "Enable JavaScript" not in out


def test_strip_noscript_is_a_noop_without_noscript():
    """Fast path: pages without <noscript> — the overwhelming majority — must
    come back byte-identical and unparsed."""
    html = "<html><body><p>hello</p></body></html>"
    assert strip_noscript(html) is html
    assert strip_noscript("") == ""


def test_strip_noscript_removes_element_and_content():
    assert strip_noscript("<p>a</p><noscript><img src=x></noscript><p>b</p>") == (
        "<p>a</p><p>b</p>"
    )


def test_realistic_lazyload_gtm_block():
    """The actual markup family from the reference host: a lazy-load wrapper
    around the Google Tag Manager iframe, immediately followed by the skip-link
    that begins the real document."""
    html = (
        "<html><head><title>Etusivu - Kiertopakkaus</title></head><body>"
        '<noscript><iframe data-lazyloaded="1" src="about:blank" '
        'data-src="https://www.googletagmanager.com/ns.html?id=GTM-XXXX"></iframe>'
        '<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-XXXX">'
        "</iframe></noscript>"
        '<a class="skip-link" href="#content">Siirry sisaltoon</a>'
        '<div class="hfeed site" id="page"><h1>Kiertopakkaus Oy</h1>'
        "<p>Myymme ja vuokraamme pakkauksia. Puhelin 010 000 0000.</p></div>"
        "</body></html>"
    )
    out = cleaned(html)
    assert "Kiertopakkaus Oy" in out
    assert "Siirry sisaltoon" in out
    assert "010 000 0000" in out
