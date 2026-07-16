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

logger = logging.getLogger(__name__)

# Per-URL HTTP timeout. Separate from limits.wall_clock_s because static
# fetches should be fast or fail fast — the whole point of static mode is a
# cheap alternative to Playwright.
STATIC_FETCH_TIMEOUT_S = 15

_static_http_client: Optional[httpx.AsyncClient] = None
_static_http_client_lock = asyncio.Lock()
_STATIC_USER_AGENT_FALLBACK = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)
_static_user_agent_cached: Optional[str] = None


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
                    timeout=httpx.Timeout(STATIC_FETCH_TIMEOUT_S),
                    verify=False,  # match --ignore-certificate-errors in config.yml
                    follow_redirects=True,
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
    caller can gather() without `return_exceptions=True`."""
    from crawl4ai.html2text import HTML2Text

    client = await _get_static_http_client()
    t0 = time.time()
    try:
        resp = await client.get(url)
    except httpx.TimeoutException:
        logger.info(f"[static] timeout after {STATIC_FETCH_TIMEOUT_S}s: {url}")
        return _static_error_result(
            url,
            error_message=f"static-fetch: timeout after {STATIC_FETCH_TIMEOUT_S}s",
        )
    except httpx.RequestError as e:
        logger.info(f"[static] request error: {url} {type(e).__name__}: {e}")
        return _static_error_result(
            url,
            error_message=f"static-fetch: {type(e).__name__}: {e}",
        )
    except Exception as e:
        logger.error(f"[static] unexpected error: {url} {e}", exc_info=True)
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


async def handle_static_crawl_request(
    urls: List[str],
    config: dict,
) -> dict:
    """Static-mode handler: httpx + html2text, no Playwright.

    Returns the same top-level envelope shape as ``handle_crawl_request`` so
    MAS's client code can treat full and static responses uniformly.
    """
    start_mem_mb = _get_memory_mb()
    start_time = time.time()

    results = await asyncio.gather(*(_fetch_static_one(u) for u in urls))

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
