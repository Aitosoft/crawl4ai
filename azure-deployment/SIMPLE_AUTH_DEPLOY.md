# Simple Token Auth Deployment Guide

## What We Added

**Simple static token authentication** - only 39 lines of code added to upstream crawl4ai.

### Why?
- Upstream JWT lets **anyone** get a token with just an email - no security
- Our simple auth requires **one secret token** - real security
- Prevents random people from using your scraper and running up Azure bills

## How It Works

```
Request → Check Authorization: Bearer <token> → Match CRAWL4AI_API_TOKEN → Allow/Deny
```

- ✅ Health check `/health` - no auth required (for Azure monitoring)
- ✅ Docs `/docs`, `/redoc` - no auth required
- 🔒 Everything else `/crawl`, `/md`, etc. - requires token

## Deploy to Azure

### Step 1: Build Your Docker Image

```bash
# Login to Azure Container Registry (create one first if needed)
az acr login --name aitosoftacr

# Build and push
docker build -t aitosoftacr.azurecr.io/crawl4ai-service:0.8.0 .
docker push aitosoftacr.azurecr.io/crawl4ai-service:0.8.0
```

### Step 2: Generate a Secure Token

```bash
# Generate a random token
TOKEN="crawl4ai-$(openssl rand -hex 24)"
echo "Your token: $TOKEN"
```

### Step 3: Deploy to Azure

```bash
# Update the container app with your image and token
az containerapp update \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --image aitosoftacr.azurecr.io/crawl4ai-service:0.8.0 \
  --set-env-vars \
    CRAWL4AI_API_TOKEN="$TOKEN" \
    ENVIRONMENT=production
```

### Step 4: Test It

```bash
# Get endpoint
ENDPOINT=$(az containerapp show \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --query "properties.configuration.ingress.fqdn" -o tsv)

# Health check (no auth)
curl https://$ENDPOINT/health

# Crawl without token (should fail)
curl -X POST https://$ENDPOINT/crawl \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"]}'
# Expected: 401 Unauthorized

# Crawl with token (should work)
curl -X POST https://$ENDPOINT/crawl \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"]}'
# Expected: Success with markdown
```

### Step 5: Update Your MAS Repo

Save the token in your multi-agent system repo:

```bash
# .env or wherever you store config
CRAWL4AI_API_URL=https://$ENDPOINT
CRAWL4AI_API_TOKEN=$TOKEN
```

## Using from Python

```python
import requests

CRAWL4AI_URL = "https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io"
CRAWL4AI_TOKEN = "crawl4ai-abc123..."  # Your secret token

response = requests.post(
    f"{CRAWL4AI_URL}/crawl",
    headers={"Authorization": f"Bearer {CRAWL4AI_TOKEN}"},
    json={"urls": ["https://example.com"]}
)

result = response.json()
markdown = result["results"][0]["markdown"]["raw_markdown"]
```

## Updating to New Upstream Versions

When crawl4ai releases a new version:

```bash
# Pull latest upstream
git fetch upstream
git merge upstream/main

# Rebuild and deploy
docker build -t aitosoftacr.azurecr.io/crawl4ai-service:0.8.1 .
docker push aitosoftacr.azurecr.io/crawl4ai-service:0.8.1

# Update Azure (token stays the same)
az containerapp update \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --image aitosoftacr.azurecr.io/crawl4ai-service:0.8.1
```

Your token stays the same - no need to update MAS repo!

## Rotating Tokens

To change the token:

```bash
# Generate new token
NEW_TOKEN="crawl4ai-$(openssl rand -hex 24)"

# Update Azure
az containerapp update \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --set-env-vars CRAWL4AI_API_TOKEN="$NEW_TOKEN"

# Update MAS repo config
# Then restart your services to pick up new token
```

## Troubleshooting

**401 Unauthorized even with correct token?**
- Check token matches exactly (no extra spaces)
- Verify `CRAWL4AI_API_TOKEN` env var is set in Azure
- Check security is enabled in config

**Want to disable auth for testing?**
```bash
# Remove the token env var
az containerapp update \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --remove-env-vars CRAWL4AI_API_TOKEN
```

**Check what token is configured:**
```bash
# Won't show the actual value (it's a secret)
az containerapp show \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --query "properties.template.containers[0].env[?name=='CRAWL4AI_API_TOKEN']"
```
