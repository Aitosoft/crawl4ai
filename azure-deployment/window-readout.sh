#!/usr/bin/env bash
# Aitosoft: crawl4ai's side of one MAS run window, from Log Analytics. Read-only: never calls the app.
#
# Usage: LAW_ID=<workspace id, PRIVATE.md> ./azure-deployment/window-readout.sh <t0> <t1> [app]
#   t0/t1 are ISO UTC (e.g. 2026-11-04T09:29:30Z); app defaults to crawl4ai-service-se.
#
# What it prints and why (AZURE_OPERATIONS.md §3.8, §4.5, §5): wire statuses and latency (the
# truth MAS received), console signals (gate and memory 429s, anti-bot retries, Patchright rescues,
# browser launches), failures by failure_class (count the field, never a token), memory by replica
# (read anon, never the guard's percentage), platform events (scale, probes, OOM), failures by
# replica (egress is per replica), and every failure line for the per-URL join with MAS.
# HTTP rows arrive several minutes after console rows: re-run the first two queries before
# comparing totals with MAS. Replica-minutes for cost come from Azure Monitor, not from here:
#   az monitor metrics list --resource "$(az containerapp show -n "$APP" -g aitosoft-prod --query id -o tsv)" \
#     --metric Replicas --interval PT1M --aggregation Average --start-time <t0> --end-time <t1+15m>
set -uo pipefail
T0="${1:?t0}"; T1="${2:?t1}"; APP="${3:-crawl4ai-service-se}"
: "${LAW_ID:?set LAW_ID (PRIVATE.md)}"
W="where TimeGenerated between (datetime($T0) .. datetime($T1))"
q() { echo "--- $1"; az monitor log-analytics query -w "$LAW_ID" --analytics-query "$2" -o table 2>&1 | grep -v '^WARNING'; }

q "HTTP /crawl by status (wire truth)" "ContainerAppHTTPLogs | $W | where ContainerAppName == '$APP' and Path == '/crawl'
| summarize n=count(), p50_s=round(percentile(toreal(RequestDuration),50)/1000.0,2), p90_s=round(percentile(toreal(RequestDuration),90)/1000.0,2), p99_s=round(percentile(toreal(RequestDuration),99)/1000.0,2), max_s=round(max(toreal(RequestDuration))/1000.0,2) by StatusCode, ResponseFlags"

q "HTTP /crawl overall latency" "ContainerAppHTTPLogs | $W | where ContainerAppName == '$APP' and Path == '/crawl'
| summarize n=count(), p50_s=round(percentile(toreal(RequestDuration),50)/1000.0,2), p90_s=round(percentile(toreal(RequestDuration),90)/1000.0,2), p99_s=round(percentile(toreal(RequestDuration),99)/1000.0,2), maxMB=round(max(toreal(BytesSent))/1e6,1)"

q "Console signals" "ContainerAppConsoleLogs_CL | $W | where ContainerAppName_s == '$APP'
| extend sig = case(
    indexof(Log_s, 'RenderGate REJECT') >= 0, 'GATE-429',
    indexof(Log_s, 'Memory pressure:') >= 0, 'MEM-REFUSE',
    indexof(Log_s, 'Browser cap reached') >= 0, 'CAP-REFUSE',
    indexof(Log_s, 'FORCE-CLOSING stuck browser') >= 0, 'STUCK-SLOT',
    indexof(Log_s, 'WALL-CLOCK FENCE 504') >= 0, 'FENCE-504',
    indexof(Log_s, 'RENDER DEFECT') >= 0, 'RENDER-DEFECT',
    indexof(Log_s, 'COLLAPSE RECOVERED') >= 0, 'COLLAPSE-RECOVERED',
    indexof(Log_s, 'RESULT FAILURE') >= 0, 'RESULT-FAIL',
    indexof(Log_s, 'ORIGIN FAILURE') >= 0, 'ORIGIN-FAIL',
    indexof(Log_s, 'TERMINAL FAILURE') >= 0, 'TERMINAL-FAIL',
    indexof(Log_s, 'RenderGate ADMIT') >= 0, 'ADMIT',
    indexof(Log_s, 'Anti-bot retry') >= 0, 'ANTIBOT-RETRY',
    indexof(Log_s, 'result(s) blocked, retrying') >= 0, 'PATCHRIGHT-TRY',
    indexof(Log_s, 'UNBLOCKED on retry') >= 0, 'PATCHRIGHT-RESCUE',
    indexof(Log_s, 'STILL blocked') >= 0, 'PATCHRIGHT-STILL-BLOCKED',
    indexof(Log_s, 'Creating new browser') >= 0, 'BROWSER-LAUNCH',
    indexof(Log_s, 'CONSENT DECLINED') >= 0, 'CONSENT-DECLINED',
    indexof(Log_s, 'Traceback') >= 0, 'TRACEBACK',
    indexof(Log_s, 'supervisord started with pid') >= 0, 'CONTAINER-START',
    'OTHER')
