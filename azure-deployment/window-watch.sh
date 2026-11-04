#!/usr/bin/env bash
# Aitosoft: one compact line every 5 min for a run in progress (wire statuses, failure classes,
# gate/memory 429s, Patchright, restarts, replicas). Log Analytics and the management API only;
# never calls the app. Meant for Claude Code's Monitor tool: each stdout line is an event.
# Usage: LAW_ID=<PRIVATE.md> ./azure-deployment/window-watch.sh <t0 ISO UTC> [app]
T0="${1:?t0}"; APP="${2:-crawl4ai-service-se}"; LAW="${LAW_ID:?set LAW_ID (PRIVATE.md)}"
while true; do
  h=$(az monitor log-analytics query -w $LAW --analytics-query "ContainerAppHTTPLogs | where TimeGenerated > datetime($T0) | where ContainerAppName == '$APP' and Path == '/crawl' | summarize n=count() by StatusCode | order by StatusCode asc" -o json 2>/dev/null | python3 -c "import json,sys; print(' '.join(f\"{r['StatusCode']}:{r['n']}\" for r in json.load(sys.stdin)))" 2>/dev/null)
  c=$(az monitor log-analytics query -w $LAW --analytics-query "ContainerAppConsoleLogs_CL | where TimeGenerated > datetime($T0) | where ContainerAppName_s == '$APP' | extend sig=case(indexof(Log_s,'RESULT FAILURE')>=0 or indexof(Log_s,'ORIGIN FAILURE')>=0 or indexof(Log_s,'TERMINAL FAILURE')>=0, strcat('F:',extract(@'failure_class=(\\w+)',1,Log_s)), indexof(Log_s,'RENDER DEFECT')>=0,'RENDER_DEFECT', indexof(Log_s,'UNBLOCKED on retry')>=0,'PR_RESCUE', indexof(Log_s,'STILL blocked')>=0,'PR_STILL', indexof(Log_s,'RenderGate REJECT')>=0,'GATE429', indexof(Log_s,'WALL-CLOCK FENCE 504')>=0,'FENCE504', indexof(Log_s,'supervisord started with pid')>=0,'CSTART', indexof(Log_s,'OOMKilled')>=0,'OOM', indexof(Log_s,'Traceback')>=0,'TRACEBACK','') | where sig != '' | summarize n=count() by sig" -o json 2>/dev/null | python3 -c "import json,sys; print(' '.join(f\"{r['sig']}:{r['n']}\" for r in json.load(sys.stdin)))" 2>/dev/null)
  r=$(az containerapp replica list -n $APP -g aitosoft-prod --query 'length(@)' -o tsv 2>/dev/null)
  echo "$(date -u +%H:%M)Z http[$h] logs[$c] replicas=$r"
  sleep 300
done
