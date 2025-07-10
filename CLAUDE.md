# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is Aitosoft's internal Crawl4AI deployment project. It provides a web scraping API service optimized for crawling Finnish company websites to extract business information, contact details, and company descriptions. The service returns both raw markdown and cleaned "fit_markdown" content suitable for AI processing.

## Current Production Deployment

### Azure Container Apps Setup
- **Resource Group**: `crawl4ai-v2-rg`
- **Container App**: `crawl4ai-v2-app`
- **Environment**: `crawl4ai-v2-env`
- **Key Vault**: `crawl4ai-v2-keyvault`
- **Location**: North Europe
- **Production URL**: https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io

### Authentication
- **Type**: Simple Bearer Token (internal use)
- **Token**: `as070511sip772patat` (stored in Azure Key Vault)
- **Usage**: `Authorization: Bearer as070511sip772patat`
- **Security**: Token stored in Key Vault, accessed via managed identity

## Development Environment

### Dev Container Configuration
- **Base Image**: `mcr.microsoft.com/devcontainers/python:3.11-bookworm`
- **Platform**: Windows 11 ARM + WSL2 + Dev Container
- **Project Location**: `~/code/crawl4ai` (Linux-native path)
- **Working Directory**: `/workspaces/crawl4ai` (inside container)
- **Port**: 11235 (forwarded for local testing)

### Pre-installed Tools
- **Python Tools**: ruff, black, mypy, pytest, pre-commit
- **Azure CLI**: For deployment and management
- **Crawl4AI**: Latest version with all dependencies
- **Claude Code CLI**: For AI-assisted development

### Development Workflow
1. Open in WSL: `cd ~/code/crawl4ai && code .`
2. Choose "Reopen in Container" when prompted
3. All tools immediately available in container
4. Test locally: `uvicorn deploy.docker.server:app --host 0.0.0.0 --port 11235`

## Key Deployment Files

### Azure Deployment Configuration
- **`azure-deployment/keyvault-deploy.sh`**: Complete deployment script with Key Vault
- **`azure-deployment/PRODUCTION_CREDENTIALS_V2.md`**: Production access credentials
- **`azure-deployment/deploy.sh`**: Original deployment script
- **`azure-deployment/DEPLOYMENT_GUIDE.md`**: Step-by-step deployment instructions

### Configuration Files
- **`deploy/docker/config.yml`**: Base server configuration
- **`azure-deployment/production-config.yml`**: Production-optimized settings
- **`.devcontainer/devcontainer.json`**: Dev container configuration

### Testing Scripts
- **`test_fit_markdown.py`**: Test fit_markdown functionality locally
- **`test_server_api.py`**: Test local server API
- **`test_production_auth.py`**: Test production authentication
- **`azure-deployment/test_auth.py`**: General authentication testing

## Core API Configuration for Finnish Companies

### Optimal Crawling Configuration
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

### Expected Response Format
- **`markdown.raw_markdown`**: Full content
- **`markdown.fit_markdown`**: Cleaned content (primary use)
- **`links.external`**: Contact details and external references
- **`metadata`**: Title, description, etc.

## Common Development Tasks

### Local Testing
```bash
# Start local server
uvicorn deploy.docker.server:app --host 0.0.0.0 --port 11235

# Test fit_markdown locally
python test_fit_markdown.py

# Test server API
python test_server_api.py
```

### Azure Deployment
```bash
# Login to Azure (Aitosoft subscription)
az login

# Deploy new version
./azure-deployment/keyvault-deploy.sh --update-only

# Test production deployment
python azure-deployment/test_auth.py --url https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io
```

### Azure Management Commands
```bash
# View container logs
az containerapp logs show \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --follow

# Check container status
az containerapp show \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --query properties.runningStatus

# Update Key Vault secret
az keyvault secret set \
  --vault-name crawl4ai-v2-keyvault \
  --name C4AI-TOKEN \
  --value new-token-value

# Update container image
az containerapp update \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --image unclecode/crawl4ai:NEW_VERSION
```

