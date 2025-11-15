# Task 1: Crawl4AI Update & Intelligent Scraping

Date: 2025-11-15 | Priority: HIGH

## Business Need

MAS AI agents call crawl4ai with homepage URL to discover and extract Finnish company content.

**Constraints:**
- Start with homepage URL only (no sitemap knowledge)
- Sites vary: 1 page to 1000+ pages
- Languages: Finnish primary, English fallback
- LLM: DeepSeek 3.2 (100k token limit, very cheap)
- Need deterministic cleaning BEFORE LLM to save tokens
- Return clean markdown without navigation, footers, cookie banners

**Goal:** Simple, robust extraction using crawl4ai built-ins only.

## Current Status
- Local: v0.6.3 | Upstream: v0.7.7 (4 versions behind)
- Production: `unclecode/crawl4ai:latest` (unpinned)
- Azure: crawl4ai-v2-rg / crawl4ai-v2-app (North Europe)

## Critical Issues
1. Security: pyOpenSSL CVE (fixed in 0.7.7)
2. Performance: Async LLM blocking bug (fixed in 0.7.7)
3. Stability: Unpinned Docker `latest` tag

## Code Boundaries

**UPSTREAM** (don't modify): `crawl4ai/`, `Dockerfile`, `requirements.txt`, `pyproject.toml`
**CUSTOM**: `azure-deployment/`, `deploy/docker/`, `.github/workflows/monitor-crawl4ai-releases.yml`

## Built-in Features for Your Use Case

### 1. URL Discovery from Homepage (No Sitemap Parser)

**What exists:**
- BestFirstCrawlingStrategy with `max_pages` hard limit
- KeywordRelevanceScorer prioritizes relevant pages first
- Automatic internal/external link classification

**No sitemap.xml support** - use deep crawling instead:

```python
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer

# Discover URLs from homepage, prioritize by relevance
scorer = KeywordRelevanceScorer(
    keywords=["yhteystiedot", "tuotteet", "contact", "products"],
    weight=1.0
)

strategy = BestFirstCrawlingStrategy(
    max_depth=2,          # Homepage + 2 levels deep
    max_pages=30,         # CRITICAL: Hard limit for token control
    url_scorer=scorer,    # Crawls most relevant pages first
    include_external=False
)
```

### 2. Deterministic Token Reduction (Pre-LLM)

**CRITICAL: All run BEFORE LLM to save tokens**

**BM25ContentFilter** (60-90% token reduction):
```python
from crawl4ai.content_filter_strategy import BM25ContentFilter

# Removes low-relevance content chunks using BM25 scoring
filter = BM25ContentFilter(
    user_query="Finnish company contact product information",
    bm25_threshold=1.2,  # Higher = more aggressive filtering
    language="finnish"   # Uses Finnish stemmer
)
```

**PruningContentFilter** (60-80% token reduction):
```python
from crawl4ai.content_filter_strategy import PruningContentFilter

# Removes navigation, footers, low-density text
filter = PruningContentFilter(
    threshold=0.48,
    threshold_type="dynamic",
    min_word_threshold=10  # Remove blocks <10 words
)
```

**HTML-level cleaning** (always happens):
```python
config = CrawlerRunConfig(
    excluded_tags=['nav', 'footer', 'header', 'aside', 'script', 'style'],
    word_count_threshold=10,
    exclude_external_links=True,
    exclude_social_media_links=True
)
```

### 3. fit_markdown vs raw_markdown (60-90% Token Savings)

**CRITICAL: Use fit_markdown for LLM input**

```python
result = await crawler.arun(url, config=config)

# DON'T use this (full page content):
raw = result.markdown.raw_markdown  # 5,000-20,000 tokens

# USE this (filtered content):
fit = result.markdown.fit_markdown  # 1,000-5,000 tokens (60-90% smaller)
```

`fit_markdown` uses your `content_filter` results. Much more token-efficient.

### 4. Finnish Language Support

**Built-in Finnish stemmer:**
```python
BM25ContentFilter(
    user_query="tuote hinta yhteystiedot toimitus",
    language="finnish",  # Uses Finnish snowball stemmer
    bm25_threshold=1.2
)
```

**Language preference header:**
```python
config = CrawlerRunConfig(
    headers={"Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8"}
)
```

### 5. Token Estimation & Limiting (DeepSeek 100k Limit)

**Built-in token estimation:**
```python
def estimate_tokens(text: str) -> int:
    """Estimate tokens using crawl4ai's WORD_TOKEN_RATE"""
    return int(len(text.split()) * 1.3)

fit_markdown = result.markdown.fit_markdown
tokens = estimate_tokens(fit_markdown)

if tokens > 90000:  # Leave 10k buffer for DeepSeek
    print(f"⚠️ {tokens} tokens exceeds limit!")
```

**Hard page limit to control total tokens:**
```python
BestFirstCrawlingStrategy(
    max_pages=30  # Stops after 30 pages regardless of relevance
)
```

## Complete Configuration for Finnish Companies

```typescript
// Your MAS agent calls crawl4ai with this configuration
const response = await fetch('https://crawl4ai-v2-app.../crawl', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer as070511sip772patat',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    urls: ['https://company.fi'],  // Homepage only
    crawler_config: {
      // 1. URL Discovery (crawls max 30 pages, prioritized)
      deep_crawl_strategy: {
        type: 'BestFirstCrawlingStrategy',
        max_depth: 2,
        max_pages: 30,  // CRITICAL: Token budget control
        include_external: false,
        url_scorer: {
          type: 'KeywordRelevanceScorer',
          keywords: ['yhteystiedot', 'tuotteet', 'tietoja', 'contact', 'products', 'about'],
          weight: 1.0
        }
      },

      // 2. Deterministic Pre-LLM Cleaning (saves 60-90% tokens)
      markdown_generator: {
        type: 'DefaultMarkdownGenerator',
        content_filter: {
          type: 'BM25ContentFilter',
          user_query: 'Finnish company contact product information',
          bm25_threshold: 1.2,
          language: 'finnish'
        }
      },

      // 3. HTML-level filtering
      excluded_tags: ['nav', 'footer', 'header', 'aside', 'script', 'style'],
      word_count_threshold: 10,
      exclude_external_links: true,

      // 4. Language preference
      headers: {
        'Accept-Language': 'fi-FI,fi;q=0.9,en;q=0.8'
      },

      // 5. Stream results as they arrive
      stream: true
    }
  })
});

// Process results
const { results } = await response.json();
for (const result of results) {
  // CRITICAL: Use fit_markdown, not raw_markdown
  const cleanMarkdown = result.markdown.fit_markdown;

  // Estimate tokens before sending to DeepSeek
  const tokens = Math.floor(cleanMarkdown.split(' ').length * 1.3);

  if (tokens < 90000) {  // DeepSeek 100k limit with buffer
    // Send to DeepSeek for extraction
    await deepseekExtract(cleanMarkdown);
  }
}
```

## Handling Different Site Sizes

### Small Site (1-10 pages)
```json
{
  "deep_crawl_strategy": {
    "type": "BFSDeepCrawlStrategy",
    "max_depth": 3,
    "max_pages": 10
  }
}
```
Result: Crawls entire site, each page ~1k-3k tokens with fit_markdown.

### Large Site (1000+ pages)
```json
{
  "deep_crawl_strategy": {
    "type": "BestFirstCrawlingStrategy",
    "max_depth": 2,
    "max_pages": 30,
    "url_scorer": {
      "type": "KeywordRelevanceScorer",
      "keywords": ["yhteystiedot", "contact"],
      "weight": 1.0
    }
  }
}
```
Result: Only crawls 30 most relevant pages (contact, about, products), skips blog/product catalog.

## Action Plan

### Immediate (This Week)

1. **Merge upstream v0.7.7**
   ```bash
   git remote add upstream https://github.com/unclecode/crawl4ai.git
   git fetch upstream
   git merge upstream/main
   ```

2. **Pin Docker version**
   ```bash
   # Edit azure-deployment/keyvault-deploy.sh
   IMAGE="unclecode/crawl4ai:0.7.7"

   # Deploy
   ./azure-deployment/keyvault-deploy.sh
   ```

3. **Setup LLM API key**
   ```bash
   cp .env.example .env
   # Add your DEEPSEEK_API_KEY or OPENAI_API_KEY

   # Add to Azure Key Vault
   az keyvault secret set \
     --vault-name crawl4ai-v2-keyvault \
     --name deepseek-api-key \
     --value "sk-your-key"

   az containerapp update \
     --name crawl4ai-v2-app \
     --resource-group crawl4ai-v2-rg \
     --set-env-vars DEEPSEEK_API_KEY=secretref:deepseek-api-key
   ```

4. **Test with Finnish companies**
   ```bash
   # Small site test
   curl -X POST https://crawl4ai-v2-app.../crawl \
     -H "Authorization: Bearer as070511sip772patat" \
     -d '{
       "urls": ["https://small-company.fi"],
       "crawler_config": {
         "max_pages": 10,
         "markdown_generator": {
           "content_filter": {
             "type": "BM25ContentFilter",
             "language": "finnish"
           }
         }
       }
     }'

   # Large site test
   curl -X POST https://crawl4ai-v2-app.../crawl \
     -H "Authorization: Bearer as070511sip772patat" \
     -d '{
       "urls": ["https://large-ecommerce.fi"],
       "crawler_config": {
         "deep_crawl_strategy": {
           "type": "BestFirstCrawlingStrategy",
           "max_pages": 30,
           "url_scorer": {
             "type": "KeywordRelevanceScorer",
             "keywords": ["yhteystiedot", "tietoja"]
           }
         },
         "markdown_generator": {
           "content_filter": {
             "type": "BM25ContentFilter",
             "bm25_threshold": 1.2,
             "language": "finnish"
           }
         }
       }
     }'
   ```

### Short-term (Next 2 Weeks)

1. **Test token efficiency**
   - Verify fit_markdown is 60-90% smaller than raw_markdown
   - Confirm BM25ContentFilter removes garbage (nav, footer, cookies)
   - Validate Finnish stemmer improves relevance

2. **Test different site types**
   - 1-page site: Ensure no over-crawling
   - 10-page site: Crawl most pages
   - 1000-page site: Only top 30 relevant pages
   - Validate total tokens stay under 90k for DeepSeek

3. **Validate Finnish/English handling**
   - Primarily Finnish sites: Finnish stemmer + keywords
   - Multilingual sites: Fallback to English
   - Verify Accept-Language header works

4. **Monitor costs**
   - DeepSeek cost per company (<$0.01 expected)
   - Token usage per page (1k-5k with fit_markdown)
   - Crawl time per company

### Only If Needed (After Testing)
- Custom URL patterns (if KeywordRelevanceScorer insufficient)
- Custom content filter (if BM25ContentFilter insufficient)
- TypeScript client (if HTTP calls too verbose)

## Success Criteria

- [ ] v0.7.7 deployed, pinned version
- [ ] Security vulnerability patched
- [ ] Small site (10 pages): Extracts contact info, <10k total tokens
- [ ] Large site (1000 pages): Finds contact page in top 30 crawled pages, <30k total tokens
- [ ] fit_markdown is 60-90% smaller than raw_markdown
- [ ] Navigation, footers, cookie banners removed deterministically
- [ ] Finnish content prioritized over other languages
- [ ] Total tokens stay under 90k for DeepSeek (with 10k buffer)
- [ ] Cost <$0.01 per company with DeepSeek

## Key Decisions

**Use crawl4ai built-ins:**
- ✅ URL discovery: `BestFirstCrawlingStrategy` + `max_pages`
- ✅ Deterministic cleaning: `BM25ContentFilter` (pre-LLM)
- ✅ Token efficiency: `fit_markdown` (60-90% smaller)
- ✅ Finnish support: `language="finnish"` in BM25
- ✅ Token limiting: `max_pages` + token estimation

**Don't build custom solutions until:**
1. Tested with 10+ Finnish companies
2. Identified specific limitation
3. No configuration can solve it

## v0.7.7 Key Features
- Monitoring dashboard: `/dashboard`
- Async LLM parallel processing (10x faster)
- URL deduplication in deep crawl
- pyOpenSSL security fix
- Better CDP error handling

## Commands

```bash
# Update to 0.7.7
git fetch upstream && git merge upstream/main

# Pin version
sed -i 's/IMAGE="unclecode\/crawl4ai:latest"/IMAGE="unclecode\/crawl4ai:0.7.7"/' azure-deployment/keyvault-deploy.sh

# Deploy
./azure-deployment/keyvault-deploy.sh

# Monitor
az containerapp logs show --name crawl4ai-v2-app --resource-group crawl4ai-v2-rg --follow

# Dashboard
open https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/dashboard
```

## Next Steps
1. Setup .env with DeepSeek API key
2. Execute: merge 0.7.7, pin version, deploy
3. Add API key to Azure Key Vault
4. Test with small/large Finnish companies
5. Validate token efficiency (fit_markdown vs raw_markdown)
6. Measure costs with DeepSeek
7. Document learnings
