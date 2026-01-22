# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Mission

**Your Role:** Primary AI developer for Aitosoft's internal web scraping service
**Upstream:** Fork of github.com/unclecode/crawl4ai
**Users:** Only Aitosoft AI agents (internal tool, no human users)

---

## Development Commands

### Setup
```bash
pip install -e .                    # Install in editable mode
crawl4ai-setup                      # Setup browsers (Playwright)
crawl4ai-doctor                     # Verify installation
```

### Running the Server
```bash
# Start the Docker API server (port 11235)
uvicorn deploy.docker.server:app --host 0.0.0.0 --port 11235

# Test health
curl http://localhost:11235/health
```

### Code Quality
```bash
black crawl4ai/ tests/              # Format code
ruff check crawl4ai/ tests/         # Lint
mypy crawl4ai/                      # Type check
pre-commit run --all-files          # All hooks
```

### Testing
```bash
pytest                              # Run all tests
pytest test-aitosoft/               # Run Aitosoft-specific tests
pytest -xvs test-aitosoft/test_fit_markdown.py  # Single test file
```

### CLI Usage
```bash
crwl https://example.com -o markdown           # Basic crawl
crwl https://example.com --deep-crawl bfs      # Deep crawl with BFS
```

---

## Architecture

### Core Classes
- **AsyncWebCrawler** - Main entry point for crawling
- **BrowserConfig** - Browser settings (headless, proxy, user agent)
- **CrawlerRunConfig** - Crawl settings (cache, markdown generator, extraction)
- **CrawlResult** - Result object with `markdown.raw_markdown`, `markdown.fit_markdown`, `links`, `extracted_content`

### Pipeline Flow
```
URL → Browser (Playwright) → HTML → Content Scraping → Markdown Generation → Content Filtering → Extraction
```

### Key Modules
| Module | Purpose |
|--------|---------|
| `crawl4ai/async_webcrawler.py` | Main crawler class |
| `crawl4ai/async_configs.py` | Configuration classes |
| `crawl4ai/extraction_strategy.py` | LLM/CSS/XPath extraction |
| `crawl4ai/content_filter_strategy.py` | PruningContentFilter, BM25ContentFilter |
| `crawl4ai/deep_crawling/` | BFS, DFS, Best-First strategies |
| `deploy/docker/server.py` | FastAPI server entry point |
| `deploy/docker/api.py` | API endpoint handlers |

### fit_markdown (Key Feature)
Use `PruningContentFilter` for cleaner LLM-friendly output:
```python
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter

config = CrawlerRunConfig(
    markdown_generator=DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.48)
    )
)
result = await crawler.arun(url, config=config)
print(result.markdown.fit_markdown)  # Cleaned content
```

---

## Testing

### Quick Test Commands

```bash
# Test a single site (saves artifacts)
python test-aitosoft/test_site.py talgraf.fi --page yhteystiedot

# Test with heavy config (for cookie walls like Accountor)
python test-aitosoft/test_site.py accountor.com/fi/finland --page suuryritykselle --config heavy

# Run Tier 1 regression (required before deploy)
python test-aitosoft/test_regression.py --tier 1 --version pre-deploy

# Run all regression tests
python test-aitosoft/test_regression.py --all --version v11
```

### Test Site Tiers

**Tier 1 (always test before deploy):**
- talgraf.fi - Cookie consent + structured contacts
- vahtivuori.fi - Email obfuscation `(at)`
- accountor.com - Cookie wall (requires `magic: true` + `scan_full_page: true`)
- monidor.fi - Clean baseline

**Quality gate:** All 4 Tier 1 sites must pass

### Key Testing Learnings

From MAS V1-V10 investigation (coordinated with aitosoft-platform repo):

| Finding | Evidence |
|---------|----------|
| **`magic: true` + `scan_full_page: true` solves cookie walls** | Accountor: 32 tokens → 14,493 tokens |
| **Raw markdown > fit_markdown for contact extraction** | PruningContentFilter removes contact data at threshold ≥0.35 |
| **LLM handles email obfuscation naturally** | JPond: all 19 `(at)` emails extracted |
| **Use `fast` config by default, `heavy` only for edge cases** | 90% of sites work with domcontentloaded (2-4s vs 30-60s) |

### Test Documentation

- [TESTING.md](TESTING.md) - Complete testing framework and best practices
- [TEST_SITES_REGISTRY.md](TEST_SITES_REGISTRY.md) - All test sites with metadata
- [test-aitosoft/](test-aitosoft/) - Test scripts and reports

---

## Key Principles

1. **Minimal changes** - Keep modifications isolated from upstream code
2. **Track everything** - Document all changes in `AITOSOFT_CHANGES.md`
3. **Security first** - No secrets in code. Use environment variables.
4. **Clear separation** - Distinguish Aitosoft code from upstream code

### Commit Messages
Always prefix commits with `[aitosoft]`:
```
[aitosoft] Add internal authentication middleware
[aitosoft] Update devcontainer setup
```

---

## 🔐 CRITICAL SECURITY RULES

**THIS IS A PUBLIC REPOSITORY. NEVER COMMIT SECRETS.**

### MANDATORY Security Checklist (For ALL Documentation Work)

Before writing ANY documentation, code examples, or making commits:

1. **❌ NEVER write the API token directly in ANY file**
   - Not in documentation files (*.md)
   - Not in code examples
   - Not in test scripts
   - Not in comments

