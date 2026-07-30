"""
Challenge-family block detection — OFFLINE, no server, no network.

MAS scanned all 117,323 stored pages with our pattern list on 2026-07-30. It
returned 22 hits of which only **2** were genuine block pages; ~15 were Shopify
storefronts condemned by their own `/pages/access-denied` navigation link. The
signature that actually dominates was not in our list at all:

    robot-suspicion.svg + "Checking the site connection security"   371 pages
    "Checking your browser…"                                         29 pages
    our entire Varnish/Fastly/Incapsula/Access-Denied family          2 pages
    -------------------------------------------------------------------------
    challenge pages stored as successful content                    402 pages
                                     across 155 companies, 243 distinct hosts

Fixtures are synthesised from the signatures MAS measured, NOT from their stored
bodies (we asked for one full sample to identify the vendor; it had not arrived
when this was written). We could not reproduce the challenge live either —
magicad.com, classified challenge_all, served clean content to our Azure egress
on 2026-07-30 — so live verification is impossible by construction and would
burn requests against hosts already classified as blocked. See
tasks/antibot-detector-challenge-blindspot.md.

    pytest test-aitosoft/test_antibot_challenge_detection.py -q
"""

import pytest

from crawl4ai.antibot_detector import is_blocked

# ── fixtures ─────────────────────────────────────────────────────────────

# The dominant signature. Served with HTTP 200 — which is the whole point: the
# tier-2 list was only ever consulted on 4xx/5xx, so interstitial wording had
# never once been checked for the pages it was written for.
CHALLENGE_ROBOT_SUSPICION = """<!DOCTYPE html><html><head>
<title>Just a moment...</title></head><body>
<div class="wrapper">
<img src="https://d1rozh26tys225.cloudfront.net/assets/robot-suspicion.svg" alt="">
<h1>Checking the site connection security</h1>
<p>www.example.fi needs to review the security of your connection before proceeding.</p>
</div></body></html>"""

# Same family, asset host stripped — the filename alone must still carry it.
CHALLENGE_ASSET_ONLY = (
    '<html><body><img src="/static/robot-suspicion.svg">'
    "<p>Please wait.</p></body></html>"
)

# The 29-page family. HTTP 200, no status signal at all.
CHALLENGE_BROWSER_CHECK = """<html><head><title>Please wait</title></head><body>
<h1>Checking your browser. This will only take a few seconds...</h1>
<p>Please enable JavaScript and cookies to continue.</p></body></html>"""

# Genuine Akamai block page — the shape the Access Denied pattern was written
# for, and one of MAS's 2 true positives. Must keep matching.
AKAMAI_ACCESS_DENIED = (
    "<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD>"
    "<BODY><H1>Access Denied</H1>You don't have permission to access "
    '"http://example.fi/" on this server.<P>Reference #18.2d351ab8.1557333295.a4e16ab'
    "</BODY></HTML>"
)

ACCESS_DENIED_TITLE_ONLY = (
    "<html><head><title>403 - Access Denied</title></head>"
    "<body><p>Request refused.</p></body></html>"
)

# The false-positive family: a healthy Shopify storefront whose menu links to
# an /pages/access-denied page. Full of real content, HTTP 200.
SHOPIFY_STOREFRONT = (
    "<html><head><title>Kaunis Kauppa - Etusivu</title></head><body>"
    '<a class="skip-to-content-link" href="/pages/access-denied">Access Denied</a>'
    "<nav><ul>"
    '<li><a href="/collections/all">Tuotteet</a></li>'
    '<li><a href="/pages/access-denied">Access Denied</a></li>'
    '<li><a href="/pages/yhteystiedot">Yhteystiedot</a></li>'
    "</ul></nav>"
    "<main><h1>Tervetuloa verkkokauppaamme</h1>"
    "<p>Myymme kasintehtyja tuotteita ympari Suomen. Ota yhteytta: "
    "myynti@example.fi tai soita 010 123 4567.</p>"
    "<p>Toimitamme tilaukset kahdessa arkipaivassa. Palautusoikeus 14 vuorokautta.</p>"
    "</main></body></html>"
)


# ── the dominant signature must be detected ──────────────────────────────


@pytest.mark.parametrize(
    "label,html,status",
    [
        ("robot-suspicion full page", CHALLENGE_ROBOT_SUSPICION, 200),
        ("robot-suspicion asset only", CHALLENGE_ASSET_ONLY, 200),
        ("browser check", CHALLENGE_BROWSER_CHECK, 200),
    ],
)
def test_challenge_pages_are_detected(label, html, status):
    blocked, reason = is_blocked(status, html)
    assert blocked, f"{label}: challenge page passed through as content"
    assert reason


