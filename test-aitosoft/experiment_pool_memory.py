#!/usr/bin/env python3
"""
tasks/render-500-window-2026-07-31.md §"The 235 MB was never the container" —
what the memory guard reads vs what the server process reports.

The question: MAS's nine HTTP 500s carried a cgroup reading of 85.1–95.6 % and a
`server_peak_memory_mb` of 204–235 MB on a 4 GiB replica. Those look
contradictory. Are they measuring the same memory, and if not, how much of the
container does each one see?

The answer this produces: **a pooled browser moves the server process's RSS by
~2 MB and the cgroup by ~165 MB** (~130 anon, ~27 page cache), because
`api._get_memory_mb()` is `psutil.Process().memory_info().rss` of the single
gunicorn worker while Chrome is ~7 descendant processes. So the two numbers were
never in conflict, the guard's reading is roughly right, and `inactive_file` is
~16 % of the growth rather than the explanation.

This is an EXPERIMENT, not a test. No assertions. Absolute MB are machine- and
page-dependent — the *ratios* are the result, not the numbers.

OFFLINE. Every request goes to the loopback fixture origin (fixture_origin.py)
through the real production path — `aitosoft_entry` -> `api.handle_crawl_request`
-> a pool browser. No customer site is contacted; TESTING.md golden rule 0.

    python test-aitosoft/experiment_pool_memory.py            # 8 browsers
    python test-aitosoft/experiment_pool_memory.py -n 12      # more

2026-08-02, tasks/pool-residency-unbounded.md: **the route is now an argument,
and the default is no longer `/ok`.** The 139-165 MB figure above was taken
against `/ok` — 1.2 KB of markup, no images — and then used as the per-browser
cost that a `max_browsers` cap would be derived from. A cap sized from a page
200x smaller than the median page we actually crawl is a cap sized from a floor.
`/heavy` is the median shape of our own 62 stored captures (236 KB, 17 images,
~900 tags), and the decoded-image term it adds is invisible to any markup-only
fixture: a PNG that costs 3 KB on the wire still allocates `w*h*4` in the
renderer.

    python test-aitosoft/experiment_pool_memory.py --route /ok       # the old figure
    python test-aitosoft/experiment_pool_memory.py --route /heavy    # default
    python test-aitosoft/experiment_pool_memory.py --blank           # price retention

`--blank` prices tasks/pool-browser-retains-last-page.md **without changing the
code first**: every pool browser keeps its last page open forever (upstream
declines to close the final page of a headless browser), so navigating those
retained pages to about:blank and re-reading the cgroup is exactly the saving
that task proposes, measured rather than argued.

What it does NOT reproduce: the guard firing. `get_container_memory_percent()`
(deploy/docker/utils.py) divides by `memory.max`, and a dev container's
`memory.max` is the string "max" — `int()` raises, the bare `except` catches,
and the function silently falls back to `psutil.virtual_memory().percent`. The
cgroup branch that ran in production is not exercised here. Any test of the
threshold must fake the file reads; do not infer it from a local run.

Each crawl gets a DISTINCT `browser_config` (a different user_agent), which is
MAS's per-company contract, so `crawler_pool._sig` differs every time and a new
browser is created per request. That is the shape that produced 125 "Creating
new browser" against 99 reuses in the 2026-07-31 probe.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "deploy",
        "docker",
    ),
)

import psutil  # noqa: E402

CG = "/sys/fs/cgroup"
MB = 1024 * 1024

#: memory.stat keys worth separating. `anon` is what the kernel cannot reclaim;
#: `inactive_file` is the page cache the standard working-set correction drops.
STAT_KEYS = ("anon", "file", "inactive_file", "active_file", "shmem", "kernel")


def cgroup_stat() -> Dict[str, Any]:
    """cgroup v2 memory.current + the memory.stat keys above. {} if unavailable."""
    out: Dict[str, Any] = {}
    try:
        with open(f"{CG}/memory.current") as fh:
            out["current"] = int(fh.read())
        stat = {}
        with open(f"{CG}/memory.stat") as fh:
            for line in fh:
                key, _, value = line.partition(" ")
                stat[key] = int(value)
        for key in STAT_KEYS:
            out[key] = stat.get(key, 0)
    except Exception as exc:
        out["error"] = str(exc)
    return out


def tree_rss() -> tuple[int, int]:
    """RSS of this process plus every descendant, and the process count.

    Deliberately reported alongside the cgroup figure: summing RSS across
    Chrome's process group counts its shared mappings once per process, so this
    number is ~3x the cgroup's. It is here to be visibly wrong, not to be used.
    """
    me = psutil.Process()
    total = me.memory_info().rss
    count = 1
    for child in me.children(recursive=True):
        try:
            total += child.memory_info().rss
            count += 1
        except psutil.Error:
            pass
    return total, count


ROWS: list[dict] = []


def snapshot(label: str, pool: str | None = None) -> dict:
    rss = psutil.Process().memory_info().rss
    tree, nproc = tree_rss()
    cg = cgroup_stat()
    row = {
        "label": label,
        "rss_mb": rss / MB,
        "tree_mb": tree / MB,
        "nproc": nproc,
        "cur_mb": cg.get("current", 0) / MB,
        **{f"{k}_mb": cg.get(k, 0) / MB for k in STAT_KEYS},
        "pool": pool,
    }
    ROWS.append(row)
    print(
        f"{label:<22} rss={row['rss_mb']:7.1f}  tree={row['tree_mb']:8.1f}"
        f" ({nproc:3d}p)  cgroup={row['cur_mb']:8.1f}"
        f"  anon={row['anon_mb']:8.1f}  file={row['file_mb']:7.1f}"
        f" (inact {row['inactive_file_mb']:7.1f})   {pool or ''}",
        flush=True,
    )
    return row


def retained_pages(crawler) -> list:
    """Every still-open page held by a pooled browser.

    The pool hands out `AsyncWebCrawler`s; the retained tab lives four levels
    down. Wrapped in a try because a browser that failed to start has none of
    this, and this is an experiment — it must degrade to "0 pages", never raise.
    """
    try:
        browser = crawler.crawler_strategy.browser_manager.browser
        return [page for ctx in browser.contexts for page in ctx.pages]
    except Exception:
        return []


def all_pooled(crawler_pool) -> list:
    out = []
    if crawler_pool.PERMANENT:
        out.append(crawler_pool.PERMANENT)
    out.extend(crawler_pool.HOT_POOL.values())
    out.extend(crawler_pool.COLD_POOL.values())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--browsers", type=int, default=8)
    ap.add_argument(
        "--route",
        default="/heavy",
        help="fixture route to crawl (/ok is the 1.2 KB page the old figure used)",
    )
    ap.add_argument(
        "--blank",
        action="store_true",
        help="after settling, navigate every retained page to about:blank and "
        "re-measure — prices pool-browser-retains-last-page.md",
    )
    ap.add_argument("--json", help="write the raw samples here")
    args = ap.parse_args()

    from fixture_origin import FixtureOrigin, ProductionPath

    origin = FixtureOrigin()
    origin.start()
    print(f"fixture origin at {origin.base_url}\n", flush=True)

    snapshot("0 before import")
    path = ProductionPath()
    base = snapshot("1 entry imported")

    import crawler_pool

    def pool_sizes() -> str:
        return (
            f"perm={'y' if crawler_pool.PERMANENT else 'n'} "
            f"hot={len(crawler_pool.HOT_POOL)} cold={len(crawler_pool.COLD_POOL)}"
        )

    url = origin.base_url + args.route
    print(f"crawling {url}\n", flush=True)
    for i in range(args.browsers):
        browser_config = {
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/138.0.{i}.0 Safari/537.36"
            ),
            "viewport_width": 1920,
            "viewport_height": 1080,
        }
        out = path.crawl(
            url, browser_config=browser_config, delay_before_return_html=0.2
        )
        if out.http_status != 200:
            print(f"  ! HTTP {out.http_status}: {out.detail}", flush=True)
        snapshot(f"2.{i} browser #{i + 1}", pool_sizes())

    time.sleep(3)
    peak = snapshot("3 settled", pool_sizes())
    # Capture this BEFORE path.close() clears the pools.
    resident = len(crawler_pool.HOT_POOL) + len(crawler_pool.COLD_POOL)

    pages = sum(len(retained_pages(c)) for c in all_pooled(crawler_pool))
    print(f"\n  retained pages across the pool: {pages}", flush=True)

    blanked = None
    if args.blank:

        async def blank_them():
            done = 0
            for crawler in all_pooled(crawler_pool):
                for page in retained_pages(crawler):
                    try:
                        await page.goto("about:blank")
                        done += 1
                    except Exception as exc:
                        print(f"  ! about:blank failed: {exc}", flush=True)
            return done

        moved = path._loop.run_until_complete(blank_them())
        time.sleep(10)  # V8/Blink return pages lazily; 3 s is not enough to say "no"
        blanked = snapshot(f"3b {moved} pages blanked", pool_sizes())

    path.close()
    time.sleep(3)
    snapshot("4 pool closed", pool_sizes())
    origin.stop()

    # Divide by browsers RESIDENT at the peak, not by how many were created.
    # Since max_browsers landed (2026-08-02) those differ: 12 crawls with
    # distinct signatures against a cap of 6 leave 6 alive, and dividing the
    # growth by 12 halves the per-browser figure silently. The divisor being
    # wrong in the direction that flatters the cap is exactly the kind of
    # instrument error that gets a capacity number believed.
    n = max(1, resident)
    if n != args.browsers:
        print(
            f"\n  NOTE: {args.browsers} crawls created browsers but only {n} are "
            f"resident (max_browsers={crawler_pool.MAX_BROWSERS}); "
            f"dividing by {n}"
        )
    print(f"\n--- per pooled browser, over {n} resident browsers ---")
    for key, note in (
        ("rss_mb", "<- what server_peak_memory_mb reports"),
        ("cur_mb", "<- what the memory guard reads"),
        ("anon_mb", ""),
        ("file_mb", ""),
        ("inactive_file_mb", ""),
        ("tree_mb", "<- sum-of-RSS, inflated by shared mappings"),
    ):
        print(f"  {key:<18} {(peak[key] - base[key]) / n:+8.1f} MB   {note}")

    growth = peak["cur_mb"] - base["cur_mb"]
    if growth > 0:
        cache = (peak["inactive_file_mb"] - base["inactive_file_mb"]) / growth
        print(f"\n  inactive_file is {cache * 100:.0f}% of the cgroup growth")

    if blanked is not None:
        print(f"\n--- retained page, per browser (route {args.route}) ---")
        for key in ("cur_mb", "anon_mb", "rss_mb"):
            print(f"  {key:<18} {(blanked[key] - peak[key]) / n:+8.1f} MB")
        print(
            "  (negative = memory the retained page was holding and the\n"
            "   about:blank navigation gave back — that is the fix's saving)"
        )

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(ROWS, fh, indent=2)
        print(f"\n  samples -> {args.json}")


if __name__ == "__main__":
    main()
