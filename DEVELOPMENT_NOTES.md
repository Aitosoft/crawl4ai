# Development Notes

This file tracks development progress and important notes for the Crawl4AI project.

**Last Updated**: 2026-01-19

## 2026-01-19: v0.8.0 Upgrade & Security Hardening

### Major Milestone: Upgraded to Crawl4AI v0.8.0

**Version Changes:**
- Local: v0.7.1 → v0.8.0 ✅
- Production: v0.6.0 → v0.8.0 (pending deployment)
- Docker Image: `latest` → `0.8.0` (pinned version)

**Critical Security Fixes in v0.8.0:**
- 🔒 **RCE Fix**: Removed `__import__` from hook allowed builtins (Neo by ProjectDiscovery)
- 🔒 **LFI Fix**: Added URL scheme validation, blocked file://, javascript:, data: URLs (Neo by ProjectDiscovery)

**Security Improvements Made:**
- ✅ Rotated all API tokens (Azure Key Vault + GitHub Secrets + local .env)
- ✅ Removed all hardcoded tokens from documentation and workflows
- ✅ Added comprehensive .env patterns to .gitignore (.env.*, *.env)
- ✅ Created .env.example template for secure onboarding
- ✅ Added notes-to-claude.md to .gitignore
- ✅ Fixed GitHub Actions workflow to use secrets.C4AI_TOKEN
- ✅ Documented token rotation procedure (TOKEN_ROTATION_GUIDE.md)
- ✅ Updated pre-commit config to exclude GitHub Actions YAML from strict checking

**New Token (Generated 2026-01-19):**
- Algorithm: `openssl rand -hex 32`
- Storage: Azure Key Vault (C4AI-TOKEN), GitHub Secrets (C4AI_TOKEN), .env.local (CRAWL4AI_API_TOKEN)
- **Next Rotation Due**: 2026-04-19 (90 days)

**Dependency Changes:**
- ✅ Python requirement: 3.9 → 3.10 (we use 3.11, so compatible)
- ✅ New: `patchright>=1.49.0` (stealth browser for anti-bot detection)
- ✅ New: `anyio>=4.0.0` (async utilities)
- ✅ New: `PyYAML>=6.0` (YAML configuration support)
- ✅ Updated: `pyOpenSSL 24.3.0 → 25.3.0` (security fix)
- ✅ **REMOVED from core**: `sentence-transformers` (now optional, saves ~500MB)