def test_challenge_detected_regardless_of_status():
    """Challenge interstitials come back 200, 403 and 503 depending on vendor
    config. None of those may be the thing detection depends on."""
    for status in (200, 403, 429, 503, None):
        blocked, _ = is_blocked(status, CHALLENGE_ROBOT_SUSPICION)
        assert blocked, f"missed at status {status}"


def test_robot_suspicion_detected_on_a_large_page():
    """Tier 1, so page size must not gate it — vendors pad challenge screens
    with inline CSS exactly the way Reddit's block page does."""
    padded = CHALLENGE_ROBOT_SUSPICION + (
        "<style>" + "a{color:red}" * 2000 + "</style>"
    )
    assert len(padded) > 20000
    blocked, _ = is_blocked(200, padded)
    assert blocked


# ── the Shopify false positive must be gone ──────────────────────────────


def test_shopify_access_denied_link_is_not_a_block():
    """~15 of MAS's 22 hits. A navigation link is not a block page."""
    blocked, reason = is_blocked(200, SHOPIFY_STOREFRONT)
    assert not blocked, f"healthy storefront condemned: {reason}"


def test_shopify_access_denied_link_is_not_a_block_on_404():
    """Same page reached through a 404 must still not match on link text alone.
    (A 403 legitimately blocks via the status rule, which is not this pattern.)"""
    blocked, reason = is_blocked(404, SHOPIFY_STOREFRONT)
    assert not blocked, f"condemned by link text on 404: {reason}"


# ── genuine Access Denied pages must still be caught ─────────────────────


def test_akamai_access_denied_still_detected():
    blocked, reason = is_blocked(403, AKAMAI_ACCESS_DENIED)
    assert blocked and reason


def test_access_denied_in_title_still_detected():
    blocked, reason = is_blocked(404, ACCESS_DENIED_TITLE_ONLY)
    assert blocked, "Access Denied in <title> on a 404 must still match"
    assert "Access Denied" in reason


# ── existing behaviour must be unchanged ─────────────────────────────────


def test_healthy_finnish_page_not_blocked():
    html = (
        "<html><head><title>Yritys Oy</title></head><body>"
        "<h1>Yritys Oy</h1><p>Olemme suomalainen perheyritys vuodesta 1985. "
        "Palvelemme asiakkaita ymparr Suomen.</p>"
        "<p>Yhteystiedot: info@yritys.fi, puhelin 010 123 4567.</p>"
        "<ul><li>Palvelut</li><li>Referenssit</li><li>Yhteystiedot</li></ul>"
        "</body></html>"
    )
    blocked, reason = is_blocked(200, html)
    assert not blocked, reason


def _article_quoting_challenge_wording(paragraphs: int) -> str:
    body = (
        "<p>Verkkosivustot kayttavat botteja vastaan erilaisia suojauksia. "
        "Kayttaja nakee usein tekstin 'Checking your browser' tai 'Just a moment' "
        "ennen kuin sivu latautuu. Tama artikkeli kasittelee aihetta.</p>"
    ) * paragraphs
    return (
        "<html><head><title>Bottisuojaus</title></head><body>"
        f"<h1>Bottisuojaus</h1>{body}</body></html>"
    )


@pytest.mark.parametrize("paragraphs", [40, 100])
def test_article_about_bot_blocking_not_blocked(paragraphs):
    """An article quoting every phrase in the list must survive — including at
    40 paragraphs, where the HTML is 8 KB and therefore *under* the tier-2 size
    gate. Size alone cannot separate the two; the visible-text discriminator is
    what does it."""
    html = _article_quoting_challenge_wording(paragraphs)
    blocked, reason = is_blocked(200, html)
    assert not blocked, f"{len(html)} B article condemned: {reason}"


def test_size_gate_alone_would_not_have_saved_the_article():
    """Pins the premise of the test above: the 40-paragraph article really is
    small enough that the tier-2 size gate lets it through."""
    assert len(_article_quoting_challenge_wording(40)) < 10000


def test_cloudflare_and_incapsula_tier1_unchanged():
    cf = '<html><body><span class="cf-error-code">1020</span></body></html>'
    incap = "<html><body>Incapsula incident ID: 123-456</body></html>"
    assert is_blocked(403, cf)[0]
    assert is_blocked(200, incap)[0]


def test_json_api_response_not_blocked():
    assert not is_blocked(200, '{"contacts": [{"email": "a@b.fi"}]}')[0]
