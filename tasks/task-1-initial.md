# Task 1: Crawl4AI Update & Intelligent Scraping

Date: 2025-11-15 | Priority: HIGH

## Current Status
- Local: v0.6.3 | Upstream: v0.7.7 (4 versions behind)
- Production: `unclecode/crawl4ai:latest` (unpinned)
- Azure: crawl4ai-v2-rg / crawl4ai-v2-app (North Europe)
- Auth: Bearer token in Key Vault

## Critical Issues
1. **Security**: pyOpenSSL CVE (24.3.0 → 25.3.0 fixed in 0.7.7)
2. **Performance**: Async LLM extraction blocking bug (#1055 fixed in 0.7.7)
3. **Stability**: Unpinned Docker `latest` tag
4. **Missing v0.7.7 features**: URL deduplication, monitoring dashboard, webhook support

## Code Boundaries

**UPSTREAM** (unclecode/crawl4ai - do not modify):
- `crawl4ai/` core library, `Dockerfile`, `requirements.txt`, `pyproject.toml`

**CUSTOM** (Aitosoft):
- `azure-deployment/` - Container Apps deployment scripts
- `deploy/docker/` - API server (FastAPI wrapper)
- `.github/workflows/monitor-crawl4ai-releases.yml` - Release monitoring

## Vision: Intelligent Scraping

Use crawl4ai's built-in LLM intelligence to adapt scraping behavior:
- **Small Finnish company** (10 pages) → crawl most of site
- **Large e-commerce** (1000 pages) → only contact/about pages
- **LLM-guided decisions**: "Did we get email/phone? Stop if yes, continue if no"
- **No custom patterns** until proven necessary

## Built-in Intelligence (v0.7.7)

### 1. Smart Link Following
```python
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer

# Prioritizes relevant pages automatically
scorer = KeywordRelevanceScorer(
    keywords=["yhteystiedot", "contact", "about", "tietoja"],
    weight=1.0
)

strategy = BestFirstCrawlingStrategy(
    max_depth=2,
    max_pages=20,  # Adaptive budget
    url_scorer=scorer  # Visits most relevant pages first
)
```

### 2. LLM Extraction with Schema
```python
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from pydantic import BaseModel

class CompanyContact(BaseModel):
    company_name: str
    email: str | None
    phone: str | None
    address: str | None

extraction = LLMExtractionStrategy(
    llm_config=LLMConfig(provider="openai/gpt-4o-mini"),
    schema=CompanyContact.model_json_schema(),
    instruction="Extract contact info, return null if not found",
    input_format="fit_markdown"
)
```

### 3. Content Noise Removal
```python
from crawl4ai.content_filter_strategy import BM25ContentFilter

# Removes navigation, footers, cookies automatically
filter = BM25ContentFilter(
    user_query="contact information",
    bm25_threshold=1.0
)
```

### 4. Session Management
```python
# Multi-page crawl with state
session_id = "company_scrape"
for url in pages:
    result = await crawler.arun(url, config=CrawlerRunConfig(session_id=session_id))
```

### 5. Caching
```python
from crawl4ai import CacheMode

# Avoid re-crawling
config = CrawlerRunConfig(cache_mode=CacheMode.ENABLED)
```

## Simple MAS Integration

**Your TypeScript MAS calls crawl4ai directly via HTTP:**

```typescript
// No generated client needed - just HTTP
const response = await fetch('https://crawl4ai-v2-app.../crawl', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer as070511sip772patat',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    urls: ['https://company.fi'],
    crawler_config: {
      deep_crawl_strategy: {
        type: 'BestFirstCrawlingStrategy',
        max_depth: 2,
        max_pages: 20,
        url_scorer: {
          type: 'KeywordRelevanceScorer',
          keywords: ['yhteystiedot', 'contact'],
          weight: 1.0
        }
      },
      content_filter: {
        type: 'BM25ContentFilter',
        user_query: 'contact information'
      },
      extraction_strategy: {
        type: 'LLMExtractionStrategy',
        llm_config: { provider: 'openai/gpt-4o-mini' },
        schema: { /* CompanyContact schema */ },
        instruction: 'Extract contact info'
      }
    }
  })
});

const { results } = await response.json();
const contacts = JSON.parse(results[0].extracted_content);
```

## Action Plan

### Immediate (This Week)
1. **Merge upstream v0.7.7**
   ```bash
   git remote add upstream https://github.com/unclecode/crawl4ai.git
   git fetch upstream
   git merge upstream/main
   # Resolve conflicts in azure-deployment/, .github/workflows/
   ```

2. **Pin Docker version**
   ```bash
   # Edit azure-deployment/keyvault-deploy.sh
   IMAGE="unclecode/crawl4ai:0.7.7"  # Change from "latest"

   # Deploy
   ./azure-deployment/keyvault-deploy.sh
   ```

3. **Test intelligent scraping**
   ```bash
   curl -X POST https://crawl4ai-v2-app.../crawl \
     -H "Authorization: Bearer as070511sip772patat" \
     -H "Content-Type: application/json" \
     -d '{
       "urls": ["https://www.nokia.com/fi_fi/"],
       "crawler_config": {
         "deep_crawl_strategy": {
           "type": "BestFirstCrawlingStrategy",
           "max_depth": 2,
           "max_pages": 15,
           "url_scorer": {
             "type": "KeywordRelevanceScorer",
             "keywords": ["yhteystiedot", "ota-yhteyttä"],
             "weight": 1.0
           }
         },
         "content_filter": {
           "type": "BM25ContentFilter",
           "user_query": "contact information"
         }
       }
     }'
   ```

### Short-term (Next 2 Weeks)
1. Test with diverse Finnish companies:
   - Small site (10 pages): Should crawl most of it
   - Large e-commerce (1000 pages): Should find contact page quickly
   - Validate `BestFirstCrawlingStrategy` adapts correctly

2. Iterate on LLM extraction schema based on results

3. Monitor costs and performance (use built-in `/dashboard`)

### If Needed (Only After Testing Built-ins)
- Custom URL patterns (if `KeywordRelevanceScorer` insufficient)
- Custom extraction (if `LLMExtractionStrategy` insufficient)
- TypeScript client generation (if HTTP calls too verbose)

## Success Criteria
- [ ] v0.7.7 deployed with pinned version
- [ ] Security vulnerability patched
- [ ] Small Finnish company: extracts contact info accurately
- [ ] Large Finnish company: finds contact page without crawling 1000 pages
- [ ] Clean markdown returned (no cookie banners, navigation, footers)
- [ ] LLM costs reasonable (<$0.01 per company)

## Key Decision: Use Built-ins First
**Don't build custom solutions until proven necessary:**
- ✅ Smart link following: `BestFirstCrawlingStrategy` + `KeywordRelevanceScorer`
- ✅ Content filtering: `BM25ContentFilter` or `LLMContentFilter`
- ✅ Extraction: `LLMExtractionStrategy` with Pydantic schema
- ✅ Caching: `CacheMode.ENABLED`
- ✅ Sessions: `session_id` parameter

**Only add custom code if:**
1. Tested built-in features with 10+ Finnish companies
2. Identified specific limitation
3. No configuration change can solve it

## v0.7.7 Key Features
- Monitoring dashboard: `/dashboard` endpoint
- Async LLM parallel processing (10x faster)
- URL deduplication in deep crawl
- pyOpenSSL security fix
- Better CDP error handling

## Commands

```bash
# Update to 0.7.7
git fetch upstream && git merge upstream/main

# Pin version in deployment
sed -i 's/IMAGE="unclecode\/crawl4ai:latest"/IMAGE="unclecode\/crawl4ai:0.7.7"/' azure-deployment/keyvault-deploy.sh

# Deploy
./azure-deployment/keyvault-deploy.sh

# Monitor
az containerapp logs show --name crawl4ai-v2-app --resource-group crawl4ai-v2-rg --follow

# Check dashboard
open https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/dashboard
```

## LLM API Key Setup

**Required for LLM extraction to work:**

1. **Create .env file** (you must add actual API key)
   ```bash
   cp .env.example .env
   # Edit .env and add your DEEPSEEK_API_KEY or OPENAI_API_KEY
   ```

2. **Add to Azure Key Vault** (for production)
   ```bash
   az keyvault secret set \
     --vault-name crawl4ai-v2-keyvault \
     --name deepseek-api-key \
     --value "sk-your-actual-key"

   az containerapp update \
     --name crawl4ai-v2-app \
     --resource-group crawl4ai-v2-rg \
     --set-env-vars DEEPSEEK_API_KEY=secretref:deepseek-api-key
   ```

3. **Verify .env is gitignored** (already configured)
   ```bash
   git status  # .env should NOT appear
   ```

**See `tasks/task-2-env-setup.md` for detailed instructions.**

## Next Steps
1. Team review → approve Phase 1
2. **Setup .env with API key** (see task-2-env-setup.md)
3. Execute: merge 0.7.7, pin version, deploy
4. **Add API key to Azure Key Vault**
5. Test intelligent scraping with Nokia, Rovio, KONE
6. Document learnings
7. Only add custom code if built-ins insufficient
