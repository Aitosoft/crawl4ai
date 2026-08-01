"""
Anti-bot detection heuristics for crawl results.

Examines HTTP status codes and HTML content patterns to determine
if a crawl was blocked by anti-bot protection.

Detection philosophy: false positives are cheap (the fallback mechanism
rescues them), false negatives are catastrophic (user gets garbage).
Err on the side of detection.

Detection is layered:
- HTTP 403/503 with HTML content → always blocked (these are never desired content)
- Tier 1 patterns (structural markers) trigger on any page size
- Challenge patterns (interstitial prose) trigger on low-text pages at any status
- Tier 2 patterns (generic terms) trigger on short pages or any error status
- Block-notice tier: the page's whole text is a refusal, at any status/size
- Tier 3 structural integrity catches silent blocks and empty shells

Evidence vs inference — Aitosoft 2026-08-01
-------------------------------------------
The tiers above are not interchangeable, and one distinction now runs through
the whole module:

    evidence   the origin's own bytes say it refused us — a vendor marker, an
               interstitial, a refusal notice, a 4xx/5xx status.
    inference  we came back with nothing and concluded "blocked" from the
               *shape* of what we got (tier 3, and near-empty at HTTP 200).

Both return ``True``, but they do not establish the same fact, and
``deploy/docker/aitosoft_failure_class.py`` now classifies them differently:
inference verdicts are *ours* (``render_error``), not the origin's
(``origin_blocked``). Four of MAS's 33 ``origin_blocked`` verdicts in the
2026-07-31 re-scrape were inference misfiring — one of them was our own
"page not fully supported" placeholder reported to the customer as the origin
blocking us. Reason strings are the seam that carries the distinction, so
**every reason produced by an inference tier must keep its ``Structural:`` /
``Near-empty content`` prefix**; ``test_failure_classification.py`` pins it.

Which gate moved, and which deliberately did not
------------------------------------------------
LOOSENED — the evidence gates are now on **visible text**, not ``len(html)``.
Four hosts served an 80,671-byte body whose entire content was
``403 - Forbidden`` at origin status 202 and passed as content, because every
size gate here read ``len(html)`` and the vendor pads to 80 KB. Our own stored
capture of ``monidor.com`` is the same defect independently: an 11,515-byte
interstitial with **58 characters** of text, over the old 10 KB challenge gate.
Padding is not evidence of content; text is.

TIGHTENED — nothing here, and that is the point: the *inference* gates
(``_STRUCTURAL_MAX_SIZE``, the near-empty-200 check) keep their ``len(html)``
bounds. Moving those onto visible text too would have made every padded page
with no recognisable notice a blocked verdict on shape alone — which is exactly
the defect above, pointed the other way. Inference was tightened where it
matters, in what the verdict is allowed to *mean*.

CORRECTION to tasks/detector-round3-evidence-vs-inference.md, which planned
this work: it stated that "the four caught hosts prove the pattern side already
works", so that moving the gates would be sufficient. It does not. Measured
2026-08-01: **no tier-1, tier-2 or challenge pattern matches that body at all**
— the four hosts that *were* caught were caught by the 403/503 status branch's
fallthrough, which is a status rule, not a pattern. A gate change alone closes
nothing; the block-notice tier below is the missing half.
"""

