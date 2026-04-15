# crawler_pool.py - Smart browser pool with tiered management
import asyncio, json, hashlib, time
from contextlib import suppress
from typing import Dict, Optional
from crawl4ai import AsyncWebCrawler, BrowserConfig
from utils import load_config, get_container_memory_percent
import logging

logger = logging.getLogger(__name__)
CONFIG = load_config()

# Pool tiers
PERMANENT: Optional[AsyncWebCrawler] = None  # Always-ready default browser
HOT_POOL: Dict[str, AsyncWebCrawler] = {}  # Frequent configs
COLD_POOL: Dict[str, AsyncWebCrawler] = {}  # Rare configs
LAST_USED: Dict[str, float] = {}
USAGE_COUNT: Dict[str, int] = {}
OVERFLOW_SEQ = 0  # Counter for unique overflow keys
LOCK = asyncio.Lock()

# Config
MEM_LIMIT = CONFIG.get("crawler", {}).get("memory_threshold_percent", 95.0)
BASE_IDLE_TTL = CONFIG.get("crawler", {}).get("pool", {}).get("idle_ttl_sec", 300)
MAX_PAGES = CONFIG.get("crawler", {}).get("pool", {}).get("max_pages", 5)
DEFAULT_CONFIG_SIG = None  # Cached sig for default config

# Aitosoft: force-close browsers that have been stuck busy for too long.
# If active_requests has stayed > 0 for longer than this, the in-flight pages
# are almost certainly leaked (e.g. upstream timed out at Azure ingress but
# the backend coroutine is still hanging) and the slot will never be released.
# Fix 1 (asyncio.wait_for in api.py) is the primary defense; this is the
# safety net for code paths Fix 1 doesn't cover or future regressions.
STUCK_BUSY_TIMEOUT_S = (
    CONFIG.get("crawler", {}).get("pool", {}).get("stuck_busy_timeout_sec", 600)
)

# Tracks when each crawler FIRST went from active_requests=0 → 1. Cleared when
# active_requests returns to 0 via release_crawler. Keyed by id(crawler) because
# release_crawler only has the object reference, not the pool key.
BUSY_SINCE: Dict[int, float] = {}


def get_pool_snapshot() -> dict:
    """Return a point-in-time snapshot of pool state for monitoring.

    This is intentionally lock-free. Under CPython's GIL, reading
    ``len(dict)``, ``dict.copy()``, and ``x is not None`` are atomic
    operations, so the monitor can safely call this without contending
    on the pool LOCK that is held during slow browser start/close ops.
    The worst case is a slightly stale count, which is acceptable for
    dashboard display purposes.
    """
    return {
        "permanent": PERMANENT,
        "permanent_sig": DEFAULT_CONFIG_SIG,
        "hot_pool": HOT_POOL.copy(),
        "cold_pool": COLD_POOL.copy(),
        "last_used": LAST_USED.copy(),
        "usage_count": USAGE_COUNT.copy(),
    }


def _sig(cfg: BrowserConfig) -> str:
    """Generate config signature."""
    payload = json.dumps(cfg.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode()).hexdigest()


def _is_default_config(sig: str) -> bool:
    """Check if config matches default."""
    return sig == DEFAULT_CONFIG_SIG


def _active(crawler: AsyncWebCrawler) -> int:
    return getattr(crawler, "active_requests", 0)


def _incr_active(crawler: AsyncWebCrawler) -> int:
    """Atomically increment active_requests.

    Records `BUSY_SINCE[id(crawler)]` on the 0→1 transition so the janitor can
    detect stuck slots (see force-close logic). Callers MUST already hold
    the pool LOCK.
    """
    if not hasattr(crawler, "active_requests"):
        crawler.active_requests = 0
    crawler.active_requests += 1
    if crawler.active_requests == 1:
        BUSY_SINCE[id(crawler)] = time.time()
    return crawler.active_requests


