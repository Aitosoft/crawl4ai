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
- Challenge patterns (interstitial prose) trigger on short pages at any status
- Tier 2 patterns (generic terms) trigger on short pages or any error status
- Tier 3 structural integrity catches silent blocks and empty shells
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
_CHALLENGE_MAX_VISIBLE_TEXT = 1500

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
    if html_len > 15000:
        _stripped_for_t1 = _SCRIPT_BLOCK_RE.sub('', html[:500000])
        _stripped_for_t1 = _STYLE_TAG_RE.sub('', _stripped_for_t1)
        _deep_snippet = _stripped_for_t1[:30000]
        for pattern, reason in _TIER1_PATTERNS:
            if pattern.search(_deep_snippet):
                return True, reason

    # --- Challenge interstitials on a small page, at ANY status ---
    # Challenge screens are normally served with HTTP 200, which the tier-2
    # path below never reaches. See _CHALLENGE_PATTERNS.
    if html_len < _TIER2_MAX_SIZE and not _looks_like_data(html):
        for pattern, reason in _CHALLENGE_PATTERNS:
            if pattern.search(snippet):
                # A challenge screen is a few hundred characters of prose. An
                # article *about* bot challenges quotes the same wording and is
                # thousands. Size alone does not separate them — an 8 KB page
                # is under the tier-2 gate yet holds ~6 KB of real text — so
                # require the page to be as empty as an interstitial actually
                # is. Without this, one Finnish blog post on bot protection
                # would be classified as a block.
                _visible_len = len(_visible_text(html))
                if _visible_len < _CHALLENGE_MAX_VISIBLE_TEXT:
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
        if html_len > _TIER2_MAX_SIZE:
            _stripped = _SCRIPT_BLOCK_RE.sub('', html[:500000])
            _stripped = _STYLE_TAG_RE.sub('', _stripped)
            _check_snippet = _stripped[:30000]
        else:
            _check_snippet = snippet
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

    # --- HTTP 200 + near-empty content (JS-rendered empty page) ---
    if status_code == 200:
        stripped = html.strip()
        if len(stripped) < _EMPTY_CONTENT_THRESHOLD and not _looks_like_data(html):
            return True, f"Near-empty content ({len(stripped)} bytes) with HTTP 200"

    # --- Tier 3: Structural integrity (catches silent blocks, redirects, incomplete renders) ---
    _blocked, _reason = _structural_integrity_check(html)
    if _blocked:
        return True, _reason

    return False, ""