| where sig != 'OTHER' | summarize n=count() by sig | order by sig asc"

q "Failures by class (RESULT/ORIGIN/TERMINAL lines; add RENDER-DEFECT above)" "ContainerAppConsoleLogs_CL | $W | where ContainerAppName_s == '$APP'
| where indexof(Log_s, 'RESULT FAILURE') >= 0 or indexof(Log_s, 'ORIGIN FAILURE') >= 0 or indexof(Log_s, 'TERMINAL FAILURE') >= 0
| extend failure_class = extract(@'failure_class=(\\w+)', 1, Log_s), host = extract(@'url=https?://([^/ ]+)', 1, Log_s)
| summarize n=count(), hosts=dcount(host) by failure_class"

q "Pool memory (anon MB) per replica" "ContainerAppConsoleLogs_CL | $W | where ContainerAppName_s == '$APP'
| where indexof(Log_s, 'Pool:') >= 0 and indexof(Log_s, 'mem=') >= 0
| extend anon_mb = toreal(extract(@'anon=([\\d.]+)MB', 1, Log_s)), mem_pct = toreal(extract(@'mem=([\\d.]+)%', 1, Log_s))
| summarize n=count(), anon_p50=percentile(anon_mb,50), anon_max=max(anon_mb), mem_max=max(mem_pct) by ContainerGroupName_s"

q "Platform events" "ContainerAppSystemLogs_CL | $W | where ContainerAppName_s == '$APP'
| where Reason_s in ('SuccessfulRescale','AssigningReplica','ContainerStarted','OOMKilled','ContainerTerminated','ProbeFailed','BackOff')
| summarize n=count(), t0=min(TimeGenerated), t1=max(TimeGenerated) by Reason_s"

q "Failures by class and replica (egress is per replica)" "ContainerAppConsoleLogs_CL | $W | where ContainerAppName_s == '$APP'
| where indexof(Log_s, 'RESULT FAILURE') >= 0 or indexof(Log_s, 'ORIGIN FAILURE') >= 0 or indexof(Log_s, 'TERMINAL FAILURE') >= 0 or indexof(Log_s, 'RENDER DEFECT') >= 0
| extend failure_class = iff(indexof(Log_s,'RENDER DEFECT')>=0, 'render_defect(line)', extract(@'failure_class=(\\w+)', 1, Log_s))
| summarize n=count() by failure_class, ContainerGroupName_s | order by failure_class asc"

q "Requests per replica (admits)" "ContainerAppConsoleLogs_CL | $W | where ContainerAppName_s == '$APP' | where indexof(Log_s, 'RenderGate ADMIT') >= 0
| summarize admits=count(), waited_max=max(toreal(extract(@'waited=([\\d.]+)s',1,Log_s))) by ContainerGroupName_s"

q "Every failure line (for the per-URL join)" "ContainerAppConsoleLogs_CL | $W | where ContainerAppName_s == '$APP'
| where indexof(Log_s, 'RESULT FAILURE') >= 0 or indexof(Log_s, 'ORIGIN FAILURE') >= 0 or indexof(Log_s, 'TERMINAL FAILURE') >= 0 or indexof(Log_s, 'RENDER DEFECT') >= 0 or indexof(Log_s, '[patchright]') >= 0
| project TimeGenerated, ContainerGroupName_s, line=substring(Log_s, 0, 260) | order by TimeGenerated asc"