### Code Quality
```bash
# Format code
black crawl4ai/ tests/ azure-deployment/

# Type checking
mypy crawl4ai/

# Linting
ruff check crawl4ai/ tests/ azure-deployment/

# Run pre-commit hooks
pre-commit run --all-files
```

## Key Architecture Components

### Core Classes (for understanding, not modification)
- **AsyncWebCrawler**: Main crawler class
- **BrowserConfig**: Browser settings configuration
- **CrawlerRunConfig**: Individual crawl configurations
- **CrawlResult**: Results container with markdown and metadata

### Important Directories
- **`crawl4ai/`**: Main package source code (generally don't modify)
- **`deploy/docker/`**: Server configuration and API endpoints
- **`azure-deployment/`**: Our custom deployment scripts and configs
- **`tests/`**: Test suites for validation

## Authentication System

### Current Setup (Simplified for Internal Use)
- **Method**: Bearer token in Azure Key Vault
- **Enforcement**: Not strictly enforced (internal network security)
- **Token Storage**: Azure Key Vault with managed identity access
- **Application Usage**: Include `Authorization: Bearer as070511sip772patat` header

### Key Vault Integration
- **Vault**: `crawl4ai-v2-keyvault`
- **Secret**: `C4AI-TOKEN`
- **Access**: Container app uses system-assigned managed identity
- **Security**: No credentials in code or environment variables

## Production Monitoring

### Health Checks
- **Endpoint**: `/health` (no authentication required)
- **Expected Response**: `{"status":"ok","timestamp":...,"version":"..."}`
- **Use for**: Automated monitoring and status checks

### Performance Metrics
- **Processing Time**: Typically 1-2 seconds for standard pages
- **Memory Usage**: Monitored and reported in API responses
- **Scaling**: 1-3 replicas based on demand

## Update Procedures

### For New Crawl4AI Versions
1. Update image tag in `azure-deployment/keyvault-deploy.sh`
2. Run: `./azure-deployment/keyvault-deploy.sh --update-only`
3. Test with: `python azure-deployment/test_auth.py --url PRODUCTION_URL`
4. Commit changes and push to GitHub

### For Configuration Changes
1. Modify relevant config files in `azure-deployment/`
2. Re-run deployment script
3. Test functionality with production URL
4. Update documentation if needed

### For Authentication Changes
1. Update token in Key Vault: `az keyvault secret set --vault-name crawl4ai-v2-keyvault --name C4AI-TOKEN --value NEW_TOKEN`
2. No container restart needed (uses Key Vault reference)
3. Update documentation with new token

## Important Notes

- **Internal Use Only**: This deployment is optimized for Aitosoft's internal applications
- **Finnish Company Focus**: Configuration optimized for Finnish business websites
- **fit_markdown Priority**: Primary output format for AI processing
- **Azure Integration**: Full Azure ecosystem with Key Vault, Container Apps, and managed identities
- **No Public Access**: Secured for internal company use only

## Troubleshooting

### Common Issues
- **503 Errors**: Container starting up (wait 30-60 seconds)
- **Slow Response**: Large pages or complex JS (expected behavior)
- **Empty fit_markdown**: Adjust PruningContentFilter threshold
- **Missing Links**: Ensure `ignore_links: false` in configuration

### Debug Commands
```bash
# Check container logs
az containerapp logs show --name crawl4ai-v2-app --resource-group crawl4ai-v2-rg --tail 50

# Test health endpoint
curl https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/health

# Test with minimal payload
curl -X POST PRODUCTION_URL/crawl -H "Authorization: Bearer as070511sip772patat" -H "Content-Type: application/json" -d '{"urls":["https://example.com"]}'
```

This deployment provides a robust, scalable web scraping service optimized for Aitosoft's business intelligence needs with Finnish company websites.