**Breaking Changes (No Impact on Aitosoft):**
- Hooks disabled by default (we don't use hooks)
- file:// URLs blocked in Docker API (we only use http/https)

**Documentation Created:**
- [azure-deployment/V0.8.0_UPGRADE_SUMMARY.md](azure-deployment/V0.8.0_UPGRADE_SUMMARY.md) - Comprehensive upgrade analysis
- [azure-deployment/TOKEN_ROTATION_GUIDE.md](azure-deployment/TOKEN_ROTATION_GUIDE.md) - Step-by-step rotation procedure
- [.env.example](.env.example) - Template for local development

**Git History:**
- Commit: `4726c2f` - Security improvements and v0.8.0 preparation
- Commit: `649a30f` - Merged v0.8.0 from upstream

**Testing Status:**
- ✅ Local installation verified (v0.8.0)
- ✅ Dependencies installed successfully
- ⏳ Production deployment pending
- ⏳ Production validation pending

**Next Steps:**
1. Deploy v0.8.0 to Azure production
2. Validate production health check + auth
3. Test markdown extraction (raw + fit_markdown)
4. Monitor for 24 hours
5. Update multi-agent platform with new token

---

## Previous Updates

### 2025-07-24: Version Management and Dependency Resolution

## Current Development Environment

### System Setup
- **Device**: Windows 11 ARM-based laptop (Snapdragon X Elite CPU, 32GB RAM)
- **Development**: WSL2 Ubuntu 24.04 LTS + Dev Container
- **Project Location**: `~/code/crawl4ai` (Linux-native folder)
- **Working Directory**: `/workspaces/crawl4ai` (inside Dev Container)

### Dev Container Details
- **Base Image**: Python 3.11 on Debian Bookworm
- **Key Features**: Node.js 20, Azure CLI, browser dependencies pre-installed
- **Server Port**: 11235 (forwarded for local testing)
- **Memory**: 1GB shared memory for browser operations
- **Tools**: All Python dev tools (ruff, black, mypy, pytest, pre-commit) pre-installed

### Development Workflow
1. Open project: `cd ~/code/crawl4ai && code .`
2. Choose "Reopen in Container" when prompted
3. All tools available immediately in container
4. Start server: `uvicorn deploy.docker.server:app --host 0.0.0.0 --port 11235`
5. Test at: `http://localhost:11235`

## Current Status

### Completed
- [x] Dev Container fully configured and working
- [x] All dependencies installed automatically
- [x] Server starts without errors
- [x] API endpoints responding correctly
- [x] CLAUDE.md created with comprehensive development guidance
- [x] **fit_markdown configuration verified and working**
- [x] **Azure deployment files created and tested**
- [x] **JWT authentication configured for production**
- [x] **Complete deployment guide written**
- [x] **Deployment scripts ready for Azure Container Apps**

### Production Deployment Complete
- [x] **Azure Container Apps deployed**: `crawl4ai-v2-rg` resource group
- [x] **Simplified authentication**: Bearer token with Azure Key Vault integration
- [x] **fit_markdown verified**: Working correctly in production
- [x] **Key Vault security**: Token stored securely, accessed via managed identity
- [x] **Production URL**: https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io
- [x] **Complete documentation**: Updated for production deployment

### Authentication Simplified
- [x] **Bearer token**: Retrieved from environment variable `C4AI_TOKEN` (stored in crawl4ai-v2-keyvault)
- [x] **No JWT complexity**: Simple internal-use authentication
- [x] **Azure best practices**: Key Vault + managed identity
- [x] **Application-ready**: Perfect for internal service-to-service calls

### Next Steps (Future)
- [ ] Add Gemini token for content cleaning (small model with large context)
- [x] Set up GitHub Actions for CI/CD automation *(2025-07-21)*
- [x] Resolve v0.7.1 dependency issues for local testing *(2025-07-24)*
- [ ] Test new v0.7.1 features with Finnish company websites
- [ ] Evaluate when to upgrade production from v0.6.0 to v0.7.x
- [ ] Monitor production usage and optimize performance
- [ ] Set up GitHub secrets for Azure authentication in new workflows

## Key Development Practices

### For Beginners
- **Always work inside the Dev Container** - tools installed in WSL won't be visible
- **Use Linux-native paths** - never use Windows mounted folders like `/mnt/c/`
- **Container handles all setup** - no manual PYTHONPATH exports needed
- **Git operations** - perform inside Dev Container for consistency

### Testing the Server
```bash
# Start the server
uvicorn deploy.docker.server:app --host 0.0.0.0 --port 11235

# Test with curl
curl -X POST http://localhost:11235/crawl \
  -H "Content-Type: application/json" \
  -d '{"urls": "https://example.com", "priority": 10}'
```

## Development Questions & Decisions

### Architecture Understanding
- Main crawler class: `AsyncWebCrawler`
- Configuration: `BrowserConfig` + `CrawlerRunConfig`
- Results: `CrawlResult` with metadata and extracted content
- Pipeline: Browser → Content Scraping → Markdown → Filtering → Extraction

### Immediate Focus Areas
1. **Documentation** - Document all changes and learnings
2. **Beginner-friendly explanations** - Keep all guidance clear and simple
3. **Testing** - Understand and use the existing test suite
4. **Code quality** - Use pre-installed tools (ruff, black, mypy)

## Notes for Future Development

### Code Quality Commands
```bash
# Format code
black crawl4ai/ tests/

# Check types
mypy crawl4ai/

# Lint code
ruff check crawl4ai/ tests/

# Run tests
python -m pytest

# Run pre-commit hooks
pre-commit run --all-files
```

### Common Tasks
- **Add new features**: Follow existing patterns in the codebase
- **Test changes**: Always run tests before committing
- **Document changes**: Update both code comments and documentation
- **Commit changes**: Use clear, descriptive commit messages

### Environment Variables
- `PYTHONPATH`: Automatically set by Dev Container
- Future: Will add Gemini API token for content cleaning

---

## Development History

### 2025-07-21: CI/CD Pipeline Implementation
- **Added**: GitHub Actions for crawl4ai release monitoring and automated updates
- **Files**: `.github/workflows/monitor-crawl4ai-releases.yml`, `.github/workflows/update-crawl4ai.yml`
- **Added**: Test orchestration script `run_validation_tests.py`
- **Enhanced**: Deployment script with rollback capabilities (`--rollback`, `--list-revisions`)
- **Features**: Automated testing, rollback on failure, Discord notifications, issue creation
- **Usage**: Manual trigger via GitHub Actions → "Update Crawl4AI and Test"

### 2025-07-23: Test Files Organization
- **Moved**: Test files to `test-aitosoft/` folder to separate custom code from upstream repo
- **Files**: `test_fit_markdown.py`, `test_production_auth.py`, `test_server_api.py`
- **Updated**: CI/CD workflows and test orchestration script to use new paths

### 2025-07-24: Version Management and Dependency Resolution
- **Issue**: Upstream merge to v0.7.1 introduced new dependencies causing test failures
- **Resolution**: Installed missing dependencies (`lark`, `sentence-transformers`, `alphashape`, `shapely`, `pdf2image`, `PyPDF2`)
- **Codebase Version**: Updated to Crawl4AI v0.7.1 for local development and testing
- **Production Strategy**: Maintains `unclecode/crawl4ai:latest` (v0.6.0 stable) for production deployment
- **Files Updated**: `CLAUDE.md` and `DEVELOPMENT_NOTES.md` to document version strategy
- **Test Status**: All `test-aitosoft/` tests now working with v0.7.1 dependencies
- **Rationale**: Allows testing new v0.7.1 features locally while keeping production stable with proven v0.6.0

---

*This file is maintained as we develop - add new entries to the Development History section with date and brief summary.*
