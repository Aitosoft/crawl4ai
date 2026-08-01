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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--browsers", type=int, default=8)
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

    url = origin.url("/ok")
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
    path.close()
    time.sleep(3)
    snapshot("4 pool closed", pool_sizes())
    origin.stop()

    n = args.browsers
    print(f"\n--- per pooled browser, over {n} browsers ---")
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

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(ROWS, fh, indent=2)
        print(f"\n  samples -> {args.json}")


if __name__ == "__main__":
    main()
