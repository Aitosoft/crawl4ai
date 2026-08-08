#!/usr/bin/env python3
"""cold_burst_probe.py — acceptance measurement for
`tasks/autoscaler-ratchets-to-the-cap.md`.

WHAT THIS MEASURES
------------------
Fire N concurrent `/crawl` requests at a cold (zero-replica) service and record
what the client sees: 429 count, TTFB distribution, total duration, and the
`failure_class` the envelope carries. Run it before and after the ACA scale-rule
change with the *same* arguments; diff the two JSON files. The server-side half
(replica ramp, `SuccessfulRescale`, RenderGate ADMIT/REJECT) comes from the
companion `cold_burst_probe.kql`.

WHY THE DEFAULT TARGET IS `raw://` AND NOT `example.com`
--------------------------------------------------------
The task file proposes `example.com`. `raw://<html>` dominates it on every axis,
and all four points below were verified from source in this repo, not assumed:

1. **Zero third-party traffic.** `deploy/docker/utils.py:354` returns early for
   `raw:`/`raw://` before any DNS or SSRF check ("Skipped for raw: URLs (inline
   HTML, no network fetch)"), and `api.py:692` excludes `raw:` from the bare-host
   `https://` prefixing. Nothing leaves the replica. TESTING.md golden rule 0 is
   satisfied outright — there is no live request to budget, register, or burn.

2. **It still exercises the FULL render path.** `async_crawler_strategy.py:488`
   routes a `raw:` URL through the browser (`_crawl_web` -> `page.set_content()`)
   whenever `needs_browser` is true, and `remove_consent_popups` — the flag MAS
   sends on every production request — is in that OR. So this hits: RenderGate
   acquire (`api.py`, the 429 boundary), `get_crawler` (pool + real Chromium
   launch on a cold replica), the consent pass, scraping, markdown, and the
   collapse guard. Only the network navigation is skipped.

3. **Render duration is an exact dial.** Measured locally through the real
   pipeline: `delay_before_return_html=0.1` -> 1.42 s wall,
   `delay_before_return_html=3.0` -> 4.18 s wall. Linear, ~1.3 s fixed overhead.
   This is the point that actually decides the experiment: an ACA concurrency
   scaler is driven by `sum(request_duration)`, so **the load shape is the
   independent variable**. `example.com` gives you whatever it gives you (~1-2 s),
   roughly 4x lighter than MAS's measured production p50 of 4.95 s — you would be
   characterising the scaler at a load it never sees. `--render-s` sets it.

4. **The before/after A/B is only valid if the load is identical in both arms.**
   `example.com` cannot promise that across two runs minutes or days apart (CDN,
   geography, their own load). `raw://` is byte-identical and duration-identical
   by construction. The task file's "run it before and after, same N, or the
   result means nothing" requirement is *unmeetable* with a third-party target
   and trivially met with this one.

`--target-url` still accepts a live URL, but the script refuses it without
`--allow-live-target` and prints golden rule 0 first.

SAFETY
------
* The bearer token is read from `CRAWL4AI_API_TOKEN` and is never printed,
  logged, or written to the JSON output.
* `--n` above 20 requires `--i-know-what-im-doing`.
* `--rounds` above 3 is refused unconditionally.
* Refuses to start unless the app is at zero replicas (`--allow-warm` overrides).

Usage:
    export CRAWL4AI_API_TOKEN=...          # never echoed
    python cold_burst_probe.py --dry-run --n 12 --label before
    python cold_burst_probe.py --n 12 --label before-c2
    # ... change the scale rule ...
    python cold_burst_probe.py --n 12 --label after-c4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:  # pragma: no cover
    sys.exit("httpx is required: pip install httpx")

DEFAULT_ENDPOINT = (
    "https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io"
)
APP_NAME = "crawl4ai-service"
RESOURCE_GROUP = "aitosoft-prod"

# Measured locally through the real pipeline, 2026-08-08: a raw:// render costs
# ~1.3 s of fixed overhead (set_content + consent pass + scrape + markdown) plus
# delay_before_return_html. MAS production p50 is 4.95 s, p90 9.35 s.
RAW_RENDER_OVERHEAD_S = 1.3
MAS_P50_RENDER_S = 4.95


# ───────────────────────── payload ─────────────────────────


def build_raw_payload(size_kb: int, tag: str) -> str:
    """A `raw://` URL whose body is plausible page markup of a chosen size.

    Content shape barely matters here — the collapse guard only needs the page
    to produce markdown, which it does (measured: 2,117 B html -> 1,756 chars of
    markdown, a healthy ratio). Size is kept small by default so that the
    ingress `RequestDuration` reflects render time and not body upload.
    """
    filler = (
        "<p>Yhteystiedot ja muuta tekstia jotta sivulla on oikeasti sisaltoa "
        "jota markdown-muunnin voi kasitella. </p>"
    )
    head = (
        f"<html><head><title>burst-probe {tag}</title></head><body>"
        f"<h1>burst-probe {tag}</h1><main>"
    )
    tail = "</main></body></html>"
    target = max(0, size_kb * 1024 - len(head) - len(tail))
    body = filler * max(1, target // len(filler))
    return "raw://" + head + body + tail


def build_request_body(target: str, render_s: float) -> Dict[str, Any]:
    """The exact body shape. Mirrors MAS's production request except for the URL.

    `delay_before_return_html` and `remove_consent_popups` are both on the
    untrusted-config ALLOWLIST (`async_configs.py:246-247`) — verified by
    executing `apply_trust_relaxations()`, not by reading it. `process_in_browser`
    is forbidden and is NOT needed: `remove_consent_popups` alone flips
    `needs_browser` to true.
    """
    return {
        "urls": [target],
        "browser_config": {
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
            ),
            "viewport_width": 1920,
            "viewport_height": 1080,
        },
        "crawler_config": {
            "cache_mode": "BYPASS",
            "wait_until": "domcontentloaded",
            "remove_consent_popups": True,
            "delay_before_return_html": render_s,
            "page_timeout": 60000,
            "max_retries": 1,
            "word_count_threshold": 1,
        },
    }


# ───────────────────── preflight: replica state ─────────────────────


def read_active_replicas() -> Optional[int]:
    """Sum of replicas across active revisions, or None if az is unavailable."""
    if shutil.which("az") is None:
        return None
    try:
        out = subprocess.run(
            [
                "az",
                "containerapp",
                "revision",
                "list",
                "-n",
                APP_NAME,
                "-g",
                RESOURCE_GROUP,
                "--query",
                "[?properties.active].properties.replicas",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=True,
        ).stdout
        counts = json.loads(out or "[]")
        return sum(int(c or 0) for c in counts)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! could not read replica count: {type(exc).__name__}: {exc}")
        return None


def read_scale_rule() -> Optional[Dict[str, Any]]:
    """Record the scale rule in the artifact so a before/after diff is
    self-describing. This is the independent variable; not capturing it is how
    two JSON files stop being comparable."""
    if shutil.which("az") is None:
        return None
    try:
        out = subprocess.run(
            [
                "az",
                "containerapp",
                "show",
                "-n",
                APP_NAME,
                "-g",
                RESOURCE_GROUP,
                "--query",
                "properties.template.scale",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=True,
        ).stdout
        return json.loads(out or "null")
    except Exception:  # noqa: BLE001
        return None


# ───────────────────────── the burst ─────────────────────────


async def one_request(
    client: httpx.AsyncClient,
    endpoint: str,
    body: Dict[str, Any],
    headers: Dict[str, str],
    idx: int,
    round_no: int,
    t_zero: float,
) -> Dict[str, Any]:
    """One /crawl request, recording TTFB separately from total duration.

    TTFB is measured at response-header receipt via a streaming send. On a cold
    start it is dominated by ACA activation (measured 10.09 s for a cold /health
    on 2026-08-08); on a warm replica it is dominated by the render. The gap
    between TTFB and total is body transfer and is expected to be ~0.
    """
    rec: Dict[str, Any] = {
        "idx": idx,
        "round": round_no,
        "sent_at_offset_s": round(time.perf_counter() - t_zero, 4),
    }
    t0 = time.perf_counter()
    try:
        req = client.build_request(
            "POST", f"{endpoint}/crawl", json=body, headers=headers
        )
        resp = await client.send(req, stream=True)
        rec["ttfb_s"] = round(time.perf_counter() - t0, 4)
        rec["status"] = resp.status_code
        rec["retry_after"] = resp.headers.get("Retry-After")
        raw = await resp.aread()
        await resp.aclose()
        rec["total_s"] = round(time.perf_counter() - t0, 4)
        rec["bytes"] = len(raw)
        try:
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001
            payload = None
        if isinstance(payload, dict):
            results = payload.get("results") or []
            if results and isinstance(results[0], dict):
                r0 = results[0]
                rec["success"] = r0.get("success")
                rec["failure_class"] = r0.get("failure_class")
                rec["origin_status"] = r0.get("status_code")
                md = r0.get("markdown") or {}
                if isinstance(md, dict):
                    rec["markdown_chars"] = len(md.get("raw_markdown") or "")
            else:
                # Error envelopes (429/500/504) carry detail + sometimes
                # failure_class; keep the detail, it is short and non-secret.
                rec["failure_class"] = payload.get("failure_class")
                detail = payload.get("detail") or payload.get("error")
                if detail:
                    rec["detail"] = str(detail)[:200]
    except Exception as exc:  # noqa: BLE001
        rec["status"] = None
        rec["error"] = f"{type(exc).__name__}: {exc}"[:200]
        rec.setdefault("ttfb_s", None)
        rec["total_s"] = round(time.perf_counter() - t0, 4)
    return rec


async def run_round(
    endpoint: str,
    body: Dict[str, Any],
    token: str,
    n: int,
    round_no: int,
    timeout_s: float,
) -> List[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    limits = httpx.Limits(max_connections=n + 4, max_keepalive_connections=0)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s), limits=limits, http2=False
    ) as client:
        t_zero = time.perf_counter()
        tasks = [
            one_request(client, endpoint, body, headers, i, round_no, t_zero)
            for i in range(n)
        ]
        return list(await asyncio.gather(*tasks))


# ───────────────────────── reporting ─────────────────────────


def pct(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return round(s[k], 3)


def summarise(records: List[Dict[str, Any]], wall_s: float) -> Dict[str, Any]:
    by_status: Dict[str, int] = {}
    for r in records:
        key = str(r.get("status")) if r.get("status") is not None else "transport-error"
        by_status[key] = by_status.get(key, 0) + 1
    ttfbs = [r["ttfb_s"] for r in records if isinstance(r.get("ttfb_s"), (int, float))]
    totals = [
        r["total_s"] for r in records if isinstance(r.get("total_s"), (int, float))
    ]
    fclasses: Dict[str, int] = {}
    for r in records:
        fc = r.get("failure_class")
        if fc:
            fclasses[str(fc)] = fclasses.get(str(fc), 0) + 1
    n429 = by_status.get("429", 0)
    return {
        "requests": len(records),
        "by_status": by_status,
        "count_429": n429,
        "rate_429": round(n429 / len(records), 4) if records else None,
        "retry_after_values": sorted(
            {r.get("retry_after") for r in records if r.get("retry_after")}
        ),
        "failure_classes": fclasses,
        "successes": sum(1 for r in records if r.get("success") is True),
        "ttfb_s": {
            "min": pct(ttfbs, 0),
            "p50": pct(ttfbs, 50),
            "p90": pct(ttfbs, 90),
            "p99": pct(ttfbs, 99),
            "max": pct(ttfbs, 100),
            "mean": round(statistics.fmean(ttfbs), 3) if ttfbs else None,
        },
        "total_s": {
            "min": pct(totals, 0),
            "p50": pct(totals, 50),
            "p90": pct(totals, 90),
            "max": pct(totals, 100),
        },
        "wall_s": round(wall_s, 3),
        # sum(duration)/wall — the same quantity ContainerAppHTTPLogs gives, so
        # the client-side and server-side concurrency figures can be cross-checked
        # against each other. Two instruments, per CLAUDE.md.
        "client_observed_concurrency": (
            round(sum(totals) / wall_s, 2) if totals and wall_s > 0 else None
        ),
    }


def print_table(
    label: str, summary: Dict[str, Any], records: List[Dict[str, Any]]
) -> None:
    # Every numeric goes through str() before a width spec: on a run where every
    # request fails at the transport layer these are all None, and
    # format(None, '<7') raises TypeError — i.e. the reporting would crash on
    # exactly the run whose report matters most.
    def c(v: Any, w: int = 7) -> str:
        return f"{'-' if v is None else v:<{w}}"

    print()
    print("=" * 72)
    print(f"  BURST SUMMARY — {label}")
    print("=" * 72)
    print(f"  requests             {summary['requests']}")
    print(f"  wall time            {summary['wall_s']} s")
    print(
        f"  observed concurrency {c(summary['client_observed_concurrency'], 8)}"
        f" (sum(dur)/wall)"
    )
    print()
    print("  status        count")
    print("  ------------  -----")
    for status, count in sorted(summary["by_status"].items()):
        flag = "   <-- 429" if status == "429" else ""
        print(f"  {status:<12}  {count:>5}{flag}")
    print()
    if summary["rate_429"] is not None:
        print(
            f"  429 count            {summary['count_429']}  "
            f"({summary['rate_429']:.1%} of burst)"
        )
    if summary["retry_after_values"]:
        print(f"  Retry-After seen     {summary['retry_after_values']}")
    if summary["failure_classes"]:
        print(f"  failure_class        {summary['failure_classes']}")
    print(f"  successes            {summary['successes']}")
    print()
    t = summary["ttfb_s"]
    print("  TTFB (s)      min     p50     p90     p99     max     mean")
    print(
        f"                {c(t['min'])} {c(t['p50'])} {c(t['p90'])} "
        f"{c(t['p99'])} {c(t['max'])} {c(t['mean'])}"
    )
    d = summary["total_s"]
    print(
        f"  total (s)     {c(d['min'])} {c(d['p50'])} {c(d['p90'])} "
        f"{c(None)} {c(d['max'])}"
    )
    print()
    print("  per-request (idx, sent+s, status, ttfb, total, class)")
    for r in sorted(records, key=lambda x: x["idx"]):
        print(
            f"    {r['idx']:>3}  +{r['sent_at_offset_s']:<6} {str(r.get('status')):<5} "
            f"{str(r.get('ttfb_s')):<8} {str(r.get('total_s')):<8} "
            f"{r.get('failure_class') or r.get('error') or ''}"
        )
    print("=" * 72)


# ───────────────────────── main ─────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Cold-start burst probe for the ACA scale-rule change.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--n",
        type=int,
        default=12,
        help="burst size (concurrent requests). Default 12 (MAS flag 3).",
    )
    ap.add_argument(
        "--rounds", type=int, default=1, help="number of bursts. Max 3, hard."
    )
    ap.add_argument(
        "--round-gap-s",
        type=float,
        default=120.0,
        help="seconds between rounds (default 120).",
    )
    ap.add_argument(
        "--label",
        required=False,
        default=None,
        help="run label, e.g. 'before-c2' / 'after-c4'. Goes in the filename.",
    )
    ap.add_argument(
        "--target-url",
        default=None,
        help="live URL to crawl INSTEAD of the raw:// payload. "
        "Requires --allow-live-target. Prefer not to.",
    )
    ap.add_argument(
        "--allow-live-target",
        action="store_true",
        help="acknowledge TESTING.md golden rule 0 for --target-url.",
    )
    ap.add_argument(
        "--render-s",
        type=float,
        default=None,
        help=f"target per-render wall time in seconds. Default "
        f"{MAS_P50_RENDER_S} (MAS production p50). Translated to "
        f"delay_before_return_html by subtracting the measured "
        f"{RAW_RENDER_OVERHEAD_S}s pipeline overhead.",
    )
    ap.add_argument(
        "--payload-kb",
        type=int,
        default=8,
        help="size of the synthetic raw:// page in KiB (default 8).",
    )
    ap.add_argument(
        "--endpoint", default=os.getenv("CRAWL4AI_API_URL", DEFAULT_ENDPOINT)
    )
    ap.add_argument(
        "--timeout-s",
        type=float,
        default=180.0,
        help="client timeout per request (default 180, the wall-clock fence).",
    )
    ap.add_argument("--outdir", default=".", help="where to write the JSON artifact.")
    ap.add_argument(
        "--allow-warm",
        action="store_true",
        help="run even if the app is not at zero replicas. "
        "The result is then NOT a cold-start measurement.",
    )
    ap.add_argument(
        "--skip-replica-check",
        action="store_true",
        help="do not shell out to az at all.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and the exact request body; send nothing.",
    )
    ap.add_argument(
        "--i-know-what-im-doing", action="store_true", help="required for --n above 20."
    )
    args = ap.parse_args()

    # ---- hard safety caps -------------------------------------------------
    if args.rounds > 3:
        return fail(
            "--rounds above 3 is refused. Three bursts is already more "
            "load than this question needs; if you think you need more, "
            "the instrument is wrong, not the cap."
        )
    if args.rounds < 1:
        return fail("--rounds must be at least 1.")
    if args.n > 20 and not args.i_know_what_im_doing:
        return fail(
            f"--n {args.n} exceeds the safety cap of 20. The task file's "
            "own reasoning: N should bracket MAS's real shape (~12 at flag 3, "
            "~16 at flag 4), not stress the fleet. Pass "
            "--i-know-what-im-doing if you have a reason."
        )
    if args.n < 1:
        return fail("--n must be at least 1.")

    # ---- target -----------------------------------------------------------
    if args.target_url:
        if not args.allow_live_target:
            return fail(
                "--target-url points at a real host.\n\n"
                "  TESTING.md golden rule 0: live traffic is the last instrument,\n"
                "  not the first. This question does not need a third party at all —\n"
                "  the default raw:// payload exercises the identical render path\n"
                "  (RenderGate, browser launch, consent pass, markdown, collapse\n"
                "  guard) with zero egress, and it lets you PIN the render duration,\n"
                "  which a third party does not.\n\n"
                "  If you really need a live target, pass --allow-live-target and\n"
                "  record the host in TEST_SITES_REGISTRY.md in the same session."
            )
        target = args.target_url
        target_kind = "live"
    else:
        target = build_raw_payload(args.payload_kb, args.label or "probe")
        target_kind = "raw"

    render_s = args.render_s if args.render_s is not None else MAS_P50_RENDER_S
    delay = max(0.0, round(render_s - RAW_RENDER_OVERHEAD_S, 3))
    body = build_request_body(target, delay)

    label = args.label or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")

    # ---- plan -------------------------------------------------------------
    print("=" * 72)
    print("  COLD-START BURST PROBE — tasks/autoscaler-ratchets-to-the-cap.md")
    print("=" * 72)
    print(f"  label            {label}")
    print(f"  endpoint         {args.endpoint}")
    print(
        f"  target kind      {target_kind}"
        + (
            f"  ({len(target)} B raw payload, ~{args.payload_kb} KiB page)"
            if target_kind == "raw"
            else f"  {target}"
        )
    )
    print(f"  burst size N     {args.n}")
    print(f"  rounds           {args.rounds} (gap {args.round_gap_s}s)")
    print(f"  target render    {render_s}s  -> delay_before_return_html={delay}")
    print(f"  client timeout   {args.timeout_s}s")
    print()
    print("  request body (token NOT shown; it goes in the Authorization header):")
    shown = json.loads(json.dumps(body))
    if target_kind == "raw":
        shown["urls"] = [target[:80] + f"... [{len(target)} B total]"]
    for line in json.dumps(shown, indent=2).splitlines():
        print("    " + line)
    print()

    scale = None if args.skip_replica_check else read_scale_rule()
    if scale:
        rules = scale.get("rules") or []
        conc = None
        for r in rules:
            if (r.get("http") or {}).get("metadata"):
                conc = r["http"]["metadata"].get("concurrentRequests")
        print(
            f"  scale rule       min={scale.get('minReplicas')} "
            f"max={scale.get('maxReplicas')} concurrentRequests={conc}"
        )

    # ---- token ------------------------------------------------------------
    token = os.getenv("CRAWL4AI_API_TOKEN")
    if not token:
        return fail(
            "CRAWL4AI_API_TOKEN is not set.\n"
            "  It lives in the repo's gitignored .env. Load it without echoing it:\n"
            "      set -a; source .env; set +a\n"
            "  This script never prints, logs or stores the token."
        )
    print(f"  token            present ({len(token)} chars, not shown)")

    if args.dry_run:
        print()
        print("  --dry-run: nothing was sent.")
        print("=" * 72)
        return 0

    # ---- cold-state gate --------------------------------------------------
    if not args.skip_replica_check:
        print()
        print("  checking replica state ...")
        replicas = read_active_replicas()
        if replicas is None:
            if not args.allow_warm:
                return fail(
                    "could not determine replica count and --allow-warm "
                    "was not given. Re-run with --allow-warm (and say so "
                    "in the writeup) or fix `az` access."
                )
            print("  ! replica count unknown; continuing because --allow-warm.")
        else:
            print(f"  active replicas  {replicas}")
            if replicas != 0 and not args.allow_warm:
                return fail(
                    f"the app is WARM ({replicas} replicas). This probe measures "
                    "cold start;\n"
                    "  running it warm measures something else and the before/after "
                    "diff would be\n"
                    "  meaningless.\n\n"
                    "  To drain: stop sending traffic and wait. Scale-down from a "
                    "burst took over\n"
                    "  twenty minutes in segment 3, so budget for it. Re-check with:\n"
                    "      az containerapp revision list -n crawl4ai-service "
                    "-g aitosoft-prod \\\n"
                    "        --query "
                    '"[?properties.active].properties.replicas" -o tsv\n\n'
                    "  NOTE: a single /health request wakes the app (measured "
                    "2026-08-08: a cold\n"
                    "  /health returned in 10.09s and left 2 replicas running). Do "
                    "not poll /health\n"
                    "  while waiting for the drain — you will keep it warm and, worse, "
                    "you will be\n"
                    "  feeding the very scaler you are trying to measure.\n\n"
                    "  Pass --allow-warm to run anyway (warm-burst arm)."
                )

    # ---- fire -------------------------------------------------------------
    started = datetime.now(timezone.utc)
    all_records: List[Dict[str, Any]] = []
    round_summaries: List[Dict[str, Any]] = []

    for round_no in range(1, args.rounds + 1):
        if round_no > 1:
            print(f"\n  waiting {args.round_gap_s}s before round {round_no} ...")
            time.sleep(args.round_gap_s)
        print(
            f"\n  round {round_no}/{args.rounds}: firing {args.n} concurrent "
            f"POST {args.endpoint}/crawl ..."
        )
        t0 = time.perf_counter()
        records = asyncio.run(
            run_round(args.endpoint, body, token, args.n, round_no, args.timeout_s)
        )
        wall = time.perf_counter() - t0
        summary = summarise(records, wall)
        print_table(f"{label} round {round_no}", summary, records)
        all_records.extend(records)
        round_summaries.append({"round": round_no, **summary})

    ended = datetime.now(timezone.utc)

    replicas_after = None if args.skip_replica_check else read_active_replicas()
    if replicas_after is not None:
        print(f"\n  replicas immediately after the burst: {replicas_after}")
        print("  (this is a floor, not the high-water mark — read the KQL for that)")

    # ---- artifact ---------------------------------------------------------
    artifact = {
        "schema": "cold_burst_probe/1",
        "label": label,
        "started_utc": started.isoformat().replace("+00:00", "Z"),
        "ended_utc": ended.isoformat().replace("+00:00", "Z"),
        "endpoint": args.endpoint,
        "config": {
            "n": args.n,
            "rounds": args.rounds,
            "round_gap_s": args.round_gap_s,
            "target_kind": target_kind,
            "target_url": args.target_url,
            "payload_kb": args.payload_kb if target_kind == "raw" else None,
            "payload_bytes": len(target) if target_kind == "raw" else None,
            "target_render_s": render_s,
            "delay_before_return_html": delay,
            "timeout_s": args.timeout_s,
            "allow_warm": args.allow_warm,
        },
        # The independent variable, captured so two artifacts are comparable
        # without trusting the label.
        "scale_at_run": scale,
        "replicas_after": replicas_after,
        "crawler_config_sent": body["crawler_config"],
        "rounds": round_summaries,
        "aggregate": summarise(all_records, (ended - started).total_seconds()),
        "records": all_records,
        # The window to paste into cold_burst_probe.kql. Padded: Log Analytics
        # ingestion lags several minutes, and the scale-down tail is the half of
        # the curve this task actually cares about.
        "kql_window": {
            "from": (started.isoformat().replace("+00:00", "Z")),
            "to": ended.isoformat().replace("+00:00", "Z"),
            "suggested_to_for_rampdown": "add 30 minutes to 'to'",
        },
    }
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    outfile = outdir / f"burst-{label}-n{args.n}-{stamp}.json"
    outfile.write_text(json.dumps(artifact, indent=2))
    print(f"\n  artifact -> {outfile}")
    print("\n  NEXT: wait ~5 minutes for Log Analytics ingestion, then run the")
    print("  queries in cold_burst_probe.kql over the window in kql_window.")
    print("  The client side alone cannot tell you the replica high-water mark.")
    return 0


def fail(msg: str) -> int:
    print(f"\nREFUSING TO RUN: {msg}\n", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