2. **✅ ALWAYS reference the .env file instead**
   - Use: `See .env file (CRAWL4AI_API_TOKEN)`
   - Use: `export CRAWL4AI_API_TOKEN=<see-.env-file>`
   - Use: `os.getenv("CRAWL4AI_API_TOKEN")`

3. **✅ BEFORE EVERY COMMIT: Run security scan**
   ```bash
   # Search for any hardcoded tokens
   grep -r "crawl4ai-[a-z0-9]" --exclude-dir=.git --exclude=".env" .
   # This command MUST return no results
   ```

4. **✅ After writing documentation: Double-check for leaks**
   - Search the file for "crawl4ai-"
   - Search for any hex strings that look like tokens
   - Verify all examples use environment variables

### Where Secrets Belong

| ✅ SAFE | ❌ NEVER |
|---------|----------|
| `.env` file (gitignored) | DEPLOYMENT_INFO.md |
| Azure Key Vault | README.md or any *.md |
| `os.getenv()` in code | Hardcoded strings |
| `source .env` in bash | `export TOKEN="actual-token"` |

### Token Rotation Protocol

If a token is accidentally committed:

1. **Rotate immediately** in Azure (invalidates old token):
   ```bash
   NEW_TOKEN="crawl4ai-$(openssl rand -hex 24)"
   az containerapp update \
     --name crawl4ai-service \
     --resource-group aitosoft-prod \
     --set-env-vars CRAWL4AI_API_TOKEN="$NEW_TOKEN"
   ```

2. **Update .env file** with new token (do not commit)

3. **Remove from all files** that were committed:
   - Replace with `.env` references
   - Commit the sanitized files

4. **Notify MAS team** - their service will break until they update

### Example: Safe Documentation

**❌ WRONG:**
```bash
export CRAWL4AI_API_TOKEN="crawl4ai-abc123..."
```

**✅ CORRECT:**
```bash
# Load token from .env file
source .env
# Or: export CRAWL4AI_API_TOKEN=<see-crawl4ai-repo-.env-file>
```

**❌ WRONG:**
```python
CRAWL4AI_TOKEN = "crawl4ai-abc123..."
```

**✅ CORRECT:**
```python
import os
CRAWL4AI_TOKEN = os.getenv("CRAWL4AI_API_TOKEN")
```

---

## What's Ours vs Upstream

### 100% Upstream (Don't modify)
- `crawl4ai/` - Core crawler library
- `deploy/docker/api.py` - API handlers
- `deploy/docker/crawler_pool.py` - Browser pool management
- All other files in `deploy/docker/` (except those listed below)

### Aitosoft Modifications (Our changes to upstream)
- `deploy/docker/server.py` - **Modified** (added 3 lines to enable SimpleTokenAuthMiddleware)
- `deploy/docker/config.yml` - **Modified** (enabled security: true)
- `deploy/docker/simple_token_auth.py` - **New** (our custom auth middleware, 39 lines)

### 100% Aitosoft Code (Safe to modify)
- `azure-deployment/` - All deployment scripts and docs
- `test-aitosoft/` - Our test suite
- `.devcontainer/` - Dev container setup
- `CLAUDE.md` - This file
- `AITOSOFT_CHANGES.md` - Change tracking
- `DEPLOYMENT_INFO.md` - Production deployment info

---

## Important Documentation

**Start here each session:**
- `AITOSOFT_FILES.md` - Quick reference: What's ours vs upstream
- `AITOSOFT_CHANGES.md` - What we've modified and why
- `DEPLOYMENT_INFO.md` - Current production deployment info

**For specific tasks:**
- **Deployments**: `DEPLOYMENT_INFO.md` + `azure-deployment/deploy-aitosoft-prod.sh`
- **Auth details**: `azure-deployment/SIMPLE_AUTH_DEPLOY.md`
- **Upstream sync**: Check `AITOSOFT_FILES.md` for conflict points

---

## Azure Deployment

**Current Production:**
- Location: West Europe (aitosoft-prod resource group)
- Uses existing infrastructure (aitosoftacr, aitosoft-aca)
- Simple Bearer token authentication enabled
- See `DEPLOYMENT_INFO.md` for endpoint and credentials

**To deploy updates:**
```bash
./azure-deployment/deploy-aitosoft-prod.sh
```

**To view current deployment:**
```bash
# Read the current state
cat DEPLOYMENT_INFO.md
```

---

## Working with Upstream

This is a fork of `github.com/unclecode/crawl4ai` - keep changes minimal for easier merges:

**Golden Rules:**
- ✅ Add new files in `azure-deployment/` and `test-aitosoft/`
- ✅ Minimize modifications to upstream files
- ✅ Document ALL changes in `AITOSOFT_CHANGES.md`
- ✅ Use `[aitosoft]` prefix in commit messages
- ❌ Never refactor upstream code
- ❌ Don't modify `crawl4ai/` core library

**Syncing with upstream:**
```bash
git fetch upstream
git merge upstream/main
# Check AITOSOFT_CHANGES.md for conflicts with our modifications
```

**Our modifications are minimal:**
- Only 42 lines of code changed from upstream (see "What's Ours vs Upstream" above)
- Easy to maintain when upstream updates

---

## Cross-Repo Communication

This repo works alongside `aitosoft-platform` (main multi-agent system). Both have Claude as developer.

**To get info from the other repo:**
1. Formulate a specific question
2. Ask the business owner to relay it
3. Wait for the response

Use for: API contracts, deployment patterns, auth coordination.