async def get_crawler(cfg: BrowserConfig) -> AsyncWebCrawler:
    """Get crawler from pool with tiered strategy.

    Enforces MAX_PAGES per browser to prevent cascading page starvation.
    When a pooled browser is at capacity, falls through to create a new one.
    """
    sig = _sig(cfg)
    async with LOCK:
        # Check permanent browser for default config
        if PERMANENT and _is_default_config(sig):
            if _active(PERMANENT) >= MAX_PAGES:
                logger.warning(
                    f"⚠️  Permanent browser at capacity "
                    f"({_active(PERMANENT)}/{MAX_PAGES})"
                )
            else:
                LAST_USED[sig] = time.time()
                USAGE_COUNT[sig] = USAGE_COUNT.get(sig, 0) + 1
                _incr_active(PERMANENT)
                logger.info("🔥 Using permanent browser")
                return PERMANENT

        # Check hot pool
        if sig in HOT_POOL:
            crawler = HOT_POOL[sig]
            if _active(crawler) >= MAX_PAGES:
                logger.warning(
                    f"⚠️  Hot browser at capacity "
                    f"(sig={sig[:8]}, "
                    f"{_active(crawler)}/{MAX_PAGES})"
                )
            else:
                LAST_USED[sig] = time.time()
                USAGE_COUNT[sig] = USAGE_COUNT.get(sig, 0) + 1
                _incr_active(crawler)
                logger.info(
                    f"♨️  Using hot pool browser "
                    f"(sig={sig[:8]}, "
                    f"active={crawler.active_requests})"
                )
                return crawler

        # Check cold pool (promote to hot if used 3+ times)
        if sig in COLD_POOL:
            crawler = COLD_POOL[sig]
            if _active(crawler) >= MAX_PAGES:
                logger.warning(
                    f"⚠️  Cold browser at capacity "
                    f"(sig={sig[:8]}, "
                    f"{_active(crawler)}/{MAX_PAGES})"
                )
            else:
                LAST_USED[sig] = time.time()
                USAGE_COUNT[sig] = USAGE_COUNT.get(sig, 0) + 1
                _incr_active(crawler)

                if USAGE_COUNT[sig] >= 3:
                    logger.info(
                        f"⬆️  Promoting to hot pool "
                        f"(sig={sig[:8]}, "
                        f"count={USAGE_COUNT[sig]})"
                    )
                    HOT_POOL[sig] = COLD_POOL.pop(sig)

                    # Track promotion in monitor
                    try:
                        from monitor import get_monitor

                        await get_monitor().track_janitor_event(
                            "promote", sig, {"count": USAGE_COUNT[sig]}
                        )
                    except:
                        pass

                    return HOT_POOL[sig]

                logger.info(f"❄️  Using cold pool browser (sig={sig[:8]})")
                return crawler

        # Check overflow browsers in hot/cold pools (keyed as sig_ovf_N)
        for pool in (HOT_POOL, COLD_POOL):
            for key, crawler in pool.items():
                if key.startswith(sig + "_ovf_") and _active(crawler) < MAX_PAGES:
                    LAST_USED[key] = time.time()
                    USAGE_COUNT[key] = USAGE_COUNT.get(key, 0) + 1
                    _incr_active(crawler)
                    pool_name = "hot" if pool is HOT_POOL else "cold"
                    logger.info(
                        f"♻️  Using overflow {pool_name} "
                        f"browser (key={key[:16]}, "
                        f"active={crawler.active_requests})"
                    )
                    return crawler

        # Memory check before creating new
        mem_pct = get_container_memory_percent()
        if mem_pct >= MEM_LIMIT:
            logger.error(f"💥 Memory pressure: {mem_pct:.1f}% >= {MEM_LIMIT}%")
            raise MemoryError(f"Memory at {mem_pct:.1f}%, refusing new browser")

        # Create new browser (either no match in pool, or existing ones at capacity)
        global OVERFLOW_SEQ
        if sig in COLD_POOL or sig in HOT_POOL or _is_default_config(sig):
            # Same sig already in pool — use overflow key
            OVERFLOW_SEQ += 1
            pool_key = f"{sig}_ovf_{OVERFLOW_SEQ}"
        else:
            pool_key = sig

        logger.info(
            f"🆕 Creating new browser in cold pool "
            f"(sig={sig[:8]}, key={pool_key[:16]}, "
            f"mem={mem_pct:.1f}%)"
        )
        crawler = AsyncWebCrawler(config=cfg, thread_safe=False)
        await crawler.start()
        crawler.active_requests = 0
        _incr_active(crawler)  # becomes 1, records BUSY_SINCE
        COLD_POOL[pool_key] = crawler
        LAST_USED[pool_key] = time.time()
        USAGE_COUNT[pool_key] = 1
        return crawler


