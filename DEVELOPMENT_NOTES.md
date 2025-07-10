# Development Notes

This file tracks development progress and important notes for the Crawl4AI project.

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
- [x] **Bearer token**: `as070511sip772patat` (stored in crawl4ai-v2-keyvault)
- [x] **No JWT complexity**: Simple internal-use authentication
- [x] **Azure best practices**: Key Vault + managed identity
- [x] **Application-ready**: Perfect for internal service-to-service calls

### Next Steps (Future)
- [ ] Add Gemini token for content cleaning (small model with large context)
- [ ] Set up GitHub Actions for CI/CD automation
- [ ] Test with actual Finnish company websites
- [ ] Monitor production usage and optimize performance

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

*This file is maintained as we develop - add notes about decisions, learnings, and progress.*