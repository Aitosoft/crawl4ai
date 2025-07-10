# Crawl4AI Azure Container Apps Deployment Guide

This guide provides step-by-step instructions for deploying Crawl4AI to Azure Container Apps with proper authentication and fit_markdown support.

## Overview

This deployment provides:
- ✅ **Clean Azure Container Apps deployment**
- ✅ **JWT authentication for security**
- ✅ **fit_markdown output support**
- ✅ **Health monitoring and logging**
- ✅ **Easy updates for new Crawl4AI versions**
- ✅ **Internal company use optimized**

## Prerequisites

1. **Azure CLI installed and logged in**
   ```bash
   az login
   az account show  # Verify you're logged in to the correct subscription
   ```

2. **Docker CLI (if you want to test locally)**
   ```bash
   docker --version
   ```

3. **Required permissions in Azure**
   - Contributor access to your Azure subscription
   - Ability to create resource groups and container apps

## Step 1: Prepare for Deployment

1. **Clone/navigate to the project directory**
   ```bash
   cd /workspaces/crawl4ai
   ```

2. **Review deployment configuration**
   ```bash
   # Check the deployment script
   cat azure-deployment/deploy.sh
   
   # Review the configuration
   cat azure-deployment/production-config.yml
   ```

3. **Customize deployment settings (optional)**
   
   Edit `azure-deployment/deploy.sh` to change:
   - `RESOURCE_GROUP`: Change from "crawl4ai-v2-rg" if desired
   - `CONTAINER_APP`: Change from "crawl4ai-v2-app" if desired
   - `LOCATION`: Change from "northeurope" to your preferred region
   - `IMAGE`: Update to newer version when available

## Step 2: Deploy to Azure

1. **Run deployment script**
   ```bash
   chmod +x azure-deployment/deploy.sh
   ./azure-deployment/deploy.sh
   ```

2. **For dry-run first (recommended)**
   ```bash
   ./azure-deployment/deploy.sh --dry-run
   ```

3. **Monitor deployment progress**
   The script will:
   - Create resource group
   - Create Log Analytics workspace
   - Create Container Apps environment
   - Deploy the container app
   - Configure authentication
   - Show deployment summary

## Step 3: Test Your Deployment

After deployment completes, you'll see output like:
```
📋 Deployment Summary:
   App URL: https://crawl4ai-v2-app.kindocean-12345.northeurope.azurecontainerapps.io
   Health Check: https://crawl4ai-v2-app.kindocean-12345.northeurope.azurecontainerapps.io/health
   Playground: https://crawl4ai-v2-app.kindocean-12345.northeurope.azurecontainerapps.io/playground
   API Token: crawl4ai-abc123...
   JWT Secret: jwt-secret-def456...
```

1. **Test health check (no auth required)**
   ```bash
   curl https://YOUR_APP_URL/health
   ```

2. **Get a JWT token**
   ```bash
   curl -X POST https://YOUR_APP_URL/token \
     -H "Content-Type: application/json" \
     -d '{"email":"test@gmail.com"}'
   ```
   
   This returns:
   ```json
   {
     "email": "test@gmail.com",
     "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
     "token_type": "bearer"
   }
   ```

3. **Test authenticated crawl with fit_markdown**
   ```bash
   curl -X POST https://YOUR_APP_URL/crawl \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
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

4. **Verify fit_markdown in response**
   Look for these fields in the response:
   ```json
   {
     "success": true,
     "results": [{
       "markdown": {
         "raw_markdown": "# Example Domain\n...",
         "fit_markdown": "# Example Domain\n..."
       },
       "links": {
         "external": [...],
         "internal": [...]
       }
     }]
   }
   ```

## Step 4: Save Credentials

**IMPORTANT**: Save these credentials securely:

```bash
# From deployment output
API_TOKEN=crawl4ai-abc123...
JWT_SECRET=jwt-secret-def456...
APP_URL=https://crawl4ai-v2-app.kindocean-12345.northeurope.azurecontainerapps.io
```

Store these in your password manager or secure note system.

## Step 5: Use the Playground

Visit the playground to test interactively:
```
https://YOUR_APP_URL/playground
```

The playground provides a web interface to:
- Test different URLs
- Configure crawling options
- See fit_markdown output
- Generate API requests

## Updating to New Versions

When a new version of Crawl4AI is released:

1. **Update the image tag**
   ```bash
   # Edit azure-deployment/deploy.sh
   # Change: IMAGE="unclecode/crawl4ai:0.6.0-r3"
   # To:     IMAGE="unclecode/crawl4ai:NEW_VERSION"
   ```

2. **Deploy update**
   ```bash
   ./azure-deployment/deploy.sh --update-only
   ```

This preserves your configuration and credentials while updating the container.

## Monitoring and Troubleshooting

1. **View logs**
   ```bash
   az containerapp logs show \
     --name crawl4ai-v2-app \
     --resource-group crawl4ai-v2-rg \
     --follow
   ```

2. **Check application status**
   ```bash
   az containerapp show \
     --name crawl4ai-v2-app \
     --resource-group crawl4ai-v2-rg \
     --query properties.runningStatus
   ```

3. **Monitor resource usage**
   ```bash
   az monitor metrics list \
     --resource /subscriptions/YOUR_SUB/resourceGroups/crawl4ai-v2-rg/providers/Microsoft.App/containerApps/crawl4ai-v2-app \
     --metric "RequestsPerSecond"
   ```

4. **Common issues**
   - **503 errors**: Check if container is starting up (takes 30-60 seconds)
   - **401 errors**: Verify JWT token is valid and not expired
   - **500 errors**: Check logs for application errors
   - **Memory issues**: Consider increasing memory limits in deploy.sh

## Security Notes

- **JWT tokens expire after 60 minutes** - get new tokens as needed
- **Email domain validation** - use real domains (gmail.com, outlook.com, etc.)
- **HTTPS only** - all API calls must use HTTPS
- **Internal use** - this setup is optimized for internal company use

## Configuration for Finnish Company Websites

For your specific use case of crawling Finnish company websites:

```json
{
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
    },
    "wait_for": "networkidle",
    "delay_before_return_html": 2.0
  }
}
```

This configuration:
- Uses fit_markdown for cleaner content
- Preserves links for contact details
- Waits for pages to fully load
- Optimized for content extraction

## Support

For issues with this deployment:
1. Check the troubleshooting section above
2. Review Azure Container Apps documentation
3. Check Crawl4AI documentation at https://docs.crawl4ai.com
4. Examine logs for specific error messages

---

*This deployment guide is maintained as part of the Crawl4AI project development notes.*