import re
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Tier 1: High-confidence structural markers (single signal sufficient)
# These are unique to block pages and virtually never appear in real content.
# ---------------------------------------------------------------------------
_TIER1_PATTERNS = [
    # Akamai — full reference pattern: Reference #18.2d351ab8.1557333295.a4e16ab
    (re.compile(r"Reference\s*#\s*[\d]+\.[0-9a-f]+\.\d+\.[0-9a-f]+", re.IGNORECASE),
     "Akamai block (Reference #)"),
    # Akamai — "Pardon Our Interruption" challenge page
    (re.compile(r"Pardon\s+Our\s+Interruption", re.IGNORECASE),
     "Akamai challenge (Pardon Our Interruption)"),
    # Cloudflare — challenge form with anti-bot token
    (re.compile(r'challenge-form.*?__cf_chl_f_tk=', re.IGNORECASE | re.DOTALL),
     "Cloudflare challenge form"),
    # Cloudflare — error code spans (1020 Access Denied, 1010, 1012, 1015)
    (re.compile(r'<span\s+class="cf-error-code">\d{4}</span>', re.IGNORECASE),
     "Cloudflare firewall block"),
    # Cloudflare — IUAM challenge script
    (re.compile(r'/cdn-cgi/challenge-platform/\S+orchestrate', re.IGNORECASE),
     "Cloudflare JS challenge"),
    # PerimeterX / HUMAN — block page with app ID assignment (not prose mentions)
    (re.compile(r"window\._pxAppId\s*=", re.IGNORECASE),
     "PerimeterX block"),
    # PerimeterX — captcha CDN
    (re.compile(r"captcha\.px-cdn\.net", re.IGNORECASE),
     "PerimeterX captcha"),
    # DataDome — captcha delivery domain (structural, not the word "datadome")
    (re.compile(r"captcha-delivery\.com", re.IGNORECASE),
     "DataDome captcha"),
    # Imperva/Incapsula — resource iframe
    (re.compile(r"_Incapsula_Resource", re.IGNORECASE),
     "Imperva/Incapsula block"),
    # Imperva/Incapsula — incident ID
    (re.compile(r"Incapsula\s+incident\s+ID", re.IGNORECASE),
     "Imperva/Incapsula incident"),
    # Sucuri firewall
    (re.compile(r"Sucuri\s+WebSite\s+Firewall", re.IGNORECASE),
     "Sucuri firewall block"),
    # Kasada
    (re.compile(r"KPSDK\.scriptStart\s*=\s*KPSDK\.now\(\)", re.IGNORECASE),
     "Kasada challenge"),
    # Network security block — Reddit and other platforms serve large SPA shells
    # with this message buried under 100KB+ of CSS/JS
    (re.compile(r"blocked\s+by\s+network\s+security", re.IGNORECASE),
     "Network security block"),
    # Aitosoft 2026-07-30 — the challenge family that dominates Finnish SME
    # crawling. MAS measured 371 of 402 stored challenge pages carrying this
    # asset; nothing in the list above matched any of them. The vendor is not
    # identified yet, so match the literal artefacts rather than inventing a
    # family (tasks/antibot-detector-challenge-blindspot.md). Tier 1 because a
    # hyphenated asset filename is not prose and cannot appear in real content.
    (re.compile(r"robot-suspicion", re.IGNORECASE),
     "Unidentified challenge (robot-suspicion asset)"),
    (re.compile(r"d1rozh26tys225\.cloudfront\.net", re.IGNORECASE),
     "Unidentified challenge (challenge asset host)"),
]

