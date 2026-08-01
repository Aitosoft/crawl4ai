# crawler_pool.py - Smart browser pool with tiered management
import asyncio, json, hashlib, time
from contextlib import suppress
from typing import Dict, Optional
from crawl4ai import AsyncWebCrawler, BrowserConfig
from utils import load_config, get_container_memory_percent, get_memory_breakdown
import logging

logger = logging.getLogger(__name__)
CONFIG = load_config()

# Pool tiers
PERMANENT: Optional[AsyncWebCrawler] = None  # Always-ready default browser
HOT_POOL: Dict[str, AsyncWebCrawler] = {}    # Frequent configs
COLD_POOL: Dict[str, AsyncWebCrawler] = {}   # Rare configs
LAST_USED: Dict[str, float] = {}
USAGE_COUNT: Dict[str, int] = {}
OVERFLOW_SEQ = 0  # Counter for unique overflow keys
LOCK = asyncio.Lock()

# Config
MEM_LIMIT = CONFIG.get("crawler", {}).get("memory_threshold_percent", 95.0)
BASE_IDLE_TTL = CONFIG.get("crawler", {}).get("pool", {}).get("idle_ttl_sec", 300)
MAX_PAGES = CONFIG.get("crawler", {}).get("pool", {}).get("max_pages", 5)
DEFAULT_CONFIG_SIG = None  # Cached sig for default config

# Aitosoft 2026-08-02 (tasks/pool-residency-unbounded.md): the number of live
# pool browsers, which nothing bounded before. `render_capacity` bounds
# concurrent renders and `max_pages` bounds pages per browser; residency was
# governed by idle TTL alone, so the browser count tracked *distinct configs
# seen in the last TTL window* rather than concurrency.
#
# Read as a module global on every call so tests can monkeypatch it — do NOT
# capture it into a default argument or a local at import.
MAX_BROWSERS = CONFIG.get("crawler", {}).get("pool", {}).get("max_browsers", 6)

# How long to let an evicted browser's close() run before giving up on it. The
# close happens OFF the pool lock (see _close_detached), so this bounds a
# background task, never the admission path.
EVICT_CLOSE_TIMEOUT_S = (
    CONFIG.get("crawler", {}).get("pool", {}).get("evict_close_timeout_sec", 30)
)

# Strong references to in-flight detached closes. Without this the task is only
# referenced by the event loop and CPython may collect it mid-close.
_CLOSING: set = set()

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

# Aitosoft 2026-08-01: how long the permanent browser may sit unused before the
# janitor closes it. `Using permanent browser` fired **0 times in 224 pool gets**
# during MAS's 2026-07-31 probe, while the boot browser held ~139-165 MB for the
# replica's whole life. `get_crawler` already lazily re-creates it, so closing it
# is free to be wrong.
#
# **The reason recorded here was wrong** (corrected 2026-08-02). It said "because
# they always send a browser_config". They do, but that is not why: `server.py`
# builds this browser's config WITHOUT `enforce_egress`, which every request path
# applies, and `enforce_egress` flips `ignore_https_errors` True -> False. The
# signatures therefore differ in a field no client controls:
#     boot sig 5e3e8048e7be  vs  request sig b318c5753575
# So a request sending `browser_config: {}` misses too, as does every internal
# /html, /screenshot and /pdf call. The permanent browser is unreachable **by
# construction**, this TTL always fires, and the lazy re-create branch in
# get_crawler is dead code in production. Left as-is deliberately: "fixing" it
# would revive a browser nothing wants.
PERMANENT_UNUSED_TTL_S = (
    CONFIG.get("crawler", {}).get("pool", {}).get("permanent_unused_ttl_sec", 600)
)


