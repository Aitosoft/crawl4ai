#!/usr/bin/env python3
"""
Soak test for crawl4ai leak fixes (2026-04-14).

Validates that Fix 1 (asyncio.wait_for in api.py) and Fix 2 (janitor force-close
in crawler_pool.py) hold under sustained mixed load. Alternates known-healthy
Finnish sites with bot-protected "hard" sites so we can see memory return to
baseline after each difficult URL.

Memory should stay flat or return to baseline after bursts. If we see
monotonic growth, the leak is NOT fixed.

Usage:
    python test-aitosoft/test_soak.py --duration-min 30     # short soak
    python test-aitosoft/test_soak.py --duration-min 180    # full 3h soak
    python test-aitosoft/test_soak.py --parallel 3          # simulate 3 agents
    python test-aitosoft/test_soak.py --url $LOCAL_URL --token test-token

Exits 0 on pass (memory flat, no stuck active_requests), non-zero on fail.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

DEFAULT_URL = os.getenv(
    "CRAWL4AI_API_URL",
    "https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io",
)
DEFAULT_TOKEN = os.getenv("CRAWL4AI_API_TOKEN", "")

# ── Test site catalogue ──────────────────────────────────────────────────
# Healthy: mix of public-infrastructure endpoints (safe to hit repeatedly
# in a 3h soak) and a small set of real Finnish sites (production realism).
# The public endpoints absorb the bulk of the repeat traffic so we don't
# over-scrape small sites — see CLAUDE.md "test site safety rules".
HEALTHY_SITES = [
    # Public endpoints — unlimited repeat hits
    "https://httpbin.org/html",
    "https://httpbin.org/get",
    "https://example.com",
    "https://www.iana.org/domains/reserved",
    "https://www.w3.org/",
    "https://docs.python.org/3/",
    "https://wordpress.org/",
    "https://readthedocs.org/",
    "https://pypi.org/",
    # Real Finnish sites — light rotation, kept minimal
    "https://www.jpond.fi/yhteystiedot/",
    "https://caverna.fi",
    "https://solwers.com/sijoittajat/hallinnointi/",
]

# Hard: Sites observed to block Azure egress IP or hang on Cloudflare.
# These are the trigger pattern for the 2026-04-14 incident. If Fix 1 works,
# each should time out cleanly at 180s (server-side) and return a 504 to us
# without wedging the pool. MAS's production retry logic treats 504 as
# retryable.
HARD_SITES = [
    "https://ahlmanedu.fi/tietoa-ahlmanedusta/yhteystiedot/hallitus/",
    "https://www.diabetes.fi/yhteystiedot",
    "https://www.diabetes.fi/henkilokunnan-yhteystiedot",
]

# Request cadence: roughly mirrors a WAA company (~11 requests / company).
# One "cycle" = 10 healthy + 2 hard. Represents ~1 company's worth of work.
CYCLE_HEALTHY = 10
CYCLE_HARD = 2


@dataclass
class RequestOutcome:
    url: str
    is_hard: bool
    status_code: int
    ok: bool
    duration_s: float
    error: Optional[str] = None


@dataclass
class Sample:
    ts: float
    elapsed_s: float
    # From /monitor/health
    memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None
    # From /monitor/browsers
    browser_count: Optional[int] = None
    total_browser_memory_mb: Optional[float] = None
    active_request_total: Optional[int] = None
    # Request accounting (cumulative)
    requests_sent: int = 0
    requests_ok: int = 0
    requests_504: int = 0
    requests_other_fail: int = 0


@dataclass
class SoakResult:
    start_ts: float
    end_ts: float
    duration_min: float
    samples: list[Sample] = field(default_factory=list)
    outcomes: list[RequestOutcome] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.memory_drift_ok
            and not self.stuck_browsers_detected
            and self.error_rate_ok
        )

    @property
    def memory_drift_ok(self) -> bool:
        """Check last-quarter memory avg vs first-quarter: must not grow > 20%."""
        mem_samples = [s.memory_mb for s in self.samples if s.memory_mb]
        if len(mem_samples) < 8:
            return True  # not enough samples to judge
        q = len(mem_samples) // 4
        first_q = mem_samples[:q]
        last_q = mem_samples[-q:]
        first_avg = sum(first_q) / len(first_q)
        last_avg = sum(last_q) / len(last_q)
        growth = (last_avg - first_avg) / first_avg if first_avg > 0 else 0
        return growth < 0.20

    @property
    def memory_drift_percent(self) -> float:
        mem_samples = [s.memory_mb for s in self.samples if s.memory_mb]
        if len(mem_samples) < 8:
            return 0.0
        q = len(mem_samples) // 4
        first_q = mem_samples[:q]
        last_q = mem_samples[-q:]
        first_avg = sum(first_q) / len(first_q)
        last_avg = sum(last_q) / len(last_q)
        return 100 * (last_avg - first_avg) / first_avg if first_avg > 0 else 0.0

    @property
    def stuck_browsers_detected(self) -> bool:
        """Any moment where > 1 browser had active_requests > 0 for > 10 min?

        We approximate by checking the last-3-samples plateau: if active_request_total
        stayed > 0 for > 3 consecutive sample intervals with no completed requests,
        something is stuck.
        """
        # Simpler heuristic: after all requests complete, did active_request_total
        # return to 0 within ~2 minutes? If the last 5 samples (post-load) still
        # show active > 0, that's a leak.
        post_load_samples = [
            s for s in self.samples[-5:] if s.active_request_total is not None
        ]
        if not post_load_samples:
            return False
        return any(
            s.active_request_total and s.active_request_total > 0
            for s in post_load_samples
        )

    @property
    def error_rate_ok(self) -> bool:
        """Healthy requests should succeed > 95%. Hard requests are expected to fail."""
        healthy = [o for o in self.outcomes if not o.is_hard]
        if not healthy:
            return True
        ok_count = sum(1 for o in healthy if o.ok)
        return ok_count / len(healthy) >= 0.95


async def _sample_telemetry(
    client: httpx.AsyncClient, base_url: str, token: str
) -> dict[str, Any]:
    """Fetch current server state snapshot. Best-effort — returns {} on failure."""
    out: dict[str, Any] = {}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = await client.get(f"{base_url}/monitor/health", headers=headers, timeout=5.0)
        if r.status_code == 200:
            out["health"] = r.json()
    except Exception:
        pass
    try:
        r = await client.get(
            f"{base_url}/monitor/browsers", headers=headers, timeout=5.0
        )
        if r.status_code == 200:
            out["browsers"] = r.json()
    except Exception:
        pass
    return out


async def _one_request(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    url: str,
    is_hard: bool,
) -> RequestOutcome:
    start = time.time()
    try:
        r = await client.post(
            f"{base_url}/crawl",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "urls": [url],
                "crawler_config": {
                    "wait_until": "domcontentloaded",
                    "remove_consent_popups": True,
                    "page_timeout": 60000,
                    "delay_before_return_html": 2.0,
                },
            },
            timeout=200.0,  # 180s server + network margin
        )
        duration = time.time() - start
        ok = r.status_code == 200
        return RequestOutcome(
            url=url,
            is_hard=is_hard,
            status_code=r.status_code,
            ok=ok,
            duration_s=duration,
            error=None
            if ok
            else (r.text[:200] if hasattr(r, "text") else str(r.status_code)),
        )
    except httpx.TimeoutException:
        return RequestOutcome(
            url=url,
            is_hard=is_hard,
            status_code=0,
            ok=False,
            duration_s=time.time() - start,
            error="client-timeout",
        )
    except Exception as e:
        return RequestOutcome(
            url=url,
            is_hard=is_hard,
            status_code=0,
            ok=False,
            duration_s=time.time() - start,
            error=f"{type(e).__name__}: {e}",
        )


async def _agent_loop(
    agent_id: int,
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    end_ts: float,
    outcomes: list[RequestOutcome],
    counter_lock: asyncio.Lock,
    counters: dict[str, int],
) -> None:
    """Mimic one WAA agent hitting the service sequentially until end_ts."""
    cycle = 0
    while time.time() < end_ts:
        cycle += 1
        batch: list[tuple[str, bool]] = []
        # Rotate through healthy + hard mix
        for i in range(CYCLE_HEALTHY):
            url = HEALTHY_SITES[(cycle * CYCLE_HEALTHY + i) % len(HEALTHY_SITES)]
            batch.append((url, False))
        for i in range(CYCLE_HARD):
            url = HARD_SITES[(cycle + i) % len(HARD_SITES)]
            batch.append((url, True))

        for url, is_hard in batch:
            if time.time() >= end_ts:
                break
            outcome = await _one_request(client, base_url, token, url, is_hard)
            outcomes.append(outcome)
            async with counter_lock:
                counters["sent"] += 1
                if outcome.ok:
                    counters["ok"] += 1
                elif outcome.status_code == 504:
                    counters["504"] += 1
                else:
                    counters["other_fail"] += 1
            tag = "HARD" if is_hard else "ok  "
            code = outcome.status_code or "—"
            print(
                f"  [a{agent_id} c{cycle:03d}] {tag} {code} "
                f"{outcome.duration_s:5.1f}s  {url[:70]}"
            )
            # Light pacing to avoid hammering a single site
            await asyncio.sleep(0.5)


async def _telemetry_loop(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    start_ts: float,
    end_ts: float,
    samples: list[Sample],
    counters: dict[str, int],
    interval_s: int = 30,
) -> None:
    """Sample server telemetry every interval_s until end_ts (+2 min drain)."""
    drain_end = end_ts + 120  # give the pool 2 min to settle post-load
    while time.time() < drain_end:
        now = time.time()
        snap = await _sample_telemetry(client, base_url, token)
        sample = Sample(
            ts=now,
            elapsed_s=now - start_ts,
            requests_sent=counters.get("sent", 0),
            requests_ok=counters.get("ok", 0),
            requests_504=counters.get("504", 0),
            requests_other_fail=counters.get("other_fail", 0),
        )
        # /monitor/health shape: {container: {memory_percent, cpu_percent}, pool: {...}}
        health = snap.get("health", {})
        container = health.get("container", {}) if isinstance(health, dict) else {}
        pool = health.get("pool", {}) if isinstance(health, dict) else {}
        sample.memory_mb = pool.get("total_memory_mb")
        sample.cpu_percent = container.get("cpu_percent")
        # Browser count from pool.permanent/hot/cold
        perm_active = 1 if (pool.get("permanent") or {}).get("active") else 0
        hot_count = (pool.get("hot") or {}).get("count") or 0
        cold_count = (pool.get("cold") or {}).get("count") or 0
        sample.browser_count = perm_active + hot_count + cold_count
        sample.total_browser_memory_mb = pool.get("total_memory_mb")
        # /monitor/browsers gives per-browser active counts
        browsers = snap.get("browsers", {})
        b_list = browsers.get("browsers") or []
        if isinstance(b_list, list):
            sample.active_request_total = sum(
                (b.get("active_requests") or 0) for b in b_list
            )
        samples.append(sample)

        tag = "load" if now < end_ts else "drain"
        print(
            f"  [{tag}] {sample.elapsed_s / 60:5.1f}m "
            f"mem={sample.memory_mb or '?':>6} MB  "
            f"browsers={sample.browser_count or '?':>2}  "
            f"active={sample.active_request_total or 0}  "
            f"sent={sample.requests_sent} ok={sample.requests_ok} "
            f"504={sample.requests_504} other={sample.requests_other_fail}"
        )
        await asyncio.sleep(interval_s)


async def run_soak(
    base_url: str,
    token: str,
    duration_min: int,
    parallel_agents: int,
) -> SoakResult:
    start_ts = time.time()
    end_ts = start_ts + duration_min * 60
    outcomes: list[RequestOutcome] = []
    samples: list[Sample] = []
    counters = {"sent": 0, "ok": 0, "504": 0, "other_fail": 0}
    counter_lock = asyncio.Lock()

    print("\n🔥 Soak test starting")
    print(f"   Target: {base_url}")
    print(f"   Duration: {duration_min} min + 2 min drain")
    print(f"   Parallel agents: {parallel_agents}")
    print(f"   Cycle pattern: {CYCLE_HEALTHY} healthy + {CYCLE_HARD} hard, repeating\n")

    async with httpx.AsyncClient() as client:
        agent_tasks = [
            asyncio.create_task(
                _agent_loop(
                    i + 1,
                    client,
                    base_url,
                    token,
                    end_ts,
                    outcomes,
                    counter_lock,
                    counters,
                )
            )
            for i in range(parallel_agents)
        ]
        telemetry_task = asyncio.create_task(
            _telemetry_loop(
                client, base_url, token, start_ts, end_ts, samples, counters
            )
        )
        await asyncio.gather(*agent_tasks)
        await telemetry_task

    return SoakResult(
        start_ts=start_ts,
        end_ts=time.time(),
        duration_min=duration_min,
        samples=samples,
        outcomes=outcomes,
    )


def _print_report(result: SoakResult, out_dir: Path) -> None:
    print(f"\n{'=' * 70}")
    print(f"Soak test complete — {'✅ PASS' if result.passed else '❌ FAIL'}")
    print(f"{'=' * 70}")
    print(f"  Duration:         {result.duration_min} min")
    print(f"  Requests sent:    {len(result.outcomes)}")
    healthy = [o for o in result.outcomes if not o.is_hard]
    hard = [o for o in result.outcomes if o.is_hard]
    print(
        f"  Healthy OK rate:  {sum(1 for o in healthy if o.ok)}/{len(healthy)} "
        f"({'✅' if result.error_rate_ok else '❌ below 95% threshold'})"
    )
    print(
        f"  Hard OK rate:     {sum(1 for o in hard if o.ok)}/{len(hard)} "
        f"(non-blocking — hard sites may legitimately fail)"
    )
    print(
        f"  Memory drift:     {result.memory_drift_percent:+.1f}% "
        f"{'✅' if result.memory_drift_ok else '❌ exceeds 20% threshold'}"
    )
    stuck_msg = (
        "❌ active_requests > 0 after drain"
        if result.stuck_browsers_detected
        else "✅ drained to 0"
    )
    print(f"  Post-load stuck:  {stuck_msg}")

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = out_dir / f"soak-{stamp}.json"
    with json_path.open("w") as f:
        json.dump(
            {
                "passed": result.passed,
                "duration_min": result.duration_min,
                "memory_drift_percent": result.memory_drift_percent,
                "samples": [s.__dict__ for s in result.samples],
                "outcomes": [o.__dict__ for o in result.outcomes],
            },
            f,
            default=str,
            indent=2,
        )
    print(f"\n  Raw data: {json_path}")

    # Compact ASCII memory trend
    mem_samples = [s.memory_mb for s in result.samples if s.memory_mb]
    if mem_samples:
        lo, hi = min(mem_samples), max(mem_samples)
        span = max(hi - lo, 1)
        print(f"\n  Memory trend (MB, range {lo:.0f}–{hi:.0f}):")
        width = 40
        buckets = max(len(mem_samples) // 30, 1)
        for i in range(0, len(mem_samples), buckets):
            v = sum(mem_samples[i : i + buckets]) / len(mem_samples[i : i + buckets])
            filled = int(((v - lo) / span) * width)
            print(f"    {v:7.0f} MB  {'█' * filled}{'·' * (width - filled)}")
    print()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=DEFAULT_URL, help="crawl4ai base URL")
    p.add_argument(
        "--token",
        default=DEFAULT_TOKEN,
        help="bearer token (or CRAWL4AI_API_TOKEN env)",
    )
    p.add_argument(
        "--duration-min", type=int, default=30, help="soak duration in minutes"
    )
    p.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="concurrent agents simulated (1=sequential)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("test-aitosoft/results"),
        help="where to write soak artifacts",
    )
    args = p.parse_args()

    if not args.token:
        print("❌ CRAWL4AI_API_TOKEN not set", file=sys.stderr)
        return 2

    result = asyncio.run(
        run_soak(args.url, args.token, args.duration_min, args.parallel)
    )
    _print_report(result, args.out_dir)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
