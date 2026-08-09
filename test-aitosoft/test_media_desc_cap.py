"""
A media `desc` must not be the whole page — OFFLINE, no server, no network.

Regression for the 2026-08-08 incident: https://www.thermokon.fi returned ~232 MB
four times, at HTTP 200 `success: true`, with no log line anywhere saying
anything was wrong. MAS's client gave up at 216 s on each attempt, so the company
was unrecoverable.

Cause is upstream's `find_closest_parent_with_useful_text`, which walks *up* from
an `<img>` until an ancestor has enough words and then returns that ancestor's
entire subtree text. An image container holds no words of its own, so on a grid
layout the walk passes every one of them and stops at whichever container also
holds the page prose. `add_variant` then copies that string into every
srcset/`<picture>` variant: 1,104 of 1,160 media entries carried the same
154,798-character string.

What these tests pin, in order of what would hurt most if it regressed:

1. the value is bounded, so the payload is O(entries x cap) instead of
   O(entries x page_text);
2. the cap touches *only* `desc` — `cleaned_html` and `links` come back
   byte-identical, which is the whole safety argument, since markdown is
   generated from `cleaned_html` and MAS never reads `media` at all;
3. an ordinary short description is returned exactly as before, with no marker.

The uncapped arm is produced by raising `MEDIA_DESCRIPTION_MAX_CHARS`, so both
arms run the real production code path and differ only in the constant.

    pytest test-aitosoft/test_media_desc_cap.py -q
"""

import json

import pytest

import crawl4ai.content_scraping_strategy as csx
from crawl4ai.content_scraping_strategy import (
    MEDIA_DESCRIPTION_MAX_CHARS,
    LXMLWebScrapingStrategy,
)

# ~5,000 characters, i.e. an ordinary page body — thermokon's was 154,798.
PROSE = (
    "Yhteystiedot: Aitosoft Oy, Helsinki. Puhelin 010 123 4567, "
    "sahkoposti info@example.fi. "
) * 60

CARD = """    <div class="product">
      <a href="/p{i}">
        <img src="/img/p{i}.jpg" srcset="/img/p{i}-400.jpg 400w, /img/p{i}-800.jpg 800w"
             width="300" height="300" alt="Tuote {i}">
      </a>
    </div>"""


def catalogue(n_images: int = 40, wrapper: str = '<div id="page">') -> str:
    """A product grid: image containers with zero words, prose in a common
    ancestor. `wrapper` exists because the obvious alternative fix — "skip the
    desc when the ancestor is <body>/<html>" — is defeated by exactly one
    wrapper div, the commonest idiom in every theme framework, while the cap
    holds either way.

    Indentation is load-bearing: the walk's stop condition needs a *truthy*
    direct `.text`, which on pretty-printed markup is the newline before the
    first child. Minified markup yields `desc: None` for the same document.
    """
    cards = "\n".join(CARD.format(i=i) for i in range(n_images))
    close = "</div>" if wrapper else ""
    return (
        f'<html>\n<body>\n  {wrapper}\n    <div class="products">\n'
        f"{cards}\n    </div>\n    <p>{PROSE}</p>\n  {close}\n</body>\n</html>"
    )


def scrape(html: str):
    return LXMLWebScrapingStrategy().scrap("https://example.fi/", html)


def media_bytes(result) -> int:
    return len(json.dumps(result.media.model_dump()))


@pytest.mark.parametrize("wrapper", ['<div id="page">', ""])
def test_every_desc_is_bounded_on_a_catalogue_page(wrapper):
    """The defect shape: one prose block reaching every image in the grid."""
    result = scrape(catalogue(wrapper=wrapper))
    images = result.media.model_dump()["images"]
    assert images, "the fixture must produce media entries or it pins nothing"
    for entry in images:
        assert len(entry["desc"]) <= MEDIA_DESCRIPTION_MAX_CHARS + 3, (
            f"desc is {len(entry['desc'])} chars: the walk still returns a whole "
            f"ancestor subtree"
        )


def test_the_variant_fanout_cannot_re_multiply_the_string():
    """`add_variant` copies `desc` into every srcset entry, so the payload is
    entries x len(desc). The cap is what makes that product bounded.

    The bound is deliberately an absolute number rather than a multiple of
    `MEDIA_DESCRIPTION_MAX_CHARS`: a test whose threshold moves with the value
    it is testing cannot fail when the truncation is lost. 40 images fan out to
    120 entries against a 5,000-character body, so the uncapped payload is
    ~600 KB and the capped one ~30 KB.
    """
    result = scrape(catalogue())
    images = result.media.model_dump()["images"]
    assert len(images) > 40, "fixture must fan out, or it does not test the amplifier"
    assert media_bytes(result) < 64_000, media_bytes(result)


def test_the_cap_changes_only_desc(monkeypatch):
    """The safety argument, measured rather than asserted: everything MAS reads
    is byte-identical between the two arms."""
    html = catalogue()
    after = scrape(html)  # production behaviour
    monkeypatch.setattr(csx, "MEDIA_DESCRIPTION_MAX_CHARS", 10**9)
    before = scrape(html)  # the pre-fix behaviour, same code path

    assert media_bytes(before) > media_bytes(after) * 2, (
        "the uncapped arm must be substantially larger, or this fixture no "
        "longer reproduces the defect"
    )
    assert after.cleaned_html == before.cleaned_html
    assert after.links.model_dump() == before.links.model_dump()

    b, a = before.media.model_dump()["images"], after.media.model_dump()["images"]
    assert len(a) == len(b), "the cap must not drop images"
    for x, y in zip(b, a):
        assert {k: v for k, v in x.items() if k != "desc"} == {
            k: v for k, v in y.items() if k != "desc"
        }
        assert y["desc"] == x["desc"][:MEDIA_DESCRIPTION_MAX_CHARS] + "..."


def test_an_ordinary_description_is_returned_verbatim():
    """Most pages are unaffected: no truncation, no marker, exact text."""
    html = (
        "<html>\n<body>\n  <figure>\n    <img src='/photo.jpg' width='600' "
        "height='400' alt='Toimitalo'>\n"
        "    <figcaption>Paakonttori Helsingissa.</figcaption>\n  </figure>\n"
        "</body>\n</html>"
    )
    images = scrape(html).media.model_dump()["images"]
    assert images, "fixture produced no image"
    assert images[0]["desc"] == "Paakonttori Helsingissa."


def test_truncation_is_marked():
    """A truncated snippet must be *visibly* truncated — a consumer, or a future
    session reading a stored capture, has to be able to tell a cut description
    from a short one. The page is Finnish because production is: the cap counts
    codepoints, so 200 chars is ~211 UTF-8 bytes here. Never size a byte budget
    from this constant."""
    html = (
        "<html>\n<body>\n  <div>\n    <img src='/kuva.jpg' width='600' "
        "height='400' alt='Kuva'>\n"
        f"    <p>{'Ääkkösiä ja pitkää tekstiä. ' * 40}</p>\n  </div>\n</body>\n</html>"
    )
    desc = scrape(html).media.model_dump()["images"][0]["desc"]
    assert desc.endswith("...")
    assert len(desc) == MEDIA_DESCRIPTION_MAX_CHARS + 3