def memory_breakdown() -> str:
    """One-line anon/file/inactive_file split for a log message.

    Aitosoft: this question — "is the memory pressure real, or is the reading
    counting page cache?" — cost an offline probe and a session to answer once.
    Logging the split makes it answerable from Log Analytics forever.
    """
    parts = get_memory_breakdown()
    if not parts:
        return "cgroup stats unavailable"
    return (
        f"anon={parts['anon']:.0f}MB file={parts['file']:.0f}MB "
        f"inactive_file={parts['inactive_file']:.0f}MB"
    )


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
    payload = json.dumps(cfg.to_dict(), sort_keys=True, separators=(",",":"))
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

def resident_browsers() -> int:
    """Live browsers this pool is holding, counting the permanent one.

    Counts POOL KEYS, not signatures. `_ovf_` keys are separate live browsers
    under the same signature, so a signature-based count understates residency
    by exactly the amount that matters under concurrency.
    """
    return len(HOT_POOL) + len(COLD_POOL) + (1 if PERMANENT else 0)


def _lru_idle_key() -> Optional[str]:
    """The least-recently-used pool key with no pages in flight, or None.

    `active_requests > 0` is the eviction veto and it is absolute: a browser
    serving a request is never a candidate, which is what makes this safe to
    run on the admission path. The stuck-slot case (a browser whose
    `active_requests` never comes back down) belongs to `_force_close_stuck`
    and is deliberately NOT duplicated here — two mechanisms force-closing the
    same browser is how a double-close race gets written.

    PERMANENT is never a candidate: `_close_unused_permanent` owns its
    lifecycle, and it is not in either pool dict anyway.
    """
    best_key, best_used = None, None
    for pool in (COLD_POOL, HOT_POOL):
        for key, crawler in pool.items():
            if _active(crawler) > 0:
                continue
            used = LAST_USED.get(key, 0.0)
            if best_used is None or used < best_used:
                best_key, best_used = key, used
    return best_key


def _close_detached(crawler: AsyncWebCrawler, key: str, reason: str) -> None:
    """Close a browser that has ALREADY been removed from the pool, off-lock.

    Why not `await crawler.close()` inline: this runs from `get_crawler`, which
    holds LOCK, and `close()` carries no timeout of its own — a wedged Chromium
    would hold the pool lock indefinitely, and `release_crawler` needs that same
    lock to bring `active_requests` back down. That is a total-pool deadlock
    reachable from the admission path of every render, which is strictly worse
    than the 429 this whole change exists to avoid. `tasks/render-retry-
    unbounded-hang.md` paid for this lesson once already.

    The browser is unreachable from the pool before this is called, so the task
    needs no lock and nothing waits on it.
    """

    async def _run() -> None:
        try:
            await asyncio.wait_for(crawler.close(), EVICT_CLOSE_TIMEOUT_S)
        except asyncio.TimeoutError:
            logger.warning(
                f"⏱️  Evicted browser did not close within "
                f"{EVICT_CLOSE_TIMEOUT_S}s (key={key[:16]}, {reason}) — "
                f"leaked to the OS; the pool no longer references it"
            )
        except Exception as exc:  # noqa: BLE001 - teardown must never propagate
            logger.warning(f"Evicted browser close failed (key={key[:16]}): {exc}")

    task = asyncio.create_task(_run())
    _CLOSING.add(task)
    task.add_done_callback(_CLOSING.discard)


def _evict_lru_idle(reason: str) -> Optional[str]:
    """Evict exactly one idle LRU browser. Returns its key, or None if none idle.

    Caller MUST hold LOCK. **Never awaits and never blocks** — that is the whole
    safety argument. If no idle browser exists it returns None and the caller
    decides; it does not wait for one to appear.

    The alternative design — wait for a browser to go idle — is what makes a
    capped pool deadlock. `release_crawler` takes the same LOCK to decrement
    `active_requests`, so waiting here while holding it means waiting for an
    event that can only be produced by code that needs the lock we are holding.
    Even releasing the lock to wait is unsafe on this path: `get_crawler` sits
    in the UNFENCED gap between render admission and the 180 s wall-clock fence
    (api.py acquires the gate, then gets a crawler, then starts the fence), and
    the budget from there to Azure ingress's 240 s is ~40 s, most of which a
    browser launch can already consume.
    """
    key = _lru_idle_key()
    if key is None:
        return None
    pool = HOT_POOL if key in HOT_POOL else COLD_POOL
    crawler = pool.pop(key, None)
    idle_for = time.time() - LAST_USED.get(key, time.time())
    LAST_USED.pop(key, None)
    USAGE_COUNT.pop(key, None)
    if crawler is None:  # defensive: _lru_idle_key only returns live pool keys
        return None
    BUSY_SINCE.pop(id(crawler), None)
    logger.info(
        f"♻️  Evicting LRU idle browser (key={key[:16]}, idle={idle_for:.0f}s, "
        f"resident={resident_browsers()}/{MAX_BROWSERS}, {reason})"
    )
    _close_detached(crawler, key, reason)
    return key


