# Crawl4AI Production Deployment

**Last Updated**: 2026-04-04
**Location**: West Europe (co-located with MAS)
**Status**: ✅ Running v0.8.6 (rescaled 2026-04-04)

---

## Endpoint & Credentials

**API Endpoint**:
```
https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io
```

**API Token**:
```
See .env file (CRAWL4AI_API_TOKEN)
NEVER commit tokens to git - always use .env files
```

**⚠️ IMPORTANT**: Add these to your MAS repo `.env` or configuration:
```bash
CRAWL4AI_API_URL=https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io
CRAWL4AI_API_TOKEN=<get-from-crawl4ai-repo-.env-file>
```

---

## Azure Resources

All resources are in the `aitosoft-prod` resource group (West Europe):

| Resource | Type | Purpose |
|----------|------|---------|
| `aitosoftacr` | Container Registry | Hosts crawl4ai Docker image |
| `aitosoft-aca` | Container Apps Environment | Runtime environment |
| `crawl4ai-service` | Container App | The crawl4ai service |
| `workspace-aitosoftprodnCsc` | Log Analytics | Monitoring & logs |

**Docker Image**: `aitosoftacr.azurecr.io/crawl4ai-service:0.8.6-maxpages-fix`

---

## Usage Examples

### Python

```python
import requests
import os

# Load from environment variables (see .env file)
CRAWL4AI_URL = os.getenv("CRAWL4AI_API_URL")
CRAWL4AI_TOKEN = os.getenv("CRAWL4AI_API_TOKEN")

# Basic crawl
response = requests.post(
    f"{CRAWL4AI_URL}/crawl",
    headers={"Authorization": f"Bearer {CRAWL4AI_TOKEN}"},
    json={"urls": ["https://example.com"]}
)

result = response.json()
if result["success"]:
    markdown = result["results"][0]["markdown"]["raw_markdown"]
    print(markdown)
```

### cURL

```bash
# Health check (no auth)
curl https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io/health

# Crawl with auth (load token from .env file)
source .env  # Or use: export CRAWL4AI_API_TOKEN=$(grep CRAWL4AI_API_TOKEN .env | cut -d= -f2)
curl -X POST https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io/crawl \
  -H "Authorization: Bearer $CRAWL4AI_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"]}'
```

---

## Management

### View Logs
```bash
az containerapp logs show \
  --name crawl4ai-service \
  --resource-group aitosoft-prod \
  --follow
```

### Update to New Version (Image Only — Keeps Existing Token)
```bash
# Step 1: Build image in Azure (no local Docker needed)
az acr build --registry aitosoftacr --image crawl4ai-service:0.8.6 .

# Step 2: Update container app image ONLY (preserves env vars including API token)
az containerapp update \
  --name crawl4ai-service \
  --resource-group aitosoft-prod \
  --image aitosoftacr.azurecr.io/crawl4ai-service:0.8.6

# Step 3: Verify
curl https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io/health
```

**⚠️ WARNING**: Do NOT use `deploy-aitosoft-prod.sh --update-only` for routine updates —
it regenerates the API token which breaks the MAS connection. Use the commands above instead.

### Rotate API Token
```bash
# Generate new token
NEW_TOKEN="crawl4ai-$(openssl rand -hex 24)"

# Update Azure
az containerapp update \
  --name crawl4ai-service \
  --resource-group aitosoft-prod \
  --set-env-vars CRAWL4AI_API_TOKEN="$NEW_TOKEN"

# Update MAS repo config with new token
```

### Scale Resources
```bash
# Current (2026-04-04): 2 CPU, 4 GiB, 0-20 replicas
# Adjust if needed:
az containerapp update \
  --name crawl4ai-service \
  --resource-group aitosoft-prod \
  --min-replicas 0 \
  --max-replicas 20 \
  --cpu 2.0 \
  --memory 4.0Gi
```

### Batch Runbook — WAA Warm-Up / Cool-Down (2026-04-14)

KEDA's http-scaler can scale 2→1 replicas mid-batch if traffic looks light to
its polling (seen in the 2026-04-14 outage at 12:51 UTC — replica SIGTERM'd
during an active crawl). Before any WAA batch larger than a handful of
companies, hold `min-replicas` up so you always have warm capacity and
failover.

```bash
# BEFORE starting a WAA batch run:
./azure-deployment/batch-scale.sh up        # 1 warm replica (sequential)
./azure-deployment/batch-scale.sh up 3      # 3 warm replicas (3-6 parallel agents)
./azure-deployment/batch-scale.sh up 5      # 5 warm (10+ parallel agents)

# AFTER batch completes:
./azure-deployment/batch-scale.sh down      # Back to scale-to-zero

# Check current state:
./azure-deployment/batch-scale.sh status
```

Cost impact of `up 1` for an 8-hour batch: ~€0.80 extra (1 replica × €0.10/h).
Worth it for reliability.

---

## Cost Optimization

Current configuration (updated 2026-04-04):
- **Replicas**: 0-20 (scales to zero when idle, scales out under load)
- **CPU**: 2.0 cores per replica
- **Memory**: 4.0 GiB per replica
- **max_pages**: 5 per replica (horizontal scaling strategy)
- **memory_threshold**: 85% (conservative for cloud)
- **Estimated cost**: Scales to zero when idle. Under load: ~€0.10/replica-hour

### Scaling Strategy (2026-04-04)
Investigation of 500s+ latency incidents revealed the original 1 CPU / 2 GiB config caused
severe resource starvation — Chromium pages competed for a single CPU core, leading to
8+ minute queuing delays on requests that actually crawled in <10s.

Fix: fewer pages per replica (5), more replicas (up to 20). Each replica gets its own
Chromium process with dedicated CPU. Azure scales replicas based on HTTP traffic.

To monitor costs:
- Azure Portal > Cost Management
- Most time will be at 0 replicas (zero cost)

---

## Legacy North Europe Deployment

There's an old deployment in `crawl4ai-v2-rg` (North Europe) that can be deleted:

```bash
# Delete old resource group (saves ~€60-80/month)
az group delete --name crawl4ai-v2-rg --yes --no-wait
```

**⚠️ WARNING**: Only delete after confirming the West Europe deployment works for your MAS!

---

## Troubleshooting

**401 Unauthorized**:
- Verify token matches exactly
- Check `Authorization: Bearer <token>` header format
- Verify token is set in Azure: `az containerapp show --name crawl4ai-service --resource-group aitosoft-prod --query "properties.template.containers[0].env"`

**500 Internal Server Error**:
- Check logs: `az containerapp logs show --name crawl4ai-service --resource-group aitosoft-prod --tail 100`
- Verify app is running: `az containerapp show --name crawl4ai-service --resource-group aitosoft-prod --query "properties.runningStatus"`

**Slow response**:
- App may be cold starting (first request after idle takes ~30s)
- Increase `--min-replicas 1` to keep always warm

---

## Support

- **Logs**: Azure Portal > Container Apps > crawl4ai-service > Logs
- **Monitoring**: Azure Portal > Container Apps > crawl4ai-service > Metrics
- **Documentation**: See `azure-deployment/SIMPLE_AUTH_DEPLOY.md`
