#!/usr/bin/env bash
# Aitosoft: post-deploy smoke and SSRF negatives (TESTING.md §Quality gates) against
# $CRAWL4AI_API_URL with $CRAWL4AI_API_TOKEN (both from .env). No third party is contacted: raw://,
# a made-up domain, and two addresses that must be refused.
# Trap (AZURE_OPERATIONS.md §2.4): `revision list` can show the new revision at 100 % before routing
# has switched; a request sent then can hang on the old revision. Wait for the system log's
# "Setting traffic weight of '100%' for revision '<new>'" before running this.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
set -a; . ./.env; set +a
U="$CRAWL4AI_API_URL"; A="Authorization: Bearer $CRAWL4AI_API_TOKEN"; J='Content-Type: application/json'
APP="${APP:-crawl4ai-service-se}"
echo "== target $U"
echo "== revisions (new one must hold 100 % before crawling)"
az containerapp revision list -n $APP -g aitosoft-prod --query "[?properties.active].{name:name, traffic:properties.trafficWeight, replicas:properties.replicas, health:properties.healthState, image:properties.template.containers[0].image}" -o table
echo "== /health"
curl -s -m 200 -w '  http=%{http_code} t=%{time_total}s\n' "$U/health"
echo "== unauthenticated /crawl (expect 401)"
curl -s -m 60 -o /dev/null -w '  http=%{http_code}\n' -X POST "$U/crawl" -H "$J" -d '{"urls":["raw://<p>x</p>"]}'
post() { curl -s -m 200 -w '\n%{http_code}' -X POST "$U/crawl" -H "$A" -H "$J" -d "$1"; }
show() { python3 -c '
import json,sys
raw=sys.stdin.read(); body,code=raw.rsplit("\n",1)
try:
    d=json.loads(body)
except Exception:
    print("  http="+code, body[:200]); sys.exit()
if "results" in d:
    r=d["results"][0]; md=(r.get("markdown") or {}).get("raw_markdown","") if isinstance(r.get("markdown"),dict) else ""
    print("  http="+code, "success=",r.get("success"), "class=",r.get("failure_class"), "status=",r.get("status_code"), "md=",len(md), "links=",list((r.get("links") or {}).keys()), "media=",list((r.get("media") or {}).keys()), "err=",(r.get("error_message") or "")[:90])
else:
    print("  http="+code, json.dumps(d)[:220])
'; }
echo "== raw:// crawl (expect 200, none)"
post '{"urls":["raw://<html><body><h1>Smoke</h1><p>Contact: smoke@example.com</p></body></html>"]}' | show
echo "== made-up domain (expect 200, success false, origin_unreachable, DNS)"
post '{"urls":["https://crawl4ai-smoke-'$(date +%s)'-nonexistent.fi/"]}' | show
echo "== SSRF negatives (expect 400 URL blocked)"
post '{"urls":["http://169.254.169.254/latest/meta-data/"]}' | show
post '{"urls":["http://127.0.0.1:8080/"]}' | show
echo "== failed result shape: keyed links/media (merge §3.3), shown on the made-up-domain line above"
