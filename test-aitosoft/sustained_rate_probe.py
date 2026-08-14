#!/usr/bin/env python3
"""sustained_rate_probe.py — the RATCHET half of the acceptance measurement for
`tasks/autoscaler-ratchets-to-the-cap.md`.

WHY THIS EXISTS (and why cold_burst_probe.py is not enough)
------------------------------------------------------------
`cold_burst_probe.py` fires N concurrent requests at a cold service. That
measures the SAFETY side: cold-start 429s and RenderGate queue wait. It does
NOT measure the ratchet, and cannot.

The measured evidence says the ACA HTTP scaler tracks ARRIVAL RATE over a
trailing ~5-7 minute window, not instantaneous concurrency:

  run          req/min  concurrency  peak-inflight  replica high-water
  RUN-A 08-05    6.3      0.74           6                18
  SEG2  08-06    5.6      0.84           7                16
  RUN-C 08-07    5.8      0.83           9                14
  SEG3  08-08   10.7      1.26           8                30

  high-water / (req/min) = 2.84, 2.87, 2.40, 2.79   (cv 8%)
  high-water / (concurrency/2) spans 35-49x          (no relationship)

RUN-C reached 14 replicas on 43 requests in 7.4 min; SEG2 reached 16 on 274
requests over 49 min. Total volume is nearly irrelevant; RATE is what moves it.
Request DURATION does not enter at all.

So a one-shot burst spikes and drains without ever filling the trailing window.
To reproduce the ratchet you must hold a steady arrival rate for longer than the
window. Segment 3 reached 30 replicas after ~10 minutes at 10.7 req/min.

This script holds a constant arrival rate for a set duration. Default 10.7/min
for 12 min = ~128 requests, which is segment 3's shape compressed to the part
that matters.

THE INSTRUMENT-VALIDATION POINT, WHICH IS THE REAL REASON TO RUN THE BEFORE-ARM
-------------------------------------------------------------------------------
The before-arm is not ceremony. If a synthetic raw:// stream at 10.7 req/min
does NOT climb to ~26-31 replicas on the current setting, then this instrument
does not reproduce the phenomenon, and the after-arm would be measuring nothing.
Run the before-arm first and check it against the prediction from the table
above (2.4-2.9 x rate) BEFORE changing anything.

It also removes the confound the task file flags: segment 3 ran against
maxReplicas 30 and was quasi-censored there (the rate model predicts 30.5).
The before-arm runs against the current 45, same as the after-arm.

TARGET: raw:// — zero third-party traffic, full render path. See
cold_burst_probe.py's module docstring for the four source-verified reasons.

SAFETY
------
* Bearer token read from CRAWL4AI_API_TOKEN; never printed or written to disk.
* Hard caps: rate <= 30/min, duration <= 20 min, total <= 400 requests.
* Refuses to start unless the app is at zero replicas (--allow-warm overrides).
* --dry-run prints the schedule and one exact request body, sends nothing.

Usage:
    export CRAWL4AI_API_TOKEN=...
    python sustained_rate_probe.py --dry-run --label before-c2
    python sustained_rate_probe.py --label before-c2
    # ... change the ACA scale rule ...
    python sustained_rate_probe.py --label after-c4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# Reuse the burst probe's payload + preflight so both arms are byte-comparable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cold_burst_probe import (  # noqa: E402
    build_raw_payload,
    build_request_body,
    read_active_replicas,
    RAW_RENDER_OVERHEAD_S,
    MAS_P50_RENDER_S,
)

DEFAULT_ENDPOINT = (
    "https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io"
)

# Segment 3's measured arrival rate, the run that produced the 30-replica ratchet.
SEG3_RATE_PER_MIN = 10.7

MAX_RATE_PER_MIN = 30.0
MAX_DURATION_MIN = 20.0
MAX_TOTAL_REQUESTS = 400


async def one_request(
    client: httpx.AsyncClient,
    endpoint: str,
    body: Dict[str, Any],
    headers: Dict[str, str],
    seq: int,
    t_origin: float,
    timeout_s: float,
) -> Dict[str, Any]:
    """Fire one /crawl and record what the client can see. Never raises."""
    rec: Dict[str, Any] = {
        "seq": seq,
        "offset_s": round(time.monotonic() - t_origin, 3),
        "status": None,
        "ttfb_s": None,
        "total_s": None,
        "failure_class": None,
        "retry_after": None,
        "error": None,
    }
    t0 = time.monotonic()
    try:
        req = client.build_request(
            "POST", f"{endpoint}/crawl", json=body, headers=headers
        )
        resp = await client.send(req, stream=True)
        rec["ttfb_s"] = round(time.monotonic() - t0, 3)
        rec["status"] = resp.status_code
        if resp.status_code == 429:
            rec["retry_after"] = resp.headers.get("Retry-After")
        raw = await resp.aread()
        await resp.aclose()
        rec["total_s"] = round(time.monotonic() - t0, 3)
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                # failure_class lives on the envelope or on the first result
                rec["failure_class"] = payload.get("failure_class")
                results = payload.get("results")
                if (
                    rec["failure_class"] is None
                    and isinstance(results, list)
                    and results
                ):
                    if isinstance(results[0], dict):
                        rec["failure_class"] = results[0].get("failure_class")
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001 - we want every transport failure recorded
        rec["total_s"] = round(time.monotonic() - t0, 3)
        rec["error"] = f"{type(exc).__name__}: {exc}"
    return rec


async def run_probe(args: argparse.Namespace, token: str) -> Dict[str, Any]:
    target = build_raw_payload(args.payload_kb, args.label)
    delay = max(0.0, round(args.render_s - RAW_RENDER_OVERHEAD_S, 2))
    body = build_request_body(target, delay)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    interval = 60.0 / args.rate_per_min
    total = int(args.duration_min * args.rate_per_min)

    print(f"  arrival interval  {interval:.2f}s  ({args.rate_per_min}/min)")
    print(f"  planned requests  {total} over {args.duration_min} min")
    print(f"  fanout            {args.fanout} request(s) per arrival")
    print()

    # Aitosoft 2026-08-14: the connection-count arm. The ACA HTTP scaler's input
    # is undocumented; an ACA maintainer states it counts "active connections as
    # well as requests" (microsoft/azure-container-apps#536), and connection
    # count is the only observable of the right magnitude to explain a fleet of
    # ~12 replicas on 0.3 req/s. `--no-keepalive` sets max_keepalive_connections
    # to 0, so httpx closes each connection after its response and every request
    # opens a fresh one. Everything else -- arrival rate, fanout, render time,
    # payload -- is held identical, which is exactly what the 2026-08-08 A/B
    # failed to do: its `--fanout 4` arm varied burstiness and connection count
    # together (see tasks/crawl-cost-is-idle-replicas-not-slow-renders.md §3).
    # THE TRAP THAT COST THIS EXPERIMENT ITS FIRST RUN, 2026-08-14: httpx's
    # default `keepalive_expiry` is **5.0 s** (verified by executing
    # `httpx.Limits().keepalive_expiry` on httpx 0.28.1, not by reading docs).
    # At 19 req/min with fanout 4 the gap between arrivals is **12.63 s**, so
    # every pooled connection expires before the next tick and the "pooled" arm
    # silently becomes a second copy of the no-keepalive arm. It climbed to 6
    # replicas and was recorded as a control until the number looked wrong.
    #
    # This is the same defect we are investigating in MAS's client: undici's
    # ~4 s keepAliveTimeout against ~7 pages per company spread over time. A
    # pool that expires between uses is not a pool. **Set the expiry explicitly
    # in both arms** so the only difference is the one under test.
    max_conns = int(args.rate_per_min * 4 + 20)
    if args.no_keepalive:
        limits = httpx.Limits(max_connections=max_conns, max_keepalive_connections=0)
    else:
        limits = httpx.Limits(
            max_connections=max_conns,
            max_keepalive_connections=max_conns,
            keepalive_expiry=args.keepalive_expiry,
        )
    started_utc = datetime.now(timezone.utc).isoformat()
    t_origin = time.monotonic()
    records: List[Dict[str, Any]] = []
    tasks: List[asyncio.Task] = []

    async with httpx.AsyncClient(timeout=args.timeout_s, limits=limits) as client:
        seq = 0
        for tick in range(total // max(1, args.fanout)):
            due = t_origin + tick * interval * args.fanout
            now = time.monotonic()
            if due > now:
                await asyncio.sleep(due - now)
            for _ in range(args.fanout):
                seq += 1
                tasks.append(
                    asyncio.create_task(
                        one_request(
                            client,
                            args.endpoint,
                            body,
                            headers,
                            seq,
                            t_origin,
                            args.timeout_s,
                        )
                    )
                )
            elapsed = time.monotonic() - t_origin
            done = sum(1 for t in tasks if t.done())
            print(
                f"    t={elapsed:6.1f}s  sent={seq:3d}  completed={done:3d}",
                flush=True,
            )
        print("\n  all requests dispatched; draining in-flight...")
        records = list(await asyncio.gather(*tasks))

    wall = time.monotonic() - t_origin
    records.sort(key=lambda r: r["seq"])
    return summarize(args, records, started_utc, wall, delay, body)


def summarize(
    args: argparse.Namespace,
    records: List[Dict[str, Any]],
    started_utc: str,
    wall: float,
    delay: float,
    body: Dict[str, Any],
) -> Dict[str, Any]:
    by_status: Dict[str, int] = {}
    for r in records:
        key = (
            str(r["status"])
            if r["status"] is not None
            else f"ERR:{(r['error'] or '')[:40]}"
        )
        by_status[key] = by_status.get(key, 0) + 1

    oks = [r for r in records if r["status"] == 200]
    durs = sorted(r["total_s"] for r in oks if r["total_s"] is not None)
    ttfbs = sorted(r["ttfb_s"] for r in oks if r["ttfb_s"] is not None)

    def pct(xs: List[float], p: float) -> Optional[float]:
        if not xs:
            return None
        idx = min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1))))
        return round(xs[idx], 3)

    classes: Dict[str, int] = {}
    for r in records:
        fc = r.get("failure_class")
        if fc:
            classes[fc] = classes.get(fc, 0) + 1

    n429 = sum(1 for r in records if r["status"] == 429)

    return {
        "label": args.label,
        "started_utc": started_utc,
        "wall_s": round(wall, 1),
        "config": {
            "rate_per_min": args.rate_per_min,
            "duration_min": args.duration_min,
            "fanout": args.fanout,
            "render_s_target": args.render_s,
            "delay_before_return_html": delay,
            "payload_kb": args.payload_kb,
            "endpoint": args.endpoint,
        },
        "crawler_config_sent": body["crawler_config"],
        "n": len(records),
        "by_status": by_status,
        "n_429": n429,
        "failure_classes": classes,
        "duration_s": {
            "p50": pct(durs, 50),
            "p90": pct(durs, 90),
            "p99": pct(durs, 99),
            "max": round(durs[-1], 3) if durs else None,
            "mean": round(statistics.fmean(durs), 3) if durs else None,
            "sum": round(sum(durs), 1) if durs else 0.0,
        },
        "ttfb_s": {
            "p50": pct(ttfbs, 50),
            "p90": pct(ttfbs, 90),
            "max": round(ttfbs[-1], 3) if ttfbs else None,
        },
        "records": records,
    }


def main() -> int:
    p = argparse.ArgumentParser(
        description="Sustained arrival-rate probe for the ACA scale-rule change."
    )
    p.add_argument(
        "--rate-per-min",
        type=float,
        default=SEG3_RATE_PER_MIN,
        help=f"arrival rate. Default {SEG3_RATE_PER_MIN} (segment 3's measured rate).",
    )
    p.add_argument(
        "--duration-min",
        type=float,
        default=12.0,
        help="how long to hold the rate. Default 12 min.",
    )
    p.add_argument(
        "--fanout",
        type=int,
        default=1,
        help="requests per arrival tick. 1 = uniform (cleanest control).",
    )
    p.add_argument("--label", default="unlabelled")
    p.add_argument(
        "--render-s",
        type=float,
        default=MAS_P50_RENDER_S,
        help=f"target per-render wall time. Default {MAS_P50_RENDER_S} (MAS p50).",
    )
    p.add_argument("--payload-kb", type=int, default=8)
    p.add_argument(
        "--keepalive-expiry",
        type=float,
        default=5.0,
        help=(
            "seconds an idle pooled connection is kept. Default 5.0 is HTTPX'S OWN "
            "DEFAULT, which is SHORTER than the arrival gap at any rate below "
            "~19/min with fanout 4 -- so the default silently disables pooling. "
            "Pass a value above the arrival gap (e.g. 300) for a real pooled arm."
        ),
    )
    p.add_argument(
        "--no-keepalive",
        action="store_true",
        help=(
            "close every connection after its response (max_keepalive_connections=0). "
            "This is the B arm of the connection-count experiment: run it against an "
            "otherwise identical pooled A arm to test whether the ACA scaler's input "
            "is connections rather than request rate."
        ),
    )
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    p.add_argument("--timeout-s", type=float, default=180.0)
    p.add_argument("--outdir", default=str(Path(__file__).resolve().parent))
    p.add_argument("--allow-warm", action="store_true")
    p.add_argument("--skip-replica-check", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    # ---- hard safety caps -------------------------------------------------
    if args.rate_per_min > MAX_RATE_PER_MIN:
        print(
            f"REFUSED: --rate-per-min {args.rate_per_min} exceeds cap "
            f"{MAX_RATE_PER_MIN}",
            file=sys.stderr,
        )
        return 2
    if args.duration_min > MAX_DURATION_MIN:
        print(
            f"REFUSED: --duration-min {args.duration_min} exceeds cap "
            f"{MAX_DURATION_MIN}",
            file=sys.stderr,
        )
        return 2
    total = int(args.duration_min * args.rate_per_min)
    if total > MAX_TOTAL_REQUESTS:
        print(
            f"REFUSED: {total} requests exceeds cap {MAX_TOTAL_REQUESTS}",
            file=sys.stderr,
        )
        return 2
    if args.fanout < 1:
        print("REFUSED: --fanout must be >= 1", file=sys.stderr)
        return 2

    token = os.getenv("CRAWL4AI_API_TOKEN", "").strip()
    if not token and not args.dry_run:
        print("REFUSED: CRAWL4AI_API_TOKEN is not set.", file=sys.stderr)
        return 2

    delay = max(0.0, round(args.render_s - RAW_RENDER_OVERHEAD_S, 2))
    print("=" * 72)
    print(f"  sustained-rate probe   label={args.label}")
    print("=" * 72)
    print(f"  endpoint          {args.endpoint}")
    print(
        f"  target            raw:// synthetic page, {args.payload_kb} KiB "
        "(NO third-party traffic)"
    )
    print(f"  render            {args.render_s}s -> delay_before_return_html={delay}")

    if args.dry_run:
        target = build_raw_payload(args.payload_kb, args.label)
        body = build_request_body(target, delay)
        interval = 60.0 / args.rate_per_min
        print(f"  arrival interval  {interval:.2f}s")
        print(f"  planned requests  {total}")
        print("\n  exact request body (url truncated):")
        shown = dict(body)
        shown["urls"] = [body["urls"][0][:120] + f"... [{len(body['urls'][0])} chars]"]
        print(json.dumps(shown, indent=2))
        print("\n  DRY RUN — nothing sent.")
        return 0

    # ---- preflight: must be cold -----------------------------------------
    if not args.skip_replica_check:
        live = read_active_replicas()
        if live is None:
            print("  WARNING: could not read replica count via az; continuing.")
        else:
            print(f"  live replicas     {live}")
            if live > 0 and not args.allow_warm:
                print(
                    f"\nREFUSED: app has {live} live replica(s); this would not "
                    "be a cold-start measurement. Wait for scale-to-zero "
                    "(~5-10 min after last traffic) or pass "
                    "--allow-warm.",
                    file=sys.stderr,
                )
                return 2
    print()

    result = asyncio.run(run_probe(args, token))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.outdir) / f"sustained_{args.label}_{stamp}.json"
    out.write_text(json.dumps(result, indent=2))

    print("\n" + "=" * 72)
    print(
        f"  RESULT  label={result['label']}  n={result['n']}  wall={result['wall_s']}s"
    )
    print("=" * 72)
    print(f"  by status         {result['by_status']}")
    print(f"  429s              {result['n_429']}")
    if result["failure_classes"]:
        print(f"  failure_classes   {result['failure_classes']}")
    d = result["duration_s"]
    print(f"  duration  p50={d['p50']}  p90={d['p90']}  p99={d['p99']}  max={d['max']}")
    print(
        f"  busy-seconds sum  {d['sum']}  -> mean concurrency "
        f"{round(d['sum'] / (result['wall_s'] or 1), 2)}"
    )
    t = result["ttfb_s"]
    print(f"  ttfb      p50={t['p50']}  p90={t['p90']}  max={t['max']}")
    print(f"\n  artifact          {out}")
    print(
        "\n  Now read the server side with cold_burst_probe.kql "
        "(replica high-water, SuccessfulRescale ramp, RenderGate ADMIT/REJECT)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
