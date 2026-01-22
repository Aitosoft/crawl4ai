# Crawl4AI Production Deployment

**Last Updated**: 2026-01-20
**Location**: West Europe (co-located with MAS)
**Status**: ✅ Running with authentication enabled

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

**Docker Image**: `aitosoftacr.azurecr.io/crawl4ai-service:0.8.0-secure`

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

### Update to New Version
```bash
# Rebuild image
az acr build --registry aitosoftacr --image crawl4ai-service:0.8.1 .

# Update container app
az containerapp update \
  --name crawl4ai-service \
  --resource-group aitosoft-prod \
  --image aitosoftacr.azurecr.io/crawl4ai-service:0.8.1
```

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
# Increase replicas
az containerapp update \
  --name crawl4ai-service \
  --resource-group aitosoft-prod \
  --min-replicas 2 \
  --max-replicas 5

# Increase CPU/Memory
az containerapp update \
  --name crawl4ai-service \
  --resource-group aitosoft-prod \
  --cpu 2.0 \
  --memory 4.0Gi
```

---

## Cost Optimization

Current configuration:
- **Replicas**: 1-3 (scales automatically)
- **CPU**: 1.0 core per replica
- **Memory**: 2.0 GiB per replica
- **Estimated cost**: ~€30-50/month (depends on usage)

To reduce costs:
- Set `--min-replicas 0` (scales to zero when idle)
- Reduce CPU/memory if performance allows
- Monitor usage via Azure Portal > Cost Management

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
