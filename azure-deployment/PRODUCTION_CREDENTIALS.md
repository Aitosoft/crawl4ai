# 🔐 Production Credentials - Crawl4AI v2 Deployment

**⚠️ KEEP THIS FILE SECURE - Contains production credentials**

## Deployment Information
- **Deployment Date**: 2025-07-10
- **Resource Group**: crawl4ai-v2-rg
- **Container App**: crawl4ai-v2-app
- **Environment**: crawl4ai-v2-env
- **Location**: North Europe
- **Subscription**: Aitosoft - Microsoft Partner Network NEW

## Production URLs
- **Main App**: https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io
- **Health Check**: https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/health
- **Interactive Playground**: https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/playground

## Authentication Credentials
- **API Token**: `crawl4ai-6f742ac78f67c5402b3041738b7d95a6`
- **JWT Secret**: `jwt-secret-1021fbb10da3e04446f83296f394f50117885a72edff437b8fe73af573257d2a`

## Usage Instructions

### 1. Get a JWT Token
```bash
curl -X POST https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/token \
  -H "Content-Type: application/json" \
  -d '{"email":"test@gmail.com"}'
```

### 2. Use the Token for Crawling
```bash
# Replace JWT_TOKEN with the token from step 1
curl -X POST https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/crawl \
  -H "Authorization: Bearer JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com"],
    "browser_config": {"headless": true},
    "crawler_config": {
      "markdown_generator": {
        "type": "DefaultMarkdownGenerator",
        "params": {
          "content_filter": {
            "type": "PruningContentFilter",
            "params": {
              "threshold": 0.6,
              "threshold_type": "fixed",
              "min_word_threshold": 0
            }
          },
          "options": {"ignore_links": false}
        }
      }
    }
  }'
```

### 3. Finnish Company Crawling Example
```bash
curl -X POST https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/crawl \
  -H "Authorization: Bearer JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://finnish-company.fi"],
    "crawler_config": {
      "markdown_generator": {
        "type": "DefaultMarkdownGenerator",
        "params": {
          "content_filter": {
            "type": "PruningContentFilter",
            "params": {"threshold": 0.6}
          },
          "options": {"ignore_links": false}
        }
      },
      "wait_for": "networkidle",
      "delay_before_return_html": 2.0
    }
  }'
```

## Expected Response Format
Your API calls will return:
```json
{
  "success": true,
  "results": [{
    "url": "https://website.com",
    "markdown": {
      "raw_markdown": "Full markdown content...",
      "fit_markdown": "Cleaned markdown content..."
    },
    "links": {
      "external": [{"href": "...", "text": "...", "base_domain": "..."}],
      "internal": [...]
    },
    "metadata": {"title": "...", "description": "..."}
  }]
}
```

## Management Commands

### Update to New Version
```bash
# Edit deploy.sh to change image version, then:
./azure-deployment/deploy.sh --update-only
```

### View Logs
```bash
az containerapp logs show \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --follow
```

### Check Status
```bash
az containerapp show \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --query properties.runningStatus
```

## Security Notes
- JWT tokens expire after 60 minutes
- Use real email domains for token requests (gmail.com, outlook.com, etc.)
- All requests must use HTTPS
- This deployment is optimized for internal company use

---
*Keep this file secure and do not commit to public repositories*