# ---------------------------------------------------------------------------
# Challenge tier: interstitial prose, checked on ANY status code for small
# pages.
#
# Aitosoft 2026-07-30. The tier-2 list below is only ever evaluated on 4xx/5xx
# responses (see is_blocked), but JS challenge interstitials are overwhelmingly
# served with **HTTP 200** — so "Checking your browser" has never once been
# consulted for the pages it was written for. MAS found 29 such pages stored as
# successful content. This tier closes that gap with a deliberately tiny,
# high-confidence list: interstitial wording only, no generic block phrases and
# no CAPTCHA-class markers, because a false positive here costs a real page.
# Size-gated exactly like tier 2 so an article discussing bot challenges cannot
# match. The entries stay in _TIER2_PATTERNS as well — that path adds
# large-page coverage for 403/503 via the stripped deep snippet.
# ---------------------------------------------------------------------------
_CHALLENGE_PATTERNS = [
    (re.compile(r"Checking\s+the\s+site\s+connection\s+security", re.IGNORECASE),
     "Challenge interstitial (checking site connection security)"),
    (re.compile(r"Checking\s+your\s+browser", re.IGNORECASE),
     "Challenge interstitial (checking your browser)"),
    (re.compile(r"<title>\s*Just\s+a\s+moment", re.IGNORECASE),
     "Challenge interstitial (Just a moment)"),
    # Aitosoft 2026-08-01, from our own stored capture of `monidor.com`
    # (test-aitosoft/artifacts/mas-comparison/): title "One moment, please...",
    # body "Please wait while your request is being verified...". 11,515 bytes
    # of HTML over **58 characters** of text, returned to MAS as a successful
    # capture. It is the same class as the padded 403 below — the old gate read
    # `len(html) < 10000` and this page is 11.5 KB — and it is real rather than
    # synthetic, which is why it is worth two more patterns.
    (re.compile(r"<title>\s*One\s+moment,?\s*please", re.IGNORECASE),
     "Challenge interstitial (One moment, please)"),
    (re.compile(r"your\s+request\s+is\s+being\s+verified", re.IGNORECASE),
     "Challenge interstitial (request being verified)"),
]

# ---------------------------------------------------------------------------
# Tier 2: Medium-confidence patterns — only match on SHORT pages (< 10KB)
# These terms appear in real content (articles, login forms, security blogs)
# so we require the page to be small to avoid false positives.
# ---------------------------------------------------------------------------
_TIER2_PATTERNS = [
    # Akamai / generic — "Access Denied", but only where a block page puts it:
    # the title or a top-level heading.
    #
    # Aitosoft 2026-07-30: the bare `Access\s+Denied` form was this list's worst
    # pattern in production. MAS's corpus scan returned 22 hits of which ~15
    # were Shopify storefronts carrying an `/pages/access-denied` navigation
    # link — full, healthy pages condemned by their own menu. Requiring
    # title/heading context keeps the genuine Akamai page
    # (`<TITLE>Access Denied</TITLE><H1>Access Denied</H1>`) and drops link
    # text. Real 403s are unaffected: the 403/503 branch below already flags any
    # non-data HTML body without needing this pattern at all.
    (re.compile(r"<(?:title|h[1-3])[^>]*>[^<]{0,60}Access\s+Denied", re.IGNORECASE),
     "Access Denied in title/heading on short page"),
    # Cloudflare — "Just a moment" / "Checking your browser"
    (re.compile(r"Checking\s+your\s+browser", re.IGNORECASE),
     "Cloudflare browser check"),
    (re.compile(r"<title>\s*Just\s+a\s+moment", re.IGNORECASE),
     "Cloudflare interstitial"),
    # CAPTCHA on a block page (not a login form — login forms are big pages)
    (re.compile(r'class=["\']g-recaptcha["\']', re.IGNORECASE),
     "reCAPTCHA on block page"),
    (re.compile(r'class=["\']h-captcha["\']', re.IGNORECASE),
     "hCaptcha on block page"),
    # PerimeterX block page title
    (re.compile(r"Access\s+to\s+This\s+Page\s+Has\s+Been\s+Blocked", re.IGNORECASE),
     "PerimeterX block page"),
    # Generic block phrases (only on short pages to avoid matching articles)
    (re.compile(r"blocked\s+by\s+security", re.IGNORECASE),
     "Blocked by security"),
    (re.compile(r"Request\s+unsuccessful", re.IGNORECASE),
     "Request unsuccessful (Imperva)"),
]

_TIER2_MAX_SIZE = 10000  # Only check tier 2 patterns on pages under 10KB

# Challenge tier: a real interstitial carries a heading, a sentence and a ray
# ID — a few hundred characters. 1500 leaves generous headroom for a wordy
# vendor while staying far below any page with actual content on it.
#
# Aitosoft 2026-08-01: this is now the tier's ONLY size gate. It used to sit
# behind `len(html) < _TIER2_MAX_SIZE`, which is what hid `monidor.com`'s
# 11,515-byte / 58-character interstitial.
_CHALLENGE_MAX_VISIBLE_TEXT = 1500

