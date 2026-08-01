#!/usr/bin/env python3
"""
Phase 1 of tasks/challenge-interstitial-resolve.md — the capture-timing sweep.

The question: when a challenge interstitial resolves into the real page, does
our pipeline capture the interstitial or the page? And if the capture wait
decides it, where is the boundary and what does raising it cost?

This is an EXPERIMENT, not a test. It has no assertions and no pass/fail; it
produces a CSV and four tables. Tests pin behaviour we have decided on; this
measures behaviour we have not. When phase 1's conclusions become behaviour we
want to keep, they belong in test_fixture_origin.py, not here.

OFFLINE. Every request goes to the loopback fixture origin (fixture_origin.py)
through the real production path — `aitosoft_entry` -> `api.handle_crawl_request`
-> a pool browser -> the patchright retry -> the wall-clock fence. No customer
site is contacted; TESTING.md golden rule 0.

    python test-aitosoft/experiment_challenge_capture.py                 # all blocks
    python test-aitosoft/experiment_challenge_capture.py --block A B     # a subset
    python test-aitosoft/experiment_challenge_capture.py --repeat 3 --block A

Blocks:

    A  crossover   resolve delay R x capture wait W x {resolve-after, resolve-by-nav}
    B  tax         what a raised W costs on a wall and on a healthy page
    C  families    the marker variants, incl. the unmarked interstitial
    D  adaptive    detect-then-recapture simulated against a raised global wait

Units, because mixing them has already cost a round trip (README cross-repo
state): `html` and `cleaned_html` are HTML **bytes**; `markdown` is markdown
**characters**, which is the unit of MAS's DEGENERATE_CAPTURE_CHARS = 500.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixture_origin import CONTENT_MARKER, FixtureOrigin, ProductionPath  # noqa: E402

# ── the grid ─────────────────────────────────────────────────────────────
# Both axes are in seconds.
#
# W (capture wait) brackets MAS's production value on both sides: 0.1 is the
# change they refuted, 2.0 is what they send, 10.0 is what they were considering.
# R (challenge resolve delay) brackets their own `raw://` measurement, which says
# 2.0 tolerates a paint of roughly 3-5 s.

WAITS = [0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
RESOLVES = [0.5, 1.0, 2.0, 3.0, 5.0, 8.0]
ROUTES = ["resolve-after", "resolve-by-nav"]

#: The wait a phase-2 re-capture would use, for block D.
RECAPTURE_WAIT = 5.0

#: Budgets. config.yml ships 180 s / 100 000 ms; these are shortened but stay
#: far above anything this grid can reach (W=10 + R=8 + the patchright retry),
#: and they are held CONSTANT across every cell so the budget can never be the
#: thing that varies.
WALL_CLOCK_S = 90
TOTAL_TIMEOUT_MS = 60000

#: What proves the interstitial survived into the capture, per `?marker=`.
#: Keyed the same way fixture_origin.CHALLENGE_MARKERS is.
INTERSTITIAL_FINGERPRINT = {
    "robot-suspicion": "One more step",
    "checking-browser": "Checking your browser",
    "none": "Odota hetki",
}

#: MAS's floor, in markdown characters.
DEGENERATE_CAPTURE_CHARS = 500


# ── one measurement ──────────────────────────────────────────────────────


@dataclass
class Cell:
    block: str
    route: str
    marker: str
    resolve_s: Optional[float]
    wait_s: float
    # what came back
    http_status: int = 0
    success: bool = False
    failure_class: str = ""
    status_code: Optional[int] = None
    html_bytes: int = 0
    cleaned_html_bytes: int = 0
    markdown_chars: int = 0
    content: bool = False  # the real page's marker is in the markdown
    interstitial: bool = False  # the challenge markup is still in the html
    origin_hits: int = 0  # document loads the origin served
    elapsed_s: float = 0.0
    note: str = ""

    @property
    def verdict(self) -> str:
        """One character per cell, so a 7x6 grid reads at a glance."""
        if self.content:
            return "+"  # the real page
        if self.interstitial:
            return "i"  # the interstitial, stored as the result
        return "?"  # neither — read the row


def _run(
    path: ProductionPath,
    origin: FixtureOrigin,
    *,
    block: str,
    url_route: str,
    route_label: str,
    marker: str,
    resolve_s: Optional[float],
    wait_s: float,
    params: Optional[Dict[str, Any]] = None,
) -> Cell:
    cell = Cell(block, route_label, marker, resolve_s, wait_s)

    url = origin.url(url_route, marker=marker, **(params or {}))
    origin.reset_hits()
    outcome = path.crawl(
        url,
        delay_before_return_html=wait_s,
        wall_clock_s=WALL_CLOCK_S,
        total_timeout_ms=TOTAL_TIMEOUT_MS,
    )

    cell.http_status = outcome.http_status
    cell.elapsed_s = round(outcome.elapsed_s, 2)
    # Assets are not page loads; the interstitial pulls one script and counting
    # it would misreport what a challenge costs the origin.
    cell.origin_hits = sum(1 for p in origin.hits if not p.startswith("/assets/"))

    if outcome.envelope is None:
        cell.note = f"no envelope: {outcome.detail!r}"[:120]
        return cell

    result = outcome.result
    html = outcome.html
    cell.success = outcome.success
    cell.failure_class = outcome.failure_class or ""
    cell.status_code = outcome.status_code
    cell.html_bytes = len(html)
    cell.cleaned_html_bytes = len(result.get("cleaned_html") or "")
    cell.markdown_chars = len(outcome.markdown)
    cell.content = CONTENT_MARKER in outcome.markdown
    cell.interstitial = INTERSTITIAL_FINGERPRINT[marker] in html
    return cell


def would_recapture(cell: Cell) -> bool:
    """The trigger a phase-2 detect-then-re-capture would fire on.

    Deliberately only the detector's verdict. The other candidate trigger — a
    capture below MAS's DEGENERATE_CAPTURE_CHARS — cannot be evaluated on this
    fixture: `fixture_origin.CONTENT_HTML` renders to 149 markdown characters
    (measured 2026-08-01), so a *successful* capture is below the floor too. That
    is a property of the fixture, not of production, and it is recorded rather
    than worked around — see TESTING.md and tasks/cleaned-html-collapse-guard.md,
    which needs the content page grown before it can measure its own threshold.
    """
    return cell.failure_class == "origin_blocked"


# ── the blocks ───────────────────────────────────────────────────────────


def block_a(path, origin, repeat: int) -> List[Cell]:
    """Where does the capture start winning, and does navigation differ?"""
    cells = []
    for route in ROUTES:
        for resolve_s in RESOLVES:
            for wait_s in WAITS:
                for _ in range(repeat):
                    cells.append(
                        _run(
                            path,
                            origin,
                            block="A",
                            url_route=f"/challenge/{route}/{resolve_s}",
                            route_label=route,
                            marker="robot-suspicion",
                            resolve_s=resolve_s,
                            wait_s=wait_s,
                        )
                    )
                    _progress(cells[-1])
    return cells


def block_b(path, origin, repeat: int) -> List[Cell]:
    """What a raised global wait costs — on a wall it cannot rescue, and on the
    healthy page that is ~97 % of the corpus."""
    cells = []
    for wait_s in WAITS:
        for _ in range(repeat):
            cells.append(
                _run(
                    path,
                    origin,
                    block="B",
                    url_route="/challenge/never",
                    route_label="never",
                    marker="robot-suspicion",
                    resolve_s=None,
                    wait_s=wait_s,
                )
            )
            _progress(cells[-1])
            cells.append(
                _run(
                    path,
                    origin,
                    block="B",
                    url_route="/ok",
                    route_label="ok",
                    marker="none",  # /ok has no interstitial; the param is inert
                    resolve_s=None,
                    wait_s=wait_s,
                )
            )
            _progress(cells[-1])
    return cells


def block_c(path, origin, repeat: int) -> List[Cell]:
    """The other two families, and the silent one.

    `marker=none` is the interstitial the detector cannot see. If a longer wait
    is the only thing that rescues it, that is an argument a detector-triggered
    re-capture cannot answer.
    """
    cells = []
    for marker in ("checking-browser", "none"):
        for wait_s in (0.1, 2.0, 10.0):
            for _ in range(repeat):
                cells.append(
                    _run(
                        path,
                        origin,
                        block="C",
                        url_route="/challenge/resolve-after/5.0",
                        route_label="resolve-after",
                        marker=marker,
                        resolve_s=5.0,
                        wait_s=wait_s,
                    )
                )
                _progress(cells[-1])
                cells.append(
                    _run(
                        path,
                        origin,
                        block="C",
                        url_route="/challenge/never",
                        route_label="never",
                        marker=marker,
                        resolve_s=None,
                        wait_s=wait_s,
                    )
                )
                _progress(cells[-1])
    return cells


@dataclass
class Adaptive:
    route: str
    resolve_s: float
    first: Cell
    second: Optional[Cell] = None

    @property
    def fired(self) -> bool:
        return self.second is not None

    @property
    def content(self) -> bool:
        return (self.second or self.first).content

    @property
    def elapsed_s(self) -> float:
        return round(
            self.first.elapsed_s + (self.second.elapsed_s if self.second else 0), 2
        )

    @property
    def origin_hits(self) -> int:
        return self.first.origin_hits + (self.second.origin_hits if self.second else 0)


def block_d(path, origin, repeat: int) -> List[Cell]:
    """Detect-then-re-capture, simulated at the harness level.

    Crawl at the shortest wait; if the detector says blocked, crawl again at
    RECAPTURE_WAIT. Compare against block A's single crawl at RECAPTURE_WAIT.

    The simulation is an UPPER BOUND on what phase 2 would cost: it re-navigates,
    where phase 2 re-captures inside the same render. For `resolve-by-nav` that
    difference is not only cost — a re-navigation restarts the challenge clock,
    so the second attempt waits out the full R again. Read the two shapes apart
    before quoting this block.
    """
    cells = []
    for route in ROUTES:
        for resolve_s in RESOLVES:
            for _ in range(repeat):
                first = _run(
                    path,
                    origin,
                    block="D",
                    url_route=f"/challenge/{route}/{resolve_s}",
                    route_label=route,
                    marker="robot-suspicion",
                    resolve_s=resolve_s,
                    wait_s=0.1,
                )
                first.note = "adaptive:first"
                cells.append(first)
                _progress(first)

                if would_recapture(first):
                    second = _run(
                        path,
                        origin,
                        block="D",
                        url_route=f"/challenge/{route}/{resolve_s}",
                        route_label=route,
                        marker="robot-suspicion",
                        resolve_s=resolve_s,
                        wait_s=RECAPTURE_WAIT,
                    )
                    second.note = "adaptive:recapture"
                    cells.append(second)
                    _progress(second)
    return cells


BLOCKS = {"A": block_a, "B": block_b, "C": block_c, "D": block_d}


# ── reporting ────────────────────────────────────────────────────────────


def _progress(cell: Cell) -> None:
    print(
        f"  {cell.block} {cell.route:<15} marker={cell.marker:<16} "
        f"R={cell.resolve_s if cell.resolve_s is not None else '-':<5} "
        f"W={cell.wait_s:<5} -> {cell.verdict} "
        f"http={cell.http_status} success={cell.success!s:<5} "
        f"class={cell.failure_class or '-':<14} "
        f"md={cell.markdown_chars:<6} hits={cell.origin_hits} "
        f"{cell.elapsed_s:>6.2f}s {cell.note}",
        flush=True,
    )


def _grid(cells: List[Cell], route: str) -> str:
    """The crossover grid: rows are resolve delay, columns are capture wait."""
    rows = [f"| R \\ W | {' | '.join(f'{w}' for w in WAITS)} |"]
    rows.append("|---|" + "|".join("---" for _ in WAITS) + "|")
    for resolve_s in RESOLVES:
        marks = []
        for wait_s in WAITS:
            here = [
                c
                for c in cells
                if c.block == "A"
                and c.route == route
                and c.resolve_s == resolve_s
                and c.wait_s == wait_s
            ]
            marks.append("".join(c.verdict for c in here) or ".")
        rows.append(f"| {resolve_s} | {' | '.join(marks)} |")
    return "\n".join(rows)


def report(cells: List[Cell]) -> str:
    out: List[str] = []
    have = {c.block for c in cells}

    if "A" in have:
        out.append(
            "## Block A — crossover grid  (`+` real page, `i` interstitial kept)\n"
        )
        for route in ROUTES:
            out.append(f"### /challenge/{route}\n")
            out.append(_grid(cells, route))
            out.append("")

    if "B" in have:
        out.append("## Block B — what a raised wait costs\n")
        out.append("| W | /challenge/never elapsed | class | /ok elapsed | class |")
        out.append("|---|---|---|---|---|")
        for wait_s in WAITS:
            never = [
                c
                for c in cells
                if c.block == "B" and c.route == "never" and c.wait_s == wait_s
            ]
            ok = [
                c
                for c in cells
                if c.block == "B" and c.route == "ok" and c.wait_s == wait_s
            ]
            if not never or not ok:
                continue
            n, o = never[0], ok[0]
            out.append(
                f"| {wait_s} | {n.elapsed_s:.2f} s | {n.failure_class} "
                f"| {o.elapsed_s:.2f} s | {o.failure_class} |"
            )
        out.append("")

    if "C" in have:
        out.append("## Block C — the families\n")
        out.append("| route | marker | W | verdict | success | class | md chars |")
        out.append("|---|---|---|---|---|---|---|")
        for c in [c for c in cells if c.block == "C"]:
            out.append(
                f"| {c.route} | {c.marker} | {c.wait_s} | {c.verdict} "
                f"| {c.success} | {c.failure_class} | {c.markdown_chars} |"
            )
        out.append("")

    if "D" in have:
        out.append("## Block D — adaptive vs global\n")
        out.append(
            "| route | R | first W=0.1 | fired | outcome | adaptive elapsed "
            "| adaptive hits |"
        )
        out.append("|---|---|---|---|---|---|---|")
        firsts = [c for c in cells if c.block == "D" and c.note == "adaptive:first"]
        seconds = [
            c for c in cells if c.block == "D" and c.note == "adaptive:recapture"
        ]
        for f in firsts:
            match = [
                s for s in seconds if s.route == f.route and s.resolve_s == f.resolve_s
            ]
            s = match[0] if match else None
            total = f.elapsed_s + (s.elapsed_s if s else 0)
            hits = f.origin_hits + (s.origin_hits if s else 0)
            outcome = (s or f).verdict
            out.append(
                f"| {f.route} | {f.resolve_s} | {f.verdict} | {bool(s)} "
                f"| {outcome} | {total:.2f} s | {hits} |"
            )
        out.append("")

    return "\n".join(out)


# ── entry point ──────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--block",
        nargs="*",
        default=list(BLOCKS),
        choices=list(BLOCKS),
        help="which blocks to run (default: all)",
    )
    parser.add_argument("--repeat", type=int, default=1, help="samples per cell")
    parser.add_argument(
        "--out",
        default="tmp/challenge-sweep",
        help="directory for results.csv and report.md",
    )
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    origin = FixtureOrigin().start()
    path = ProductionPath()
    print(f"fixture origin: {origin.base_url}   chrome channel: {path.channel}")
    print(f"blocks: {' '.join(args.block)}   repeat: {args.repeat}\n", flush=True)

    cells: List[Cell] = []
    try:
        for name in args.block:
            print(f"── block {name} ──", flush=True)
            cells.extend(BLOCKS[name](path, origin, args.repeat))
    finally:
        path.close()
        origin.stop()

        csv_path = os.path.join(args.out, "results.csv")
        with open(csv_path, "w", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=list(asdict(Cell("", "", "", None, 0)))
            )
            writer.writeheader()
            for cell in cells:
                writer.writerow(asdict(cell))

        text = report(cells)
        with open(os.path.join(args.out, "report.md"), "w") as fh:
            fh.write(text + "\n")

        print(f"\n{text}")
        print(f"\n{len(cells)} cells -> {csv_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