def _evict_for_capacity(headroom: int = 1) -> int:
    """Make room for `headroom` more browsers by evicting idle LRU ones.

    Caller MUST hold LOCK. Returns how many were evicted. Never awaits — see
    `_evict_lru_idle`, which carries the deadlock argument.
    """
    evicted = 0
    while resident_browsers() + headroom > MAX_BROWSERS:
        if _evict_lru_idle("max_browsers cap") is None:
            break
        evicted += 1
    return evicted


async def get_crawler(cfg: BrowserConfig) -> AsyncWebCrawler:
    """Get crawler from pool with tiered strategy.

    Enforces MAX_PAGES per browser to prevent cascading page starvation.
    When a pooled browser is at capacity, falls through to create a new one.
    """
    global PERMANENT
    sig = _sig(cfg)
    async with LOCK:
        # Aitosoft: lazily re-create the permanent browser if the stuck-slot
        # janitor force-closed it (_force_close_stuck sets PERMANENT = None).
        # Without this, one stuck slot would degrade all default-config
        # traffic to overflow cold browsers until the container restarts.
        # DEFAULT_CONFIG_SIG is only set by init_permanent, so this can never
        # fire before the first init.
        if PERMANENT is None and _is_default_config(sig):
            logger.warning("🔁 Re-creating permanent browser after force-close")
            crawler = AsyncWebCrawler(config=cfg, thread_safe=False)
            await crawler.start()
            PERMANENT = crawler
            LAST_USED[sig] = time.time()
            USAGE_COUNT[sig] = USAGE_COUNT.get(sig, 0) + 1
            _incr_active(PERMANENT)
            logger.info("🔥 Using permanent browser")
            return PERMANENT

        # Check permanent browser for default config
        if PERMANENT and _is_default_config(sig):
            if _active(PERMANENT) >= MAX_PAGES:
                logger.warning(f"⚠️  Permanent browser at capacity ({_active(PERMANENT)}/{MAX_PAGES})")
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
                logger.warning(f"⚠️  Hot browser at capacity (sig={sig[:8]}, {_active(crawler)}/{MAX_PAGES})")
            else:
                LAST_USED[sig] = time.time()
                USAGE_COUNT[sig] = USAGE_COUNT.get(sig, 0) + 1
                _incr_active(crawler)
                logger.info(f"♨️  Using hot pool browser (sig={sig[:8]}, active={crawler.active_requests})")
                return crawler

        # Check cold pool (promote to hot if used 3+ times)
        if sig in COLD_POOL:
            crawler = COLD_POOL[sig]
            if _active(crawler) >= MAX_PAGES:
                logger.warning(f"⚠️  Cold browser at capacity (sig={sig[:8]}, {_active(crawler)}/{MAX_PAGES})")
            else:
                LAST_USED[sig] = time.time()
                USAGE_COUNT[sig] = USAGE_COUNT.get(sig, 0) + 1
                _incr_active(crawler)

                if USAGE_COUNT[sig] >= 3:
                    logger.info(f"⬆️  Promoting to hot pool (sig={sig[:8]}, count={USAGE_COUNT[sig]})")
                    HOT_POOL[sig] = COLD_POOL.pop(sig)

                    # Track promotion in monitor
                    try:
                        from monitor import get_monitor
                        await get_monitor().track_janitor_event("promote", sig, {"count": USAGE_COUNT[sig]})
                    except:
                        pass

                    return HOT_POOL[sig]

                logger.info(f"❄️  Using cold pool browser (sig={sig[:8]})")
                return crawler

        # Check overflow browsers in the cold pool (keyed as sig_ovf_N).
        # Overflow keys live only in COLD_POOL: they are created there and
        # promotion only ever moves plain-sig keys to HOT_POOL.
        for key, crawler in COLD_POOL.items():
            if key.startswith(sig + "_ovf_") and _active(crawler) < MAX_PAGES:
                LAST_USED[key] = time.time()
                USAGE_COUNT[key] = USAGE_COUNT.get(key, 0) + 1
                _incr_active(crawler)
                logger.info(f"♻️  Using overflow cold browser (key={key[:16]}, active={crawler.active_requests})")
                return crawler

        # Memory check before creating new.
        #
        # Aitosoft 2026-08-01: this used to raise MemoryError, which api.py's
        # generic `except Exception` turned into a **500** with
        # `failure_class: render_error`. MAS retries 500 three times with
        # 1s/2s/4s backoff, so the service answered memory pressure by
        # multiplying its own load by four, at the exact moment capacity was
        # tightest. All nine 500s in their 2026-07-31 probe were this line.
        #
        # "We are full" already has a correct shape in this codebase: RenderGate
        # answers 429 + Retry-After, which MAS backs off on. Same condition,
        # same answer — so raise the same exception rather than inventing a
        # second vocabulary for it. See tasks/render-500-window-2026-07-31.md S1.
        #
        # This is a symptom fix and was labelled as one. **The cause it named
        # was wrong**, corrected 2026-08-02: residency being unbounded is real
        # (measured peak 9-10 browsers per replica, not the 8 the record said),
        # but how much of the pressure it explains is NOT settled — the
        # replacement regression is disputed on three counts in
        # tasks/replica-memory-baseline-unexplained.md ("Why the fit is not
        # settled"). Do not quote a per-browser cost or an intercept from any
        # file until it is re-derived. MAX_BROWSERS below bounds residency by
        # construction, which is correct under every candidate slope.
        #
        # SHED BEFORE REFUSING (2026-08-02). Removing the memory-adaptive TTL
        # was right — it thrashed, closing browsers exactly when memory was
        # tight so the next request had to launch one — but it took with it the
        # only path that shed under pressure. Without this line a replica over
        # the limit holds every idle browser for the full constant idle_ttl_sec
        # (300 s) while refusing every arrival. So each refusal now evicts the
        # single LRU *idle* browser first: pressure-proportional (it stops as
        # soon as arrivals stop being refused), LRU so the working set survives
        # longest, never touches a busy browser, and it launches nothing.
        #
        # It evicts ONE PER REFUSAL, and it refuses ANYWAY. Both halves are
        # deliberate, and the first is weaker than it sounds — say so plainly:
        #   - One per refusal is not "one per pressure episode". MAS's
        #     2026-07-31 replica refused nine times in ~4 minutes, which under
        #     this policy sheds up to nine browsers. The honest difference from
        #     the adaptive TTL is not "fewer" and not "idle-only" (the TTL
        #     skipped busy browsers too) — it is LRU order, that it engages only
        #     while arrivals are actually being refused, and that a refusal
        #     never launches anything. The TTL's defect was the relaunch it
        #     provoked, not the closing.
        #   - Refuse anyway, rather than re-read the meter and maybe proceed:
        #     _close_detached schedules the close on a background task that
        #     cannot start before this coroutine yields, and there is no await
        #     between here and a re-read — so it would measure the number it
        #     just read, exactly. Even forced to start, Chromium exit plus
        #     kernel reclaim is not synchronous, and sleeping for it would sit
        #     inside LOCK on the unfenced admission path. The reclaim is for
        #     the NEXT arrival, which the 429 + Retry-After exists to schedule.
        #
        # KNOWN COST, for whoever next regresses memory on browser count: this
        # is a feedback path from memory to browser count, which is the exact
        # confound that makes the 2026-07-31 slope unusable (see
        # tasks/replica-memory-baseline-unexplained.md §2 — the adaptive TTL
        # was one of these). It is narrower (it fires only on refusals, not on
        # a timer) and the eviction log line names `memory pressure X%` so those
        # samples can be excluded, but a naive fit across this build has the
        # same bias. Filter on the reason, or measure offline.
        mem_pct = get_container_memory_percent()
        if mem_pct >= MEM_LIMIT:
            from aitosoft_admission import RenderCapacityExceeded

            # Snapshot composition BEFORE shedding: this line is the one place
            # a memory reading is paired with a pool composition, and pairing
            # `mem_pct` with counts taken after an eviction would report one
            # browser fewer than the pool held when the reading was taken. That
            # is the same artefact class as the janitor's stale-`mem_pct`
            # caveat below, in the more-quoted line.
            hot_at_read, cold_at_read = len(HOT_POOL), len(COLD_POOL)
            perm_at_read = "yes" if PERMANENT else "no"
            shed = _evict_lru_idle(f"memory pressure {mem_pct:.1f}%")
            logger.error(
                f"💥 Memory pressure: {mem_pct:.1f}% >= {MEM_LIMIT}% "
                f"({memory_breakdown()}) — refusing new browser. "
                f"At the reading: hot={hot_at_read}, cold={cold_at_read}, "
                f"permanent={perm_at_read}; "
                f"shed={'1 idle browser' if shed else 'nothing idle to shed'}, "
                f"resident now {resident_browsers()}/{MAX_BROWSERS}"
            )
            raise RenderCapacityExceeded(
                f"memory at {mem_pct:.1f}% (limit {MEM_LIMIT}%), refusing new browser"
            )

        # Aitosoft 2026-08-02: bound residency by construction, not by a
        # threshold on a reading (tasks/pool-residency-unbounded.md).
        #
        # Evict LRU idle browsers to make room. If nothing is idle we refuse
        # rather than wait — see _evict_for_capacity for why waiting here is a
        # deadlock. Refusal reuses RenderCapacityExceeded because that is the
        # ONLY exception api.py maps to 429 + Retry-After; a new exception type
        # would fall into the generic `except Exception` and become the 500 MAS
        # retries three times, which is the regression this file already carries
        # a comment about above.
        #
        # In MAS's traffic this refusal is unreachable: the render gate admits
        # at most `render_capacity` (2) concurrent renders, each holding exactly
        # one pool browser, so at a cap of 6 there are always >= 3 idle
        # candidates. It is reachable only from the ungated endpoints (/md,
        # /html, /screenshot, /pdf, streaming), which MAS does not use.
        if resident_browsers() >= MAX_BROWSERS:
            _evict_for_capacity(headroom=1)
            if resident_browsers() >= MAX_BROWSERS:
                from aitosoft_admission import RenderCapacityExceeded

                busy = sum(
                    1
                    for c in list(HOT_POOL.values()) + list(COLD_POOL.values())
                    if _active(c) > 0
                )
                logger.error(
                    f"🚧 Browser cap reached and nothing is idle: "
                    f"resident={resident_browsers()}/{MAX_BROWSERS}, busy={busy}, "
                    f"hot={len(HOT_POOL)}, cold={len(COLD_POOL)} — refusing"
                )
                raise RenderCapacityExceeded(
                    f"browser pool at capacity ({resident_browsers()}/"
                    f"{MAX_BROWSERS}, {busy} busy), refusing new browser"
                )

        # Create new browser (either no match in pool, or existing ones at capacity)
        global OVERFLOW_SEQ
        if sig in COLD_POOL or sig in HOT_POOL or _is_default_config(sig):
            # Same sig already in pool — use overflow key
            OVERFLOW_SEQ += 1
            pool_key = f"{sig}_ovf_{OVERFLOW_SEQ}"
        else:
            pool_key = sig

        logger.info(f"🆕 Creating new browser in cold pool (sig={sig[:8]}, key={pool_key[:16]}, mem={mem_pct:.1f}%)")
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
        if hasattr(crawler, 'active_requests'):
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
    global OVERFLOW_SEQ
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
        OVERFLOW_SEQ = 0

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

        # Aitosoft 2026-08-02: the POLL RATE stays adaptive; the TTLs no longer
        # are (tasks/pool-residency-unbounded.md).
        #
        # This used to collapse cold_ttl to 30 s and hot_ttl to 120 s above 80 %
        # memory. That is the thrash engine: it closed browsers precisely when
        # memory was tight, and the next request for that same config had to
        # launch a fresh one — allocating while allocation was the problem. Over
        # MAS's 2026-07-31 probe it produced 136 launches for a working set of
        # 10-12 signatures per replica.
        #
        # `MAX_BROWSERS` now bounds residency by construction, so the TTL's only
        # remaining job is reclaiming genuinely idle browsers on a quiet replica
        # — which is a constant-time policy, not a pressure-driven one.
        #
        # Shedding under pressure did not disappear with it: `get_crawler`'s
        # memory guard evicts one idle LRU browser per refusal, which is the
        # same intent without the launch-while-tight loop. Do NOT restore a
        # pressure-driven TTL here on the strength of a memory regression — the
        # one this comment used to cite is disputed on three counts (see
        # tasks/replica-memory-baseline-unexplained.md).
        interval = 10 if mem_pct > 80 else (30 if mem_pct > 60 else 60)
        cold_ttl, hot_ttl = BASE_IDLE_TTL, BASE_IDLE_TTL * 2

        await asyncio.sleep(interval)

        now = time.time()
        async with LOCK:
            # Clean cold pool
            for sig in list(COLD_POOL.keys()):
                if now - LAST_USED.get(sig, now) > cold_ttl:
                    crawler = COLD_POOL[sig]
                    if getattr(crawler, 'active_requests', 0) > 0:
                        continue  # still serving requests, skip
                    idle_time = now - LAST_USED[sig]
                    logger.info(f"🧹 Closing cold browser (sig={sig[:8]}, idle={idle_time:.0f}s)")
                    with suppress(Exception):
                        await crawler.close()
                    COLD_POOL.pop(sig, None)
                    LAST_USED.pop(sig, None)
                    USAGE_COUNT.pop(sig, None)

                    # Track in monitor
                    try:
                        from monitor import get_monitor
                        await get_monitor().track_janitor_event("close_cold", sig, {"idle_seconds": int(idle_time), "ttl": cold_ttl})
                    except:
                        pass

            # Clean hot pool (more conservative)
            for sig in list(HOT_POOL.keys()):
                if now - LAST_USED.get(sig, now) > hot_ttl:
                    crawler = HOT_POOL[sig]
                    if getattr(crawler, 'active_requests', 0) > 0:
                        continue  # still serving requests, skip
                    idle_time = now - LAST_USED[sig]
                    logger.info(f"🧹 Closing hot browser (sig={sig[:8]}, idle={idle_time:.0f}s)")
                    with suppress(Exception):
                        await crawler.close()
                    HOT_POOL.pop(sig, None)
                    LAST_USED.pop(sig, None)
                    USAGE_COUNT.pop(sig, None)

                    # Track in monitor
                    try:
                        from monitor import get_monitor
                        await get_monitor().track_janitor_event("close_hot", sig, {"idle_seconds": int(idle_time), "ttl": hot_ttl})
                    except:
                        pass

            # Aitosoft: force-close browsers whose active_requests has been > 0
            # for longer than STUCK_BUSY_TIMEOUT_S. This catches leaked slots
            # that escape Fix 1 (asyncio.wait_for in api.py) — e.g. future code
            # paths that bypass the timeout wrapper, or bugs in release_crawler.
            # Without this safety net, a stuck slot wedges the pool forever
            # because regular idle cleanup skips anything with active > 0.
            await _force_close_stuck(now)

            # Aitosoft: close the permanent browser if nothing has ever used it.
            await _close_unused_permanent(now)

            # Log pool stats. Aitosoft: the memory split rides along — the
            # `mem=` figure alone could not distinguish "we are holding 1.3 GB
            # of browsers" from "the kernel is holding page cache", and that
            # ambiguity is what made the 2026-07-31 diagnosis expensive.
            #
            # CAVEAT for whoever reads these lines: `mem_pct` is sampled BEFORE
            # the sleep at the top of this loop and logged AFTER the cleanup
            # below it, so it is up to `interval` seconds staler than the
            # hot/cold counts printed beside it. Do not pair them as
            # simultaneous.
            # Aitosoft 2026-08-02: logged unconditionally now, and it carries
            # `resident=`. The `mem_pct > 60` gate meant pool composition was
            # only observable while memory was already high — so the one
            # question this line exists to answer ("does the browser count
            # explain the memory?") could only be asked on the half of the
            # data where it does not. Answering it cost a Log Analytics
            # regression that a full-coverage log line would have made free.
            logger.info(
                f"📊 Pool: hot={len(HOT_POOL)}, cold={len(COLD_POOL)}, "
                f"permanent={'yes' if PERMANENT else 'no'}, "
                f"resident={resident_browsers()}/{MAX_BROWSERS}, "
                f"mem={mem_pct:.1f}%, {memory_breakdown()}"
            )


