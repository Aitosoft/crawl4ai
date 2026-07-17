"""
Aitosoft: static-mode rendering (``render_mode: "static"`` on POST /crawl).

httpx + html2text, no Playwright. Added for hosts where Playwright hangs at
the C-level DevTools protocol (e.g. roadscanners.com) and only the request
wall-clock deadline unblocks the pool. MAS auto-pivots to static mode after
2 consecutive 504s per host per session.

Design constraints (deliberate — see tasks/done/static-html-fallback-mode-*.md):
- No hookability, extraction strategies, or content filtering. Minimal on purpose.
- Response envelope matches handle_crawl_request exactly; every inner result
  carries ``render_mode: "static"`` and its own ``success`` flag.
- Network failures NEVER raise — they become success=false results so the
  HTTP status stays 200. 504 is reserved for "we tried to render and failed".

This file is Aitosoft-only. api.py short-circuits into handle_static_crawl_request
when the request carries render_mode == "static"; server.py's lifespan calls
close_static_http_client on shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional

import httpx

# Module scope on purpose: _fetch_static_one's contract is "never raises", so
# an import failure must surface at first module load (one clear 500), not
# propagate through gather() on every request.
from crawl4ai.html2text import HTML2Text
from egress_broker import EgressBlocked, check_redirect

logger = logging.getLogger(__name__)

# Per-URL HTTP timeout default. Separate from limits.wall_clock_s because
# static fetches should be fast or fail fast — the whole point of static mode
# is a cheap alternative to Playwright. Configurable via
# crawler.static_fetch_timeout_s in config.yml.
DEFAULT_STATIC_FETCH_TIMEOUT_S = 15

# Cap on concurrent fetches per request batch: a 100-URL request must not open
# 100 sockets at once (replica has 2 vCPU; html2text is CPU-bound).
STATIC_FETCH_MAX_CONCURRENCY = 10

# Redirect hops followed per URL. Each hop is re-validated against the same
# egress rule as full mode (egress_broker.check_redirect), so a public page
# 302-ing to IMDS or an internal service is refused, not fetched.
STATIC_MAX_REDIRECT_HOPS = 5

_static_http_client: Optional[httpx.AsyncClient] = None
_static_http_client_lock = asyncio.Lock()
_STATIC_USER_AGENT_FALLBACK = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)
_static_user_agent_cached: Optional[str] = None
_static_fetch_timeout_cached: Optional[float] = None


def _get_static_fetch_timeout_s() -> float:
    """Per-URL fetch timeout from config.yml (crawler.static_fetch_timeout_s),
    falling back to the module default. Cached per-process, same pattern as
    the UA below and aitosoft_admission's gate sizing."""
    global _static_fetch_timeout_cached
    if _static_fetch_timeout_cached is None:
        try:
            from utils import load_config

            _static_fetch_timeout_cached = float(
                (load_config().get("crawler", {}) or {}).get(
                    "static_fetch_timeout_s", DEFAULT_STATIC_FETCH_TIMEOUT_S
                )
            )
        except Exception:
            _static_fetch_timeout_cached = float(DEFAULT_STATIC_FETCH_TIMEOUT_S)
    return _static_fetch_timeout_cached


def _get_memory_mb() -> Optional[float]:
    try:
        import psutil

        return psutil.Process().memory_info().rss // (1024 * 1024)
    except Exception:
        return None


def _get_static_user_agent() -> str:
    """Mirror the full-mode UA from config.yml so static fetches don't look
    like a different client to target sites. Falls back to a Chrome UA if
    config is unavailable for any reason. Cached per-process."""
    global _static_user_agent_cached
    if _static_user_agent_cached is not None:
        return _static_user_agent_cached
    try:
        from utils import load_config

        cfg = load_config()
        ua = (
            (cfg.get("crawler", {}) or {})
            .get("browser", {})
            .get("kwargs", {})
            .get("user_agent")
        )
        _static_user_agent_cached = ua or _STATIC_USER_AGENT_FALLBACK
    except Exception:
        _static_user_agent_cached = _STATIC_USER_AGENT_FALLBACK
    return _static_user_agent_cached


async def _get_static_http_client() -> httpx.AsyncClient:
    """Return the module-scope httpx.AsyncClient, creating it on first use."""
    global _static_http_client
    if _static_http_client is None:
        async with _static_http_client_lock:
            if _static_http_client is None:
                _static_http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(_get_static_fetch_timeout_s()),
                    # Deliberate: broken-cert SME sites must crawl in static
                    # mode just like they do in full mode, where upstream
                    # hardcodes --ignore-certificate-errors into every
                    # Chromium launch (verified live 2026-07-17; see
                    # tasks/done/tls-broken-cert-regression-2026-07-17.md).
                    verify=False,
                    # Redirects are followed manually in _fetch_static_one so
                    # every hop is SSRF-validated via egress_broker.
                    follow_redirects=False,
                    headers={
                        "User-Agent": _get_static_user_agent(),
                        "Accept": (
                            "text/html,application/xhtml+xml,"
                            "application/xml;q=0.9,*/*;q=0.8"
                        ),
                        "Accept-Language": "fi,en;q=0.7",
                    },
                )
    return _static_http_client


async def close_static_http_client() -> None:
    """Close the module-scope httpx client. Called from server.py lifespan."""
    global _static_http_client
    if _static_http_client is not None:
        client = _static_http_client
        _static_http_client = None
        try:
            await client.aclose()
        except Exception as e:
            logger.warning(f"[static] client close raised (non-fatal): {e}")


def _static_error_result(
    url: str,
    *,
    status_code: int = 0,
    error_message: Optional[str] = None,
) -> dict:
    return {
        "url": url,
        "success": False,
        "status_code": status_code,
        "error_message": error_message,
        "render_mode": "static",
        "markdown": {"raw_markdown": "", "fit_markdown": ""},
        "links": {"internal": [], "external": []},
    }


def _strip_hidden_decoys(html: str) -> str:
    """Remove CSS-hidden nodes before markdown conversion.

    Motivates: roadscanners.com (and other Odoo-powered sites) obfuscate
    emails by inlining a hidden ``<span class="oe_displaynone">null</span>``
    between the user and domain parts. Browsers hide the span via CSS;
    html2text, which has no CSS awareness, keeps the text, producing
    ``name@nullroadscanners.com``.

    We strip elements hidden via inline style or common display-none utility
    classes. Deliberately NOT matching sr-only / visually-hidden — those are
    accessibility utilities that legitimately hold screen-reader-only content.
    """
    try:
        from bs4 import BeautifulSoup
    except Exception as e:  # pragma: no cover — BS4 is a crawl4ai dep
        logger.warning(f"[static] BeautifulSoup unavailable: {e}; skipping decoy strip")
        return html

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        # Fall back to the stdlib parser if lxml chokes on malformed input.
        soup = BeautifulSoup(html, "html.parser")

    for tag_name in ("script", "style", "noscript", "template"):
        for t in soup.find_all(tag_name):
            t.decompose()

    # Inline style="display:none" / "visibility:hidden".
    for t in soup.find_all(
        style=lambda v: bool(v)
        and (
            "display:none" in v.replace(" ", "").lower()
            or "visibility:hidden" in v.replace(" ", "").lower()
        )
    ):
        t.decompose()

    # Class-based display-none utilities commonly used to hide scraper decoys.
    # oe_displaynone is Odoo; d-none is Bootstrap 4+; is-hidden is Bulma.
    # Note: BS4 calls the class_ callable once per class name (a string),
    # not once per tag with the class list.
    hidden_classes = {
        "oe_displaynone",
        "d-none",
        "is-hidden",
    }
    for t in soup.find_all(class_=lambda cs: cs in hidden_classes):
        t.decompose()

    return str(soup)