async def release_crawler(crawler: AsyncWebCrawler):
    """Decrement active request count for a pooled crawler.

    Call this in a finally block after finishing work with a crawler
    obtained via get_crawler() so the janitor knows when it's safe
    to close idle browsers.
    """
    async with LOCK:
        if hasattr(crawler, "active_requests"):
            crawler.active_requests = max(0, crawler.active_requests - 1)
            if crawler.active_requests == 0:
                # Slot freed — clear the stuck-detection timestamp so the
                # janitor doesn't flag this crawler as stuck after legitimate
                # idle reuse.
                BUSY_SINCE.pop(id(crawler), None)


async def init_permanent(cfg: BrowserConfig):
    """Initialize permanent default browser."""
    global PERMANENT, DEFAULT_CONFIG_SIG
    async with LOCK:
        if PERMANENT:
            return
        DEFAULT_CONFIG_SIG = _sig(cfg)
        logger.info("🔥 Creating permanent default browser")
        PERMANENT = AsyncWebCrawler(config=cfg, thread_safe=False)
        await PERMANENT.start()
        LAST_USED[DEFAULT_CONFIG_SIG] = time.time()
        USAGE_COUNT[DEFAULT_CONFIG_SIG] = 0


async def close_all():
    """Close all browsers."""
    async with LOCK:
        tasks = []
        if PERMANENT:
            tasks.append(PERMANENT.close())
        tasks.extend([c.close() for c in HOT_POOL.values()])
        tasks.extend([c.close() for c in COLD_POOL.values()])
        await asyncio.gather(*tasks, return_exceptions=True)
        HOT_POOL.clear()
        COLD_POOL.clear()
        LAST_USED.clear()
        USAGE_COUNT.clear()
        BUSY_SINCE.clear()


async def _force_close_stuck(now: float) -> None:
    """Force-close pool browsers whose active_requests has been > 0 too long.

    Caller MUST hold LOCK. Scans permanent + hot + cold. Any crawler whose
    id() has been in BUSY_SINCE for > STUCK_BUSY_TIMEOUT_S is treated as
    having leaked slots and is closed + removed. Logs a prominent WARNING
    with diagnostic context so ops can see when this fires in production.
    """
    global PERMANENT

    def _check(crawler: "AsyncWebCrawler") -> Optional[float]:
        """Return busy_seconds if stuck past threshold, else None."""
        if crawler is None:
            return None
        active = getattr(crawler, "active_requests", 0)
        if active <= 0:
            return None
        busy_start = BUSY_SINCE.get(id(crawler))
        if busy_start is None:
            # Recover: stamp now so next tick can evaluate. Handles the case
            # where a crawler was somehow incremented without going through
            # _incr_active.
            BUSY_SINCE[id(crawler)] = now
            return None
        busy_for = now - busy_start
        if busy_for <= STUCK_BUSY_TIMEOUT_S:
            return None
        return busy_for

    async def _log_and_close(
        pool_name: str, key: str, crawler: "AsyncWebCrawler", busy_for: float
    ) -> None:
        active = getattr(crawler, "active_requests", 0)
        logger.warning(
            f"🚨 FORCE-CLOSING stuck browser "
            f"(pool={pool_name}, key={key[:16]}, "
            f"active={active}, busy_for={busy_for:.0f}s, "
            f"limit={STUCK_BUSY_TIMEOUT_S}s). "
            f"This indicates a leaked request slot — investigate logs "
            f"around busy-start time for matching request_id."
        )
        with suppress(Exception):
            await crawler.close()
        BUSY_SINCE.pop(id(crawler), None)
        try:
            from monitor import get_monitor

            await get_monitor().track_janitor_event(
                f"force_close_{pool_name}",
                key,
                {"active_requests": active, "busy_seconds": int(busy_for)},
            )
        except Exception:
            pass

    # Permanent browser
    if PERMANENT is not None:
        busy_for = _check(PERMANENT)
        if busy_for is not None:
            await _log_and_close(
                "permanent", DEFAULT_CONFIG_SIG or "permanent", PERMANENT, busy_for
            )
            PERMANENT = None
            if DEFAULT_CONFIG_SIG:
                LAST_USED.pop(DEFAULT_CONFIG_SIG, None)
                USAGE_COUNT.pop(DEFAULT_CONFIG_SIG, None)

    # Hot + cold pools
    for pool_name, pool in (("hot", HOT_POOL), ("cold", COLD_POOL)):
        for key in list(pool.keys()):
            crawler = pool.get(key)
            busy_for = _check(crawler)
            if busy_for is None:
                continue
            await _log_and_close(pool_name, key, crawler, busy_for)
            pool.pop(key, None)
            LAST_USED.pop(key, None)
            USAGE_COUNT.pop(key, None)


