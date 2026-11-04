#!/usr/bin/env bash
# Aitosoft: replica-minutes for a window, summed across revisions. Read-only (Azure Monitor only).
#
# Usage: ./azure-deployment/replica-minutes.sh <t0> <t1> [t2] [app]
#   t0..t1 is the window (MAS's start and end); t1..t2 is the tail after it (default t1 + 20 min).
#   Prints the per-minute fleet (one column per revision) and the two totals with their price.
#
# Why split by revision: the unsplit Replicas series AVERAGES overlapping revisions instead of
# adding them, so every deploy or minReplicas change under-reads (AZURE_OPERATIONS.md §4.4).
# Price: $0.3024 per replica-hour, active rate (§4.2). A replica idle at a pinned minimum may bill
# at the idle rate instead (§4.3, never measured here), so for a pinned window this is an upper bound.
set -euo pipefail
T0="${1:?t0}"; T1="${2:?t1}"
T2="${3:-$(date -u -d "$T1 + 20 minutes" +%Y-%m-%dT%H:%M:%SZ)}"; APP="${4:-crawl4ai-service-se}"
RID="$(az containerapp show -n "$APP" -g aitosoft-prod --query id -o tsv)"
az monitor metrics list --resource "$RID" --metric Replicas --interval PT1M --aggregation Average \
  --start-time "$T0" --end-time "$T2" --filter "revisionName eq '*'" -o json |
python3 -c '
import json, sys
t1 = sys.argv[1].replace("Z", "")[:16]
d = json.load(sys.stdin)
series = {}
for ts in d["value"][0]["timeseries"]:
    rev = next((m["value"] for m in ts["metadatavalues"]), "?").rsplit("--", 1)[-1]
    series[rev] = {p["timeStamp"][:16]: (p.get("average") or 0.0) for p in ts["data"]}
revs = sorted(series)
minutes = sorted({m for s in series.values() for m in s})
win = tail = 0.0
print("minute  " + "  ".join(f"{r:>9}" for r in revs) + "    sum")
for m in minutes:
    vals = [series[r].get(m, 0.0) for r in revs]
    s = sum(vals)
    if m < t1: win += s
    else: tail += s
    if s: print(f"{m[11:16]}   " + "  ".join(f"{v:9.2f}" for v in vals) + f"  {s:5.2f}")
usd = lambda x: x / 60 * 0.3024
print(f"window {win:.1f} replica-min (${usd(win):.3f})  tail {tail:.1f} (${usd(tail):.3f})  "
      f"total {win + tail:.1f} (${usd(win + tail):.3f})")
' "$T1"