async def _fetch_static_one(url: str) -> dict:
    """Fetch a single URL with httpx and convert the body to markdown. Never
    raises — all failure modes are encoded into the returned dict so the
    caller can gather() without `return_exceptions=True`.

    Redirects are followed manually (≤ STATIC_MAX_REDIRECT_HOPS) and every
    Location is re-validated with egress_broker.check_redirect — the same rule
    full mode enforces via the pinning egress proxy. The seed URL itself was
    already validated by api.py's _normalize_and_validate_seeds; without the
    per-hop check a public page 302-ing to http://169.254.169.254/ (IMDS) or
    an internal service would be fetched and returned to the caller."""
    client = await _get_static_http_client()
    timeout_s = _get_static_fetch_timeout_s()
    t0 = time.time()
    current_url = url
    hops = 0
    try:
        while True:
            resp = await client.get(current_url)
            if not resp.has_redirect_location:
                break
            hops += 1
            if hops > STATIC_MAX_REDIRECT_HOPS:
                logger.info(
                    f"[static] too many redirects (>{STATIC_MAX_REDIRECT_HOPS}): {url}"
                )
                return _static_error_result(
                    url,
                    error_message=(
                        f"static-fetch: too many redirects "
                        f"(>{STATIC_MAX_REDIRECT_HOPS})"
                    ),
                )
            try:
                next_url = str(httpx.URL(current_url).join(resp.headers["location"]))
            except Exception:
                return _static_error_result(
                    url, error_message="static-fetch: invalid redirect location"
                )
            try:
                check_redirect(next_url)
            except EgressBlocked:
                # error_message stays opaque (no target echo) — egress_broker
                # rule; the server log is trusted and keeps the ops signal.
                logger.warning(
                    f"[static] redirect blocked (SSRF): {url} -> {next_url} "
                    f"(hop {hops})"
                )
                return _static_error_result(
                    url,
                    error_message=("static-fetch: redirect blocked (SSRF protection)"),
                )
            current_url = next_url
    except httpx.TimeoutException:
        logger.info(f"[static] timeout after {timeout_s:g}s: {current_url}")
        return _static_error_result(
            url,
            error_message=f"static-fetch: timeout after {timeout_s:g}s",
        )
    except httpx.RequestError as e:
        logger.info(f"[static] request error: {current_url} {type(e).__name__}: {e}")
        return _static_error_result(
            url,
            error_message=f"static-fetch: {type(e).__name__}: {e}",
        )
    except Exception as e:
        logger.error(f"[static] unexpected error: {current_url} {e}", exc_info=True)
        return _static_error_result(
            url,
            error_message=f"static-fetch: {type(e).__name__}: {e}",
        )

    elapsed_ms = int((time.time() - t0) * 1000)
    final_url = str(resp.url)
    status_code = resp.status_code
    success = 200 <= status_code < 400

    try:
        body = resp.text
    except Exception as e:
        logger.warning(f"[static] body decode failed for {url}: {e}")
        body = ""

    cleaned_body = _strip_hidden_decoys(body) if body else body

    try:
        h = HTML2Text(baseurl=final_url)
        h.body_width = 0  # no hard-wrap; preserve paragraphs for downstream LLMs
        h.ignore_images = True  # MAS doesn't use images in static mode
        markdown = h.handle(cleaned_body)
    except Exception as e:
        # html2text has parser edge cases; fall back to raw HTML rather than
        # failing the request — MAS can still strip tags on its end.
        logger.warning(
            f"[static] html2text failed for {url}: {e}; returning raw HTML as markdown"
        )
        markdown = cleaned_body or body

    logger.info(
        f"[static] {status_code} {final_url} "
        f"({len(body)}B html, {len(markdown)}B md, {elapsed_ms}ms)"
    )

    return {
        "url": final_url,
        "success": success,
        "status_code": status_code,
        "error_message": None if success else f"HTTP {status_code}",
        "render_mode": "static",
        "markdown": {"raw_markdown": markdown, "fit_markdown": ""},
        "links": {"internal": [], "external": []},
    }


async def handle_static_crawl_request(urls: List[str]) -> dict:
    """Static-mode handler: httpx + html2text, no Playwright.

    Returns the same top-level envelope shape as ``handle_crawl_request`` so
    MAS's client code can treat full and static responses uniformly.
    """
    start_mem_mb = _get_memory_mb()
    start_time = time.time()

    # Bound the fan-out: without this a 100-URL request opens 100 concurrent
    # fetches on a 2 vCPU replica.
    sem = asyncio.Semaphore(STATIC_FETCH_MAX_CONCURRENCY)

    async def _bounded(u: str) -> dict:
        async with sem:
            return await _fetch_static_one(u)

    results = await asyncio.gather(*(_bounded(u) for u in urls))

    end_time = time.time()
    end_mem_mb = _get_memory_mb()

    mem_delta_mb = None
    if start_mem_mb is not None and end_mem_mb is not None:
        mem_delta_mb = end_mem_mb - start_mem_mb

    logger.info(
        f"[static] batch done: {len(urls)} url(s) in "
        f"{end_time - start_time:.2f}s, mem Δ {mem_delta_mb}MB"
    )

    return {
        "success": True,
        "results": list(results),
        "server_processing_time_s": end_time - start_time,
        "server_memory_delta_mb": mem_delta_mb,
        "server_peak_memory_mb": end_mem_mb,
    }