# ---------------------------------------------------------------------------
# Block-notice tier (Aitosoft 2026-08-01): the page's entire text is a refusal.
#
# The defect this closes: four hosts returned 80,671 bytes rendering to
# `# 403 - Forbidden / Access to this page is forbidden.` at origin status
# **202**, `success: true`. The identical bytes at status 403 were classified
# correctly on four other hosts — by the status branch, not by any pattern.
# So neither the size gates nor the pattern list could have caught it: the
# gates were on `len(html)` and no pattern matched a bare HTTP refusal notice.
#
# The generalisable statement is: *a page whose whole visible text is a refusal
# is a refusal, whatever status it was served at and however much padding
# surrounds it.* Origin evidence, not inference — the origin's own bytes say so
# — which is why this maps to `origin_blocked` and tier 3 no longer does.
#
# The two discriminators below are the whole safety of this tier, and they are
# not optional. MAS's corpus scan found ~15 of 22 "Access Denied" hits were
# healthy Shopify storefronts carrying an `/pages/access-denied` navigation
# link, and such a storefront can easily sit under the text gate — our own
# fixture for that false positive measures **247** characters of visible text.
# Matching "these words appear somewhere" would re-open that family verbatim.
# So a notice counts only when the origin either
#   (1) put it where a page puts its subject — the <title> or an <h1>-<h3>,
#       the idiom the tier-2 `Access Denied` pattern already uses, or
#   (2) had nothing else to say: the matched text is most of the page.
# ---------------------------------------------------------------------------
_BLOCK_NOTICE_PATTERNS = [
    # "Access to this page has been denied." / "Access to this page is
    # forbidden." / "Access Denied" — the refusal written out.
    (re.compile(
        r"\baccess\b[^.!?]{0,60}?\b(?:denied|forbidden|blocked)\b", re.IGNORECASE),
     "Access refused"),
    # "403 - Forbidden", "Error 403 Forbidden", "HTTP 401 Unauthorized".
    # 404 and 5xx are deliberately absent: a missing page or a broken origin is
    # `origin_http_error`, and calling it a block is the `snuup.fi` defect.
    (re.compile(
        r"\b(?:401|403|429|451)\b[\s\-–—:|]*"
        r"(?:forbidden|unauthori[sz]ed|denied|blocked|too\s+many\s+requests)",
        re.IGNORECASE),
     "HTTP refusal status"),
    (re.compile(
        r"\b(?:forbidden|unauthori[sz]ed)\b[\s\-–—:|]*\b(?:401|403)\b",
        re.IGNORECASE),
     "HTTP refusal status"),
    # "You have been blocked", "Your request was blocked", "This IP is blocked".
    (re.compile(
        r"\b(?:you|your\s+(?:request|ip|access|connection)|this\s+(?:request|ip))\b"
        r"[^.!?]{0,40}?\bblocked\b", re.IGNORECASE),
     "Request blocked"),
]

#: A refusal notice is a heading and a sentence. 500 is measured, not picked:
#: the smallest healthy content page in our 58 stored real captures carries
#: **739** characters of text, and everything below that in the corpus is a
#: cookie wall (0) or an interstitial (58). It is also
#: `aitosoft_collapse_guard.MIN_VISIBLE_TEXT_CHARS`, deliberately — that guard
#: declares pages under 500 characters "the detector's business", so the two
#: modules meet exactly here instead of overlapping or leaving a gap.
_BLOCK_NOTICE_MAX_VISIBLE_TEXT = 500

#: Discriminator (2): how much of the page the notice has to *be*. The Shopify
#: false-positive fixture measures 0.11 (13 characters of link text in 247);
#: a real notice measures 0.94-1.00.
_BLOCK_NOTICE_MIN_COVERAGE = 0.5