async def _close_unused_permanent(now: float) -> None:
    """Close the permanent browser when nothing has ever used it.

    Caller MUST hold LOCK. `USAGE_COUNT[DEFAULT_CONFIG_SIG]` is initialised to 0
    by `init_permanent` and incremented only by a default-config pool hit, so a
    count still at zero after the TTL means literally no request has matched it.

    In production that is every request: 0 permanent hits against 224 pool gets
    on 2026-07-31, while the browser held ~139-165 MB for the replica's whole
    life. **Not because MAS always sends a `browser_config`** — that reason was
    recorded here and is wrong (corrected 2026-08-02); see PERMANENT_UNUSED_TTL_S
    above, where the signature mismatch that makes it unreachable by
    construction is spelled out. Recovering that
    is a saving, not a defect fix, and it is safe because `get_crawler` already
    lazily re-creates the permanent browser when a default-config request does
    turn up (the path `test_crawler_pool.py::test_permanent_reinit_after_stuck_
    force_close` already covers).
    """
    global PERMANENT
    if PERMANENT is None or not DEFAULT_CONFIG_SIG:
        return
    if USAGE_COUNT.get(DEFAULT_CONFIG_SIG, 0) > 0:
        return  # it is earning its memory
    if getattr(PERMANENT, "active_requests", 0) > 0:
        return  # cannot be unused and busy, but never close a browser mid-work
    idle_for = now - LAST_USED.get(DEFAULT_CONFIG_SIG, now)
    if idle_for <= PERMANENT_UNUSED_TTL_S:
        return

    logger.info(
        f"🧹 Closing permanent browser — never used in {idle_for:.0f}s "
        f"(every request carries its own browser_config). "
        f"It re-creates lazily if a default-config request arrives."
    )
    crawler, PERMANENT = PERMANENT, None
    with suppress(Exception):
        await crawler.close()
    BUSY_SINCE.pop(id(crawler), None)
    LAST_USED.pop(DEFAULT_CONFIG_SIG, None)
    USAGE_COUNT.pop(DEFAULT_CONFIG_SIG, None)

    try:
        from monitor import get_monitor

        await get_monitor().track_janitor_event(
            "close_unused_permanent",
            DEFAULT_CONFIG_SIG,
            {"idle_seconds": int(idle_for)},
        )
    except Exception:
        pass