async def janitor():
    """Adaptive cleanup based on memory pressure."""
    while True:
        mem_pct = get_container_memory_percent()

        # Adaptive intervals and TTLs
        if mem_pct > 80:
            interval, cold_ttl, hot_ttl = 10, 30, 120
        elif mem_pct > 60:
            interval, cold_ttl, hot_ttl = 30, 60, 300
        else:
            interval, cold_ttl, hot_ttl = 60, BASE_IDLE_TTL, BASE_IDLE_TTL * 2

        await asyncio.sleep(interval)

        now = time.time()
        async with LOCK:
            # Clean cold pool
            for sig in list(COLD_POOL.keys()):
                if now - LAST_USED.get(sig, now) > cold_ttl:
                    crawler = COLD_POOL[sig]
                    if getattr(crawler, "active_requests", 0) > 0:
                        continue  # still serving requests, skip
                    idle_time = now - LAST_USED[sig]
                    logger.info(
                        f"🧹 Closing cold browser (sig={sig[:8]}, idle={idle_time:.0f}s)"
                    )
                    with suppress(Exception):
                        await crawler.close()
                    COLD_POOL.pop(sig, None)
                    LAST_USED.pop(sig, None)
                    USAGE_COUNT.pop(sig, None)

                    # Track in monitor
                    try:
                        from monitor import get_monitor

                        await get_monitor().track_janitor_event(
                            "close_cold",
                            sig,
                            {"idle_seconds": int(idle_time), "ttl": cold_ttl},
                        )
                    except:
                        pass

            # Clean hot pool (more conservative)
            for sig in list(HOT_POOL.keys()):
                if now - LAST_USED.get(sig, now) > hot_ttl:
                    crawler = HOT_POOL[sig]
                    if getattr(crawler, "active_requests", 0) > 0:
                        continue  # still serving requests, skip
                    idle_time = now - LAST_USED[sig]
                    logger.info(
                        f"🧹 Closing hot browser (sig={sig[:8]}, idle={idle_time:.0f}s)"
                    )
                    with suppress(Exception):
                        await crawler.close()
                    HOT_POOL.pop(sig, None)
                    LAST_USED.pop(sig, None)
                    USAGE_COUNT.pop(sig, None)

                    # Track in monitor
                    try:
                        from monitor import get_monitor

                        await get_monitor().track_janitor_event(
                            "close_hot",
                            sig,
                            {"idle_seconds": int(idle_time), "ttl": hot_ttl},
                        )
                    except:
                        pass

            # Aitosoft: force-close browsers whose active_requests has been > 0
            # for longer than STUCK_BUSY_TIMEOUT_S. This catches leaked slots
            # that escape Fix 1 (asyncio.wait_for in api.py) — e.g. future code
            # paths that bypass the timeout wrapper, or bugs in release_crawler.
            # Without this safety net, a stuck slot wedges the pool forever
            # because regular idle cleanup skips anything with active > 0.
            await _force_close_stuck(now)

            # Log pool stats
            if mem_pct > 60:
                logger.info(
                    f"📊 Pool: hot={len(HOT_POOL)}, cold={len(COLD_POOL)}, mem={mem_pct:.1f}%"
                )