#: Where a page states its subject. Same idiom as the tier-2 `Access Denied`
#: pattern, which is what made that one safe against MAS's corpus.
_HEADING_RE = re.compile(
    r"<(?:title|h[1-3])\b[^>]*>(.*?)</(?:title|h[1-3])\s*>", re.IGNORECASE | re.DOTALL
)

_WHITESPACE_RE = re.compile(r"\s+")

# How much of a large document to strip and scan for prose. Stripping is what
# makes an 80 KB padded page readable — the padding is inline CSS — so the
# tier-1 deep scan, the challenge tier and the block-notice tier all share it
# rather than each re-deriving it.
_PROSE_SCAN_LIMIT = 500000
_PROSE_SNIPPET_CHARS = 30000

# ---------------------------------------------------------------------------
# Tier 3: Structural integrity — catches silent blocks, anti-bot redirects,
# incomplete renders that pass pattern detection but are structurally broken
# ---------------------------------------------------------------------------
_STRUCTURAL_MAX_SIZE = 50000  # Only check pages under 50KB
_CONTENT_ELEMENTS_RE = re.compile(
    r'<(?:p|h[1-6]|article|section|li|td|a|pre)\b', re.IGNORECASE
)
_SCRIPT_TAG_RE = re.compile(r'<script\b', re.IGNORECASE)
_STYLE_TAG_RE = re.compile(r'<style\b[\s\S]*?</style>', re.IGNORECASE)
_SCRIPT_BLOCK_RE = re.compile(r'<script\b[\s\S]*?</script>', re.IGNORECASE)
_TAG_RE = re.compile(r'<[^>]+>')
_BODY_RE = re.compile(r'<body\b', re.IGNORECASE)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
_BLOCK_PAGE_MAX_SIZE = 5000   # 403 + short page = likely block
_EMPTY_CONTENT_THRESHOLD = 100  # 200 + near-empty = JS-blocked render


def _looks_like_data(html: str) -> bool:
    """Check if content looks like a JSON/XML API response (not an HTML block page)."""
    stripped = html.strip()
    if not stripped:
        return False
    # Raw JSON/XML (not wrapped in HTML)
    if stripped[0] in ('{', '['):
        return True
    # Browser-rendered JSON: browsers wrap raw JSON in <html><body><pre>{...}</pre>
    if stripped[:10].lower().startswith(('<html', '<!')):
        if re.search(r'<body[^>]*>\s*<pre[^>]*>\s*[{\[]', stripped[:500], re.IGNORECASE):
            return True
        return False
    # Other XML-like content
    return stripped[0] == '<'


def _visible_text(html: str) -> str:
    """Body text with scripts, styles and tags removed. Cheap approximation —
    used to tell a block/challenge screen (a few hundred characters of prose)
    from a real page that merely mentions one."""
    body_match = re.search(r'<body\b[^>]*>([\s\S]*)</body>', html, re.IGNORECASE)
    body_content = body_match.group(1) if body_match else html
    stripped = _SCRIPT_BLOCK_RE.sub('', body_content)
    stripped = _STYLE_TAG_RE.sub('', stripped)
    return _TAG_RE.sub('', stripped).strip()


def _normalized_visible_text(html: str) -> str:
    """``_visible_text`` with runs of whitespace collapsed.

    Normalising is not cosmetic, and it is what makes a *text* gate mean the
    same thing everywhere: `monidor.com`'s interstitial measures 506 raw
    "visible" characters and **58** once collapsed — the other 448 are markup
    indentation. ``aitosoft_collapse_guard`` normalises the same way for the
    same reason, so the two modules agree about what counts as text on a page.
    """
    return _WHITESPACE_RE.sub(" ", _visible_text(html)).strip()


