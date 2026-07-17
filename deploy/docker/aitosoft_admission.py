"""
Aitosoft: per-replica render admission control (RenderGate).

Why this exists (2026-07-16 incident): the only concurrency limits were
upstream's GLOBAL_SEM (max_pages=5) and the per-browser page cap — both
*wait silently*, and the waiting happened INSIDE the 180s wall-clock fence.
Under 4-6 concurrent Chromium renders a 2 vCPU replica oversubscribes, one
render starves past the fence, and the client gets a terminal 504 that cost
180s. See tasks/capacity-scaling-redesign.md for the full forensics.

Design (agreed with MAS 2026-07-17):
  * Hard cap of `render_capacity` concurrent full renders per replica
    (gunicorn runs --workers 1, so process-level == replica-level).
  * A short bounded queue (`admission_queue` waiters, `admission_max_wait_s`
    max wait) absorbs micro-bursts while ACA boots more replicas.
  * Beyond that: fail fast with RenderCapacityExceeded -> HTTP 429 +
    Retry-After. MAS retries 429s with backoff; a 429 costs milliseconds
    where the old contention path cost up to 180s.
  * The 180s render fence (limits.wall_clock_s) starts AFTER admission:
    api.py acquires the gate before asyncio.wait_for, so queue wait can
    never eat the render budget. Budget: 15s queue + browser get/launch +
    180s fence ≈ 200s, inside Azure ingress's 240s.
  * Weighted all-or-nothing acquire: a request takes min(len(urls),
    capacity) slots so a multi-URL batch can't smuggle N renders through
    one slot. Slots are granted atomically (no partial holds -> no
    deadlock between two batches).

The ACA scale rule must match: concurrency target == render_capacity, so
Azure adds replicas exactly when a replica is at render capacity.

Static-mode requests (httpx, no browser) bypass the gate. /md, /screenshot,
/pdf, /html and streaming remain governed only by upstream's GLOBAL_SEM —
MAS does not use them; revisit if that changes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_RENDER_CAPACITY = 2
DEFAULT_ADMISSION_QUEUE = 4
DEFAULT_ADMISSION_MAX_WAIT_S = 15.0
RETRY_AFTER_S = 5  # advertised in the 429 Retry-After header


class RenderCapacityExceeded(Exception):
    """Raised when a render cannot be admitted (queue full or wait timeout)."""

    def __init__(self, reason: str, retry_after_s: int = RETRY_AFTER_S):
        super().__init__(reason)
        self.reason = reason
        self.retry_after_s = retry_after_s


class RenderGate:
    """Bounded-concurrency, bounded-queue admission gate for browser renders.

    All-or-nothing weighted acquire on top of an asyncio.Condition. Not
    strictly FIFO under contention (Condition.notify_all races waiters);
    with weight-1 requests (MAS's traffic) this is effectively fair and
    a heavier waiter cannot deadlock, only wait its bounded time.
    """

    def __init__(
        self,
        capacity: int = DEFAULT_RENDER_CAPACITY,
        max_queue: int = DEFAULT_ADMISSION_QUEUE,
        max_wait_s: float = DEFAULT_ADMISSION_MAX_WAIT_S,
    ):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self.max_queue = max(0, max_queue)
        self.max_wait_s = max_wait_s
        self._in_use = 0
        self._queued = 0
        self._cond = asyncio.Condition()

    def snapshot(self) -> dict:
        return {
            "capacity": self.capacity,
            "in_use": self._in_use,
            "queued": self._queued,
            "max_queue": self.max_queue,
            "max_wait_s": self.max_wait_s,
        }

    async def acquire(self, weight: int = 1, label: Optional[str] = None) -> int:
        """Admit `weight` renders (clamped to capacity). Returns the granted
        weight, which MUST be passed back to release(). Raises
        RenderCapacityExceeded when the queue is full or the wait times out.

        `label` (optional, typically the request URL) is echoed in the ADMIT
        log line so every admission — immediate or queued — is attributable
        to a request in the replica logs (2026-07-17 WAA eval: the fence 504s
        could only be located via queue-wait timing coincidences).

        NOTE on weight clamping: a weight > capacity is clamped, so the gate
        alone cannot bound a multi-URL batch's render concurrency. Not
        reachable in practice: multi-URL requests are rejected with 400 in
        api.py handle_crawl_request, upstream of this gate (MAS single-URL
        contract, 2026-07-17 — see AITOSOFT_CHANGES.md).
        """
        weight = max(1, min(int(weight), self.capacity))
        async with self._cond:
            if self._in_use + weight <= self.capacity:
                self._in_use += weight
                self._log_admit(label, 0.0)
                return weight

            if self._queued >= self.max_queue:
                logger.warning(
                    "RenderGate REJECT (queue full): in_use=%d/%d queued=%d",
                    self._in_use,
                    self.capacity,
                    self._queued,
                )
                raise RenderCapacityExceeded(
                    f"render capacity exhausted ({self._in_use}/{self.capacity} "
                    f"rendering, {self._queued} queued)"
                )

            self._queued += 1
            t0 = asyncio.get_event_loop().time()
            try:
                await asyncio.wait_for(
                    self._cond.wait_for(lambda: self._in_use + weight <= self.capacity),
                    timeout=self.max_wait_s,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "RenderGate REJECT (wait timeout %.0fs): in_use=%d/%d queued=%d",
                    self.max_wait_s,
                    self._in_use,
                    self.capacity,
                    self._queued,
                )
                raise RenderCapacityExceeded(
                    f"no render slot freed within {self.max_wait_s:.0f}s"
                ) from None
            finally:
                self._queued -= 1

            waited = asyncio.get_event_loop().time() - t0
            self._in_use += weight
            self._log_admit(label, waited)
            return weight

    def _log_admit(self, label: Optional[str], waited_s: float) -> None:
        logger.info(
            "RenderGate ADMIT url=%s waited=%.1fs in_use=%d/%d queued=%d",
            label or "-",
            waited_s,
            self._in_use,
            self.capacity,
            self._queued,
        )

    async def release(self, weight: int) -> None:
        async with self._cond:
            self._in_use = max(0, self._in_use - weight)
            self._cond.notify_all()


_GATE: Optional[RenderGate] = None


def get_render_gate() -> RenderGate:
    """Process-wide gate, sized from config.yml crawler.pool.* on first use."""
    global _GATE
    if _GATE is None:
        try:
            from utils import load_config

            pool = (load_config().get("crawler", {}) or {}).get("pool", {}) or {}
        except Exception:
            pool = {}
        _GATE = RenderGate(
            capacity=int(pool.get("render_capacity", DEFAULT_RENDER_CAPACITY)),
            max_queue=int(pool.get("admission_queue", DEFAULT_ADMISSION_QUEUE)),
            max_wait_s=float(
                pool.get("admission_max_wait_s", DEFAULT_ADMISSION_MAX_WAIT_S)
            ),
        )
        logger.info("RenderGate initialized: %s", _GATE.snapshot())
    return _GATE


def set_render_gate(gate: Optional[RenderGate]) -> None:
    """Test hook: inject or reset the singleton."""
    global _GATE
    _GATE = gate
