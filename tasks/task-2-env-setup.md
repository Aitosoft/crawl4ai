# Task 2: Environment Setup for LLM API Keys

## Overview
LLM extraction requires API keys. These must be configured locally and in Azure, but NEVER committed to git.

## Local Development Setup

1. **Create .env file from template**
   ```bash
   cp .env.example .env
   ```

2. **Add your API key to .env**
   ```bash
   # Edit .env and add your actual key:
   DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   # or
   OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

3. **Verify .env is gitignored**
   ```bash
   git status  # .env should NOT appear
   ```

4. **Test locally**
   ```bash
   # Load env vars
   export $(cat .env | xargs)

   # Start server
   uvicorn deploy.docker.server:app --host 0.0.0.0 --port 11235

   # Test LLM extraction
   curl -X POST http://localhost:11235/crawl \
     -H "Content-Type: application/json" \
     -d '{
       "urls": ["https://example.com"],
       "crawler_config": {
         "extraction_strategy": {
           "type": "LLMExtractionStrategy",
           "llm_config": {
             "provider": "deepseek/deepseek-chat",
             "api_token": "${DEEPSEEK_API_KEY}"
           },
           "instruction": "Extract main content"
         }
       }
     }'
   ```

## Azure Deployment Setup

### Option A: Environment Variables (Simple)

Add API key as environment variable in Azure Container Apps:

```bash
az containerapp update \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --set-env-vars DEEPSEEK_API_KEY=sk-your-actual-key
```

**Warning**: Environment variables visible in Azure Portal to anyone with access.

### Option B: Key Vault (Secure - Recommended)

Store API key securely in Azure Key Vault:

```bash
# 1. Add secret to Key Vault
az keyvault secret set \
  --vault-name crawl4ai-v2-keyvault \
  --name deepseek-api-key \
  --value "sk-your-actual-key"

# 2. Reference in Container App
az containerapp update \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --set-env-vars DEEPSEEK_API_KEY=secretref:deepseek-api-key
```

### Verify Azure Configuration

```bash
# Test production endpoint with LLM extraction
curl -X POST https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/crawl \
  -H "Authorization: Bearer as070511sip772patat" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://www.nokia.com/fi_fi/"],
    "crawler_config": {
      "extraction_strategy": {
        "type": "LLMExtractionStrategy",
        "llm_config": {
          "provider": "deepseek/deepseek-chat"
        },
        "instruction": "Extract company contact information"
      }
    }
  }'
```

## LLM Provider Configuration

### DeepSeek (Recommended for Finnish Companies)
- **Cost**: $0.14 per 1M input tokens, $0.28 per 1M output tokens
- **Model**: `deepseek/deepseek-chat`
- **API Key**: Get from https://platform.deepseek.com/
- **Use for**: Cost-effective extraction at scale

### OpenAI
- **Cost**: ~$0.15 per 1M input tokens (gpt-4o-mini)
- **Model**: `openai/gpt-4o-mini`
- **API Key**: Get from https://platform.openai.com/
- **Use for**: Higher quality extraction, complex queries

### Google Gemini
- **Cost**: Free tier available, then $0.075 per 1M tokens
- **Model**: `gemini/gemini-1.5-flash`
- **API Key**: Get from https://aistudio.google.com/
- **Use for**: Large context windows (1M tokens)

## Configuration in crawl4ai

The API server reads LLM config from `deploy/docker/config.yml`:

```yaml
llm:
  provider: "deepseek/deepseek-chat"
  api_key_env: "DEEPSEEK_API_KEY"  # References environment variable
```

Or pass directly in request:

```json
{
  "extraction_strategy": {
    "type": "LLMExtractionStrategy",
    "llm_config": {
      "provider": "deepseek/deepseek-chat",
      "api_token": "${DEEPSEEK_API_KEY}"
    }
  }
}
```

## Security Checklist

- [ ] .env file created from .env.example
- [ ] .env contains actual API key
- [ ] .env is NOT committed (verify with `git status`)
- [ ] Azure Key Vault contains API key secret
- [ ] Container App references Key Vault secret
- [ ] API key works in local testing
- [ ] API key works in Azure production
- [ ] No API keys in any committed files
- [ ] No API keys in task documents or logs

## Files That Are Gitignored (Safe for Secrets)

```
.env                              # Root env file
.llm.env                         # LLM-specific env
azure-deployment/.env            # Azure deployment env
azure-deployment/secrets/        # Any secrets directory
azure-deployment/local-config.sh # Local configuration
```

## Files That Are Committed (NO SECRETS)

```
.env.example                     # Template only
azure-deployment/.env.example    # Template only
deploy/docker/.llm.env.example   # Template only
tasks/*.md                       # Task documents
```

## Next Steps

1. Create `.env` with your DeepSeek or OpenAI API key
2. Test locally with LLM extraction
3. Add API key to Azure Key Vault
4. Update Container App to reference Key Vault secret
5. Test production endpoint with LLM extraction
