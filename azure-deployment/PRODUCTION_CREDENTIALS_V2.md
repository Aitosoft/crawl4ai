# 🔐 Production Credentials - Crawl4AI v2 (Simplified Auth)

**⚠️ KEEP THIS FILE SECURE - Contains production credentials**

## Deployment Information
- **Deployment Date**: 2025-07-10
- **Resource Group**: crawl4ai-v2-rg
- **Container App**: crawl4ai-v2-app
- **Environment**: crawl4ai-v2-env
- **Location**: North Europe
- **Authentication**: Simplified Bearer Token (Internal Use)
- **Key Vault**: crawl4ai-v2-keyvault

## Production URLs
- **Main App**: https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io
- **Health Check**: https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/health
- **Interactive Playground**: https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/playground

## Authentication (Simplified for Internal Use)

### Bearer Token
- **Token**: `as070511sip772patat`
- **Storage**: Azure Key Vault secret `C4AI-TOKEN`
- **Usage**: Include in all API requests as `Authorization: Bearer as070511sip772patat`

### Security Model
- **Internal Use Only**: Designed for application-to-application communication
- **No Token Expiration**: Static token, no refresh needed
- **Key Vault Protection**: Token secured in Azure Key Vault
- **Network Security**: Accessible via HTTPS only

## Usage Examples

### 1. Health Check (No Auth Required)
```bash
curl https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/health
```

### 2. Basic Crawl with fit_markdown
```bash
curl -X POST https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/crawl \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer as070511sip772patat" \
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

### 3. Finnish Company Crawling (Your Use Case)
```bash
curl -X POST https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/crawl \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer as070511sip772patat" \
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
  }],
  "server_processing_time_s": 1.76,
  "server_memory_delta_mb": 3.48
}
```

## Application Integration

### Python Example
```python
import requests

def crawl_website(url):
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer as070511sip772patat"
    }
    
    payload = {
        "urls": [url],
        "crawler_config": {
            "markdown_generator": {
                "type": "DefaultMarkdownGenerator",
                "params": {
                    "content_filter": {
                        "type": "PruningContentFilter",
                        "params": {"threshold": 0.6}
                    },
                    "options": {"ignore_links": False}
                }
            }
        }
    }
    
    response = requests.post(
        "https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/crawl",
        json=payload,
        headers=headers
    )
    
    return response.json()

# Usage
result = crawl_website("https://finnish-company.fi")
fit_markdown = result["results"][0]["markdown"]["fit_markdown"]
links = result["results"][0]["links"]["external"]
```

### JavaScript/Node.js Example
```javascript
async function crawlWebsite(url) {
    const response = await fetch(
        'https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/crawl',
        {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer as070511sip772patat'
            },
            body: JSON.stringify({
                urls: [url],
                crawler_config: {
                    markdown_generator: {
                        type: "DefaultMarkdownGenerator",
                        params: {
                            content_filter: {
                                type: "PruningContentFilter",
                                params: { threshold: 0.6 }
                            },
                            options: { ignore_links: false }
                        }
                    }
                }
            })
        }
    );
    
    return await response.json();
}

// Usage
const result = await crawlWebsite('https://finnish-company.fi');
const fitMarkdown = result.results[0].markdown.fit_markdown;
const links = result.results[0].links.external;
```

## Management Commands

### Update Token in Key Vault
```bash
az keyvault secret set \
  --vault-name crawl4ai-v2-keyvault \
  --name C4AI-TOKEN \
  --value new-token-value
```

### Update Container App
```bash
# For new Crawl4AI versions
az containerapp update \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --image unclecode/crawl4ai:NEW_VERSION
```

### View Logs
```bash
az containerapp logs show \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --follow
```

## Key Vault Information
- **Vault Name**: crawl4ai-v2-keyvault
- **Secret Name**: C4AI-TOKEN
- **Secret URI**: https://crawl4ai-v2-keyvault.vault.azure.net/secrets/C4AI-TOKEN/53d91e37b9164821b401e9733780b494
- **Access**: Container app has managed identity with "Key Vault Secrets User" role

## Security Benefits
- ✅ **Token in Key Vault**: Not exposed in environment variables
- ✅ **Managed Identity**: No credentials in code
- ✅ **HTTPS Only**: Encrypted communication
- ✅ **Internal Use**: Simplified for application-to-application communication
- ✅ **No Expiration**: Static token, no refresh complexity

## Advantages Over Previous JWT Setup
1. **Simpler**: No token generation/refresh endpoints
2. **More Secure**: Token stored in Key Vault vs environment variables
3. **Application-Friendly**: Perfect for service-to-service communication
4. **No Downtime**: No token expiration to manage
5. **Azure Best Practice**: Uses managed identity and Key Vault

---
*This deployment is optimized for internal application use with simplified authentication*