def _prose_snippet(html: str) -> str:
    """The head of the document with ``<script>`` and ``<style>`` blocks gone.

    Modern block and challenge pages bury a two-line notice under 80-180 KB of
    inline CSS, so the raw first-15 KB window can hold nothing but padding.
    """
    stripped = _SCRIPT_BLOCK_RE.sub('', html[:_PROSE_SCAN_LIMIT])
    stripped = _STYLE_TAG_RE.sub('', stripped)
    return stripped[:_PROSE_SNIPPET_CHARS]


def _covered_chars(spans) -> int:
    """Total length of a set of possibly-overlapping ``(start, end)`` spans."""
    total = 0
    reach = -1
    for start, end in sorted(spans):
        if end <= reach:
            continue
        total += end - max(start, reach)
        reach = end
    return total


def _block_notice_check(prose: str, visible: str) -> Tuple[bool, str]:
    """Is this page's own text a refusal notice, and nothing else?

    ``prose`` is the script/style-stripped markup (so headings survive);
    ``visible`` is the normalised body text. See ``_BLOCK_NOTICE_PATTERNS`` for
    why both discriminators are needed and what happens without them.
    """
    if not visible or len(visible) > _BLOCK_NOTICE_MAX_VISIBLE_TEXT:
        return False, ""

    spans = []
    label = ""
    for pattern, reason in _BLOCK_NOTICE_PATTERNS:
        for match in pattern.finditer(visible):
            spans.append(match.span())
            label = label or reason
    if not spans:
        return False, ""

    # (1) the origin put the notice where a page puts its subject
    headings = _WHITESPACE_RE.sub(
        " ", " ".join(_TAG_RE.sub(" ", h) for h in _HEADING_RE.findall(prose))
    )
    in_heading = any(p.search(headings) for p, _ in _BLOCK_NOTICE_PATTERNS)

    # (2) …or the notice is all the page has to say
    coverage = _covered_chars(spans) / len(visible)

    if not in_heading and coverage < _BLOCK_NOTICE_MIN_COVERAGE:
        return False, ""

    where = "in the page heading" if in_heading else f"{coverage:.0%} of the page text"
    return True, (
        f"Block notice is the page: {label} ({where}, "
        f"{len(visible)} chars visible): {visible[:120]}"
    )


def _structural_integrity_check(html: str) -> Tuple[bool, str]:
    """
    Tier 3: Structural integrity check for pages that pass pattern detection
    but are structurally broken — incomplete renders, anti-bot redirects, empty shells.

    Only applies to pages < 50KB that aren't JSON/XML.

    Returns:
        Tuple of (is_blocked, reason).
    """
    html_len = len(html)

    # Skip large pages (unlikely to be block pages) and data responses
    if html_len > _STRUCTURAL_MAX_SIZE or _looks_like_data(html):
        return False, ""

    signals = []

    # Signal 1: No <body> tag — definitive structural failure
    if not _BODY_RE.search(html):
        return True, f"Structural: no <body> tag ({html_len} bytes)"

    # Signal 2: Minimal visible text after stripping scripts/styles/tags
    visible_len = len(_visible_text(html))
    if visible_len < 50:
        signals.append("minimal_text")

    # Signal 3: No content elements (semantic HTML)
    content_elements = len(_CONTENT_ELEMENTS_RE.findall(html))
    if content_elements == 0:
        signals.append("no_content_elements")

    # Signal 4: Script-heavy shell — scripts present but no content
    script_count = len(_SCRIPT_TAG_RE.findall(html))
    if script_count > 0 and content_elements == 0 and visible_len < 100:
        signals.append("script_heavy_shell")

    # Scoring
    signal_count = len(signals)
    if signal_count >= 2:
        return True, f"Structural: {', '.join(signals)} ({html_len} bytes, {visible_len} chars visible)"

    if signal_count == 1 and html_len < 5000:
        return True, f"Structural: {signals[0]} on small page ({html_len} bytes, {visible_len} chars visible)"

    return False, ""


def effective_status(
    status_code: Optional[int],
    redirected_status_code: Optional[int] = None,
) -> Optional[int]:
    """
    The status code that actually produced the HTML we are holding.

    `AsyncCrawlResponse.status_code` / `CrawlResult.status_code` deliberately
    carry the **first** hop of a redirect chain (a 3xx), while the body always
    comes from the **last** hop; the final status is kept separately as
    `redirected_status_code`.  Block detection must be given the last hop —
    otherwise a site that redirects apex -> www and then serves a 403 block
    page is judged on its 301, no status rule fires, and the block page is
    returned as successful content.

    `redirected_status_code` is None on non-HTTP paths (raw:, file://,
    js_only), so fall back to `status_code` there.

    Args:
        status_code: First hop of the redirect chain (or the only response).
        redirected_status_code: Final hop, when the request was redirected.

    Returns:
        The status code to judge the response body by.
    """
    return redirected_status_code or status_code


def is_blocked(
    status_code: Optional[int],
    html: str,
    error_message: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Detect if a crawl result indicates anti-bot blocking.

    Uses layered detection to maximize coverage while minimizing false positives:
    - Tier 1 patterns (structural markers) trigger on any page size
    - Tier 2 patterns (generic terms) only trigger on short pages (< 10KB)
    - Tier 3 structural integrity catches silent blocks and empty shells
    - Status-code checks require corroborating content signals

    Args:
        status_code: HTTP status code from the response.
        html: Raw HTML content from the response.
        error_message: Error message from the crawl result, if any.

    Returns:
        Tuple of (is_blocked, reason). reason is empty string when not blocked.
    """
    html = html or ""
    html_len = len(html)

    # --- HTTP 429 is always rate limiting ---
    if status_code == 429:
        return True, "HTTP 429 Too Many Requests"

    # --- Check for tier 1 patterns (high confidence, any page size) ---
    # First check the raw start of the page (fast path for small pages).
    # Then, for large pages, also check a stripped version (scripts/styles
    # removed) because modern block pages bury text under 100KB+ of CSS/JS.
    snippet = html[:15000]
    if snippet:
        for pattern, reason in _TIER1_PATTERNS:
            if pattern.search(snippet):
                return True, reason

    # Large-page deep scan: strip scripts/styles and re-check tier 1
    _prose = _prose_snippet(html) if html_len > 15000 else snippet
    if html_len > 15000:
        for pattern, reason in _TIER1_PATTERNS:
            if pattern.search(_prose):
                return True, reason

    # Everything below judges the page by how much *text* it has, not how many
    # bytes it weighs, so compute it once. (Aitosoft 2026-08-01 — the gates
    # used to be on `len(html)`, and a vendor that pads its block page to 80 KB
    # walked through all of them.)
    #
    # Cost, measured so nobody has to wonder: this makes `is_blocked` **6.6 ms**
    # mean across our 58 stored real captures (median page 178 KB) and 16.5 ms
    # on the largest we hold (720 KB), against 6.8 ms for that page before. A
    # render is 2-4 s, so it is under 0.5 % of a crawl. It was left exact rather
    # than short-circuited on a bounded prefix: this is the most
    # safety-critical module in the service and a few ms is not worth a
    # semantic subtlety in it.
    _is_data = _looks_like_data(html)
    _visible = "" if _is_data else _normalized_visible_text(html)
    _visible_len = len(_visible)

    # --- Challenge interstitials on a low-text page, at ANY status ---
    # Challenge screens are normally served with HTTP 200, which the tier-2
    # path below never reaches. See _CHALLENGE_PATTERNS.
    #
    # A challenge screen is a few hundred characters of prose. An article
    # *about* bot challenges quotes the same wording and is thousands. Size in
    # bytes does not separate them — an 8 KB page is under the old gate yet
    # holds ~6 KB of real text, and an 11.5 KB interstitial is over it while
    # holding 58 — so the gate is the text itself. Without it, one Finnish blog
    # post on bot protection would be classified as a block.
    if not _is_data and _visible_len < _CHALLENGE_MAX_VISIBLE_TEXT:
        for pattern, reason in _CHALLENGE_PATTERNS:
            if pattern.search(_prose):
                return True, (
                    f"{reason} (HTTP {status_code}, {html_len} bytes, "
                    f"{_visible_len} chars visible)"
                )

    # --- HTTP 403/503 — always blocked for non-data HTML responses ---
    # Rationale: 403/503 are never the content the user wants. Modern block pages
    # (Reddit, LinkedIn, etc.) serve full SPA shells that exceed 100KB, so
    # size-based filtering misses them. Even for a legitimate auth error, the
    # fallback (Web Unlocker) will also get 403 and we correctly report failure.
    # False positives are cheap — the fallback mechanism rescues them.
    if status_code in (403, 503) and not _looks_like_data(html):
        if html_len < _EMPTY_CONTENT_THRESHOLD:
            return True, f"HTTP {status_code} with near-empty response ({html_len} bytes)"
        # For large pages, strip scripts/styles to find block text in the
        # actual content (Reddit hides it under 180KB of inline CSS).
        # Check tier 2 patterns regardless of page size.
        _check_snippet = _prose_snippet(html) if html_len > _TIER2_MAX_SIZE else snippet
        for pattern, reason in _TIER2_PATTERNS:
            if pattern.search(_check_snippet):
                return True, f"{reason} (HTTP {status_code}, {html_len} bytes)"
        # Even without a pattern match, a non-data 403/503 HTML page is
        # almost certainly a block. Flag it so the fallback gets a chance.
        return True, f"HTTP {status_code} with HTML content ({html_len} bytes)"

    # --- Tier 2 patterns on other 4xx/5xx + short page ---
    if status_code and status_code >= 400 and html_len < _TIER2_MAX_SIZE:
        for pattern, reason in _TIER2_PATTERNS:
            if pattern.search(snippet):
                return True, f"{reason} (HTTP {status_code}, {html_len} bytes)"

    # --- The page's whole text is a refusal notice, at ANY status or size ---
    # The last of the evidence tiers, and the one that does not need a status
    # to work: the four hosts this was written for served their block page at
    # 202. It sits *after* the status branches so a 403 keeps its existing,
    # more specific reason, and *before* the two inference checks below so that
    # origin evidence always outranks a verdict derived from shape.
    if not _is_data:
        _blocked, _reason = _block_notice_check(_prose, _visible)
        if _blocked:
            return True, f"{_reason} (HTTP {status_code}, {html_len} bytes)"

    # ---------------------------------------------------------------------
    # INFERENCE from here down. Nothing below is the origin telling us it
    # refused us — it is us observing that we came back with nothing. The
    # reason strings must keep their `Near-empty content` / `Structural:`
    # prefixes: aitosoft_failure_class.py reads them to decide that these are
    # OUR failures (`render_error`) and not the origin's (`origin_blocked`).
    # Reporting a healthy site as permanently blocked is the expensive
    # direction, and these tiers are where that used to happen.
    #
    # Their `len(html)` bounds stay exactly where they were, on purpose. See
    # the module docstring: moving them onto visible text would turn every
    # padded page with no recognisable notice into a blocked verdict on shape
    # alone, which is the defect above wearing the other hat.
    # ---------------------------------------------------------------------

    # --- HTTP 200 + near-empty content (JS-rendered empty page) ---
    if status_code == 200:
        stripped = html.strip()
        if len(stripped) < _EMPTY_CONTENT_THRESHOLD and not _is_data:
            return True, f"Near-empty content ({len(stripped)} bytes) with HTTP 200"

    # --- Tier 3: Structural integrity (catches silent blocks, redirects, incomplete renders) ---
    _blocked, _reason = _structural_integrity_check(html)
    if _blocked:
        return True, _reason

    return False, ""
