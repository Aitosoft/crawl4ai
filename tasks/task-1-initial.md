# Task 1: Crawl4AI Status & Reactivation

Date: 2025-11-15 | Priority: HIGH

## Status
- Local: v0.6.3 | Upstream: v0.7.7 (4 versions behind)
- Production: `unclecode/crawl4ai:latest` (unpinned)
- Azure: crawl4ai-v2-rg / crawl4ai-v2-app (North Europe)
- Auth: Bearer token `as070511sip772patat` in Key Vault

## Critical Issues
1. Security: pyOpenSSL CVE (24.3.0 → 25.3.0 in v0.7.7)
2. Performance: Async LLM extraction blocking (#1055 fixed in 0.7.7)
3. Stability: Unpinned Docker version in production
4. Missing: URL deduplication for Finnish sites (0.7.7 feature)
5. Missing: Monitoring dashboard `/dashboard` (0.7.7)
6. Missing: Webhook infrastructure for TypeScript MAS (0.7.6+)

## Code Structure

### UPSTREAM (unclecode/crawl4ai - do not modify)
- `crawl4ai/` - Core library (63 files)
- `Dockerfile`, `docker-compose.yml`
- `requirements.txt`, `pyproject.toml`

### CUSTOM (Aitosoft modifications)
- `azure-deployment/` - Container Apps deployment
  - `keyvault-deploy.sh` - Production deploy script
  - `simple_auth.py` - Bearer token auth (diverges from upstream JWT)
  - `custom_server.py` - Azure FastAPI wrapper
  - `production-config.yml` - 20 max pages, 85% memory threshold
- `deploy/docker/` - API server
  - `server.py`, `api.py` - FastAPI REST API
  - `auth.py` - JWT authentication
  - `crawler_pool.py` - Browser pooling (30min idle TTL, 95% memory cap)
- `.github/workflows/` - CI/CD
  - `monitor-crawl4ai-releases.yml` - Daily upstream checks
- `.devcontainer/` - Python 3.11, Node 20, Azure CLI

## Finnish Company Scraping Requirements

### Target Data
- Contact: email, phone, address
- Company: offering, customer segments, value proposition
- Exclude: `/blogi/`, `/uutiset/`, `/tietosuoja`, product pages, blogs, privacy notices
- Avoid: Cookie consent, duplicate sections

### Current Gaps
1. No URL exclusion patterns
2. No `JsonCssExtractionStrategy` for contacts
3. No Finnish stemmer for BM25 filter
4. No schema.org extraction
5. No cookie consent removal

### Extraction Strategy (implement in Phase 3)

```python
# Phase 1: Contact extraction
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

contact_schema = {
    "name": "Company Contact",
    "baseSelector": "body",
    "fields": [
        {"name": "email", "selector": "a[href^='mailto:']", "type": "attribute", "attribute": "href"},
        {"name": "phone", "selector": "a[href^='tel:'], .contact-phone", "type": "text"},
        {"name": "address", "selector": ".address, [itemtype*='PostalAddress']", "type": "text"}
    ]
}

# Phase 2: Company info
from crawl4ai.extraction_strategy import LLMExtractionStrategy

llm_instruction = """Extract JSON: {"company_name": "", "offering": "", "target_customers": "", "value_proposition": ""}
Ignore blogs, news, privacy policies, cookies. Language: Finnish or English."""

# Phase 3: URL filtering
exclude_patterns = [r'/blog/', r'/blogi/', r'/article/', r'/artikkeli/', r'/news/', r'/uutiset/',
                   r'/privacy', r'/tietosuoja', r'/cookie', r'/evastekaytanto', r'/product/\d+', r'/tuote/\d+']

crawler_config = {
    "exclude_patterns": exclude_patterns,
    "max_depth": 2,
    "url_deduplication": True  # Requires 0.7.7+
}
```

## TypeScript Integration (Phase 4)

### Current State
- No TypeScript client
- No type safety
- Manual HTTP calls from MAS

### Implementation

```bash
# Generate OpenAPI client
openapi-typescript-codegen \
  --input https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/openapi.json \
  --output ./typescript-client --client fetch
```

```typescript
// Webhook receiver (requires 0.7.6+)
app.post('/webhooks/crawl4ai', async (req, res) => {
  const { job_id, status, result } = req.body;
  if (status === 'completed') await processCompanyData(result);
  res.status(200).send('OK');
});

// WebSocket monitor (requires 0.7.7+)
const ws = new WebSocket('wss://your-app/monitor/stream');
ws.on('message', (data) => logStatus(JSON.parse(data)));
```

## Action Plan

### Phase 1: Security & Stability (Week 1) - 2 dev days
1. Merge upstream v0.7.7
2. Edit `azure-deployment/keyvault-deploy.sh`: `IMAGE="unclecode/crawl4ai:0.7.7"`
3. Deploy: `./azure-deployment/keyvault-deploy.sh --update-only`
4. Test: Health, auth, fit_markdown, Finnish sample

### Phase 2: Monitoring (Week 2)
1. Access `/dashboard` endpoint
2. Configure Prometheus → Azure Monitor
3. Set up alerts: browser pool exhaustion, memory >95%, fail rate >10%
4. WebSocket monitoring in MAS

### Phase 3: Finnish Optimization (Week 3-4)
1. Implement `contact_schema` + `llm_instruction`
2. Add `exclude_patterns` for Finnish sites
3. Configure Finnish stemmer: `snowballstemmer.stemmer('finnish')`
4. Test: nokia.fi, rovio.com, kone.com/fi, fortum.fi
5. Validate: contact accuracy >90%, no duplicates

### Phase 4: TypeScript Integration (Week 5-6)
1. Generate OpenAPI client
2. Create `FinnishCompanyScraper` wrapper class
3. Implement webhook receiver in MAS
4. End-to-end test: MAS → Crawl4AI → Webhook → MAS

### Phase 5: Modernization (Ongoing)
1. Update `.devcontainer/devcontainer.json`: Python 3.12, Node 22
2. Create `ARCHITECTURE.md`: upstream vs custom boundaries
3. CI/CD: `tests/test_finnish_companies.py`
4. Document upgrade checklist

## Tech Stack Updates

Current → Recommended:
- Python: 3.11 → 3.12 (align with Docker)
- Node.js: 20 → 22 LTS
- Playwright: 1.49.0+ → latest
- Dev container: Add Docker-in-Docker, ESLint, Prettier

## Key Metrics

### Performance
- Crawl latency: p50, p95, p99
- Browser pool utilization
- Memory peaks
- Concurrent capacity

### Quality
- Contact extraction accuracy: target >90%
- Finnish company coverage
- Duplicate detection rate
- Success rate per .fi domain

### Business
- Companies/hour
- Cost/company (Azure compute)
- MAS task completion time

## Authentication Decision

Current: Dual auth (JWT dev, bearer token prod)
Options:
A. Keep dual (recommended for internal use)
B. Standardize JWT (better security, more complex)
C. Azure AD (overkill for internal)

Recommendation: Keep dual, document in ARCHITECTURE.md

## Success Criteria

Phase 1: v0.7.7 deployed, pinned version, security patched, tests passing
Phase 2: Dashboard accessible, metrics exporting, alerts configured
Phase 3: Finnish extraction working, 10+ companies scraped, accuracy >90%
Phase 4: TypeScript client integrated, webhooks handling async jobs
Phase 5: Architecture documented, CI/CD testing Finnish scraping

## Immediate Actions (This Week)
1. Team review → decide on Phase 1 start
2. Execute Phase 1: merge 0.7.7, pin version, deploy
3. Test with Finnish samples
4. Document learnings

## Cost-Benefit

Update cost: ~2 dev days
Benefits: Security fix, 10x faster async LLM, monitoring, URL dedup
Risk of not updating: Vulnerability, growing tech debt, blocked features

Recommendation: Proceed with 5-phase plan immediately

## Commands Reference

```bash
# Upstream sync
git remote add upstream https://github.com/unclecode/crawl4ai.git
git fetch upstream
git merge upstream/main  # Preserve custom files in azure-deployment/, .github/workflows/, .devcontainer/

# Deploy
./azure-deployment/keyvault-deploy.sh

# Monitor
az containerapp logs show --name crawl4ai-v2-app --resource-group crawl4ai-v2-rg --follow

# Generate TypeScript client
openapi-typescript-codegen --input https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/openapi.json --output ./typescript-client --client fetch

# Test Finnish company
curl -X POST https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/crawl \
  -H "Authorization: Bearer as070511sip772patat" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://www.nokia.com/fi_fi/"], "crawler_config": {"exclude_patterns": ["/blogi/", "/uutiset/"], "max_depth": 2}}'
```

## Version 0.7.7 Changelog (Key Items)
- Monitoring dashboard at `/dashboard` with WebSocket streaming
- Async LLM extraction fix (#1055) - parallel processing
- pyOpenSSL 24.3.0 → 25.3.0 (CVE fix)
- URL deduplication in DFS deep crawl
- 3-tier browser pool with janitor
- CDP endpoint verification with exponential backoff
- Better HTTP error handling
- Webhook infrastructure (v0.7.6)

## Questions for Team
1. Keep dual auth or standardize JWT?
2. Update dev container to Python 3.12 now or after Phase 1?
3. Azure Monitor or separate Grafana?
4. TypeScript client: monorepo or NPM package?
5. Current Azure monthly cost? Projected scaling cost?
6. Where to store scraped data: Azure SQL, Cosmos DB, or MAS database?
