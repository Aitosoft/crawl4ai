"""
Aitosoft: patchright (undetected-chromium) fallback for blocked crawls.

Second-tier retry. When the regular stealth-enabled crawl returns a result
marked as blocked by anti-bot protection, retry the same URL once through
a patchright-backed crawler. Patchright is a maintained fork of Playwright
that uses undetected-chromium under the hood — different from the
stealth-patched Playwright path, so it can get through cases where
stealth alone isn't enough (specifically Cloudflare JS challenges that
spin forever, and some WAFs that sniff Playwright-specific quirks beyond
what playwright-stealth can hide).

Design:
- Lazy singleton crawler. Patchright startup is slow (~3-5s). We create one
  shared instance on first use and reuse it across retries. It's fine for
  concurrent retries as long as the stealth path handles the normal load.
- Stealth adapter is NOT used on top of patchright (they conflict — see
  browser_manager.py:787: `not self.use_undetected`). Patchright's own
  stealth is sufficient.
- The retry only fires when `error_message` starts with "Blocked by anti-bot
  protection:" — i.e. the signal antibot_detector writes in async_webcrawler.
- If the retry still fails (either block or error), we keep the ORIGINAL
  blocked result so the caller sees the first-attempt diagnostic, not a
  duplicated "both failed" message.

This file is Aitosoft-only. It is imported from api.py after the first-tier
crawl completes. It does NOT modify crawl4ai core.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    UndetectedAdapter,
)
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy

logger = logging.getLogger(__name__)

_UNDETECTED_CRAWLER: Optional[AsyncWebCrawler] = None
_UNDETECTED_LOCK = asyncio.Lock()

# Aitosoft: bound concurrent arun() calls on the patchright singleton.
# Without this, 10+ parallel agents all hitting a blocked site can pile
# 10+ Playwright pages onto the same Chromium process, leaking memory
# on timeout (Playwright pages don't always GC cleanly when their
# outer coroutine is cancelled). MAX matches crawler_pool's MAX_PAGES
# for symmetry; each of the 5 slots maps to one live page on the
# singleton at peak.
_UNDETECTED_CONCURRENCY = 5
_UNDETECTED_SEM = asyncio.Semaphore(_UNDETECTED_CONCURRENCY)

# Aitosoft: recycle the singleton periodically to bound long-run memory
# growth. Even if every arun frees its page cleanly, long-running Chromium
# processes accumulate cruft (cookies, caches, in-progress fetches from
# cancelled requests). We close + recreate after N successful + failed
# calls. Guarded by _UNDETECTED_LOCK on the swap so no in-flight call
# sees a half-closed crawler.
_UNDETECTED_RECYCLE_USES = 100
_UNDETECTED_USES = 0

_BLOCK_MARKER = "Blocked by anti-bot protection:"


def _is_blocked(result: Any) -> bool:
    """Return True if this result was flagged as blocked by antibot_detector."""
    if result is None:
        return False
    success = getattr(result, "success", None)
    if success is None and isinstance(result, dict):
        success = result.get("success")
    if success:
        return False
    err = getattr(result, "error_message", None)
    if err is None and isinstance(result, dict):
        err = result.get("error_message")
    return isinstance(err, str) and _BLOCK_MARKER in err


async def _get_undetected_crawler(base_cfg: BrowserConfig) -> AsyncWebCrawler:
    """Return (lazy-creating) a shared patchright-backed crawler.

    The base_cfg is the same BrowserConfig we'd normally use — we strip
    enable_stealth because patchright handles stealth natively and the two
    conflict in crawl4ai's BrowserManager initialization.
    """
    global _UNDETECTED_CRAWLER
    async with _UNDETECTED_LOCK:
        if _UNDETECTED_CRAWLER is not None:
            return _UNDETECTED_CRAWLER

        # Build a patchright-safe BrowserConfig: disable stealth, keep
        # everything else from the first-tier config (UA, viewport, args).
        cfg_dict = base_cfg.to_dict()
        cfg_dict["enable_stealth"] = False
        # chrome_channel=chrome is fine for patchright too — patchright is a
        # Playwright fork that still accepts `channel` on launch.
        patchright_cfg = BrowserConfig.load(cfg_dict)

        strategy = AsyncPlaywrightCrawlerStrategy(
            browser_config=patchright_cfg,
            browser_adapter=UndetectedAdapter(),
        )
        crawler = AsyncWebCrawler(
            crawler_strategy=strategy,
            thread_safe=False,
        )
        logger.info("[patchright] Starting singleton undetected crawler (first use)")
        await crawler.start()
        _UNDETECTED_CRAWLER = crawler
        return crawler


async def maybe_retry_blocked(
    results: List[Any],
    urls: List[str],
    crawler_config: CrawlerRunConfig,
    base_browser_config: BrowserConfig,
) -> List[Any]:
    """Retry any blocked results through patchright. Returns the updated list.

    Args:
        results: Per-URL result list from the first-tier crawl. May contain
                 blocked (success=False, antibot error_message) entries.
        urls:    The URLs in the same order as results. Used to look up which
                 URL to retry for each blocked index.
        crawler_config: The same CrawlerRunConfig the first-tier crawl used.
                 Reused as-is — patchright uses the same per-crawl config.
        base_browser_config: The first-tier BrowserConfig (already merged with
                 config.yml). Patchright strips enable_stealth from it.

    Returns:
        The list, with blocked entries replaced by patchright results IF
        the patchright retry succeeded. If patchright still blocks or errors,
        the original entry is preserved so the caller sees the first-tier
        diagnostic (which is what MAS branches on).
    """
    blocked_indices = [i for i, r in enumerate(results) if _is_blocked(r)]
    if not blocked_indices:
        return results

    logger.info(
        f"[patchright] {len(blocked_indices)}/{len(results)} "
        f"result(s) blocked, retrying"
    )

    try:
        undetected = await _get_undetected_crawler(base_browser_config)
    except Exception as e:
        logger.warning(f"[patchright] crawler startup failed: {e}")
        return results

    global _UNDETECTED_USES

    for i in blocked_indices:
        url = urls[i] if i < len(urls) else None
        if not url:
            continue
        try:
            # Aitosoft: concurrency cap prevents runaway page count on the
            # shared singleton under parallel-agent load. Waiters queue here;
            # each retry is short (~5-10s normally, bounded by api.py's
            # asyncio.wait_for(180s)).
            async with _UNDETECTED_SEM:
                raw: Any = await undetected.arun(url=url, config=crawler_config)
            _UNDETECTED_USES += 1
            new_result: Any
            if isinstance(raw, list):
                new_result = raw[0] if raw else None
            else:
                new_result = raw
            if new_result is None:
                logger.warning(f"[patchright] {url}: empty result")
                continue
            if _is_blocked(new_result):
                logger.info(
                    f"[patchright] {url}: STILL blocked "
                    f"({getattr(new_result, 'error_message', '')[:120]})"
                )
                # Keep the original (first-tier) result so caller sees the
                # primary diagnostic. Optional: we could merge the two.
                continue
            if not getattr(new_result, "success", False):
                logger.info(
                    f"[patchright] {url}: retry failed "
                    f"({getattr(new_result, 'error_message', '')[:120]})"
                )
                continue
            logger.info(f"[patchright] {url}: UNBLOCKED on retry")
            results[i] = new_result
        except Exception as e:
            logger.warning(f"[patchright] {url}: retry raised {type(e).__name__}: {e}")
            continue

    # Aitosoft: periodic recycle. When usage hits the threshold and no
    # calls are in flight (semaphore fully released), swap the singleton.
    # Triggered opportunistically from the same coroutine that just hit
    # the threshold; under parallel load the swap may be deferred until a
    # quiet moment, which is fine — the point is eventual bounded growth.
    if _UNDETECTED_USES >= _UNDETECTED_RECYCLE_USES:
        try:
            await _recycle_undetected()
        except Exception as e:
            logger.warning(f"[patchright] recycle failed (non-fatal): {e}")

    return results


async def _recycle_undetected() -> None:
    """Close + clear the singleton so the next call builds a fresh one.

    Only runs if we can grab _UNDETECTED_LOCK AND the concurrency semaphore
    shows zero in-flight callers. Avoids closing a crawler that another
    coroutine is mid-arun on. Under sustained parallel load this may wait
    for a gap before recycling, which is acceptable — we want bounded
    long-term growth, not strict periodicity.
    """
    global _UNDETECTED_CRAWLER, _UNDETECTED_USES
    # Cheap check before acquiring the lock — if fully busy, skip this round.
    if _UNDETECTED_SEM._value < _UNDETECTED_CONCURRENCY:
        return
    async with _UNDETECTED_LOCK:
        if _UNDETECTED_CRAWLER is None:
            _UNDETECTED_USES = 0
            return
        if _UNDETECTED_SEM._value < _UNDETECTED_CONCURRENCY:
            return
        logger.info(f"[patchright] Recycling singleton after {_UNDETECTED_USES} uses")
        old = _UNDETECTED_CRAWLER
        _UNDETECTED_CRAWLER = None
        _UNDETECTED_USES = 0
    # Close outside the lock so a concurrent _get_undetected_crawler caller
    # can immediately start building the replacement without waiting on
    # Chromium shutdown (~1-2s).
    try:
        await old.close()
    except Exception as e:
        logger.warning(f"[patchright] close during recycle failed: {e}")


async def close_patchright_crawler() -> None:
    """Close the singleton on shutdown. Called from server lifespan."""
    global _UNDETECTED_CRAWLER
    async with _UNDETECTED_LOCK:
        if _UNDETECTED_CRAWLER is not None:
            try:
                await _UNDETECTED_CRAWLER.close()
            except Exception as e:
                logger.warning(f"[patchright] shutdown close failed: {e}")
            _UNDETECTED_CRAWLER = None
