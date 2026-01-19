# Development Notes

This file tracks development progress and important notes for the Crawl4AI project.

**Last Updated**: 2026-01-19

---

## Current State (2026-01-19)

### Version
- **Local**: v0.8.0 ✅
- **Production**: Pending deployment to v0.8.0
- **Docker Image**: Pinned to `0.8.0`

### Environment
- **Host**: Windows 11 (Snapdragon X Elite, 32GB RAM)
- **Local Path**: `c:\src\crawl4ai-aitosoft` → `/workspaces/crawl4ai-aitosoft`
- **Dev Container**: Python 3.11 on Debian Bookworm
- **Key Tools**: Node.js 20, Azure CLI, GitHub CLI, Claude Code

### Authentication
- **Azure**: Logged into Aitosoft subscription
- **GitHub**: Authenticated as Aitosoft org
- **API Token**: Fresh token in `.env.local` (generated 2026-01-19)

---

## v0.8.0 Upgrade Notes

### Security Fixes (Critical)
- 🔒 **RCE Fix**: Removed `__import__` from hook allowed builtins
- 🔒 **LFI Fix**: Added URL scheme validation, blocked file://, javascript:, data: URLs

### Breaking Changes (No Impact on Aitosoft)
- Hooks disabled by default (we don't use hooks)
- file:// URLs blocked in Docker API (we only use http/https)

### Dependency Changes
- Python requirement: 3.9 → 3.10 (we use 3.11 ✅)
- New: `patchright>=1.49.0` (stealth browser)
- **REMOVED from core**: `sentence-transformers` (now optional, saves ~500MB)

---

## Production Deployment

### Azure Resources
- **Resource Group**: `crawl4ai-v2-rg`
- **Key Vault**: `crawl4ai-v2-keyvault`
- **Container App**: `crawl4ai-v2-app`

### Authentication
- Bearer token via `C4AI_TOKEN` environment variable
- Token stored in Azure Key Vault, accessed via managed identity

### Next Deployment Steps
1. Deploy v0.8.0 to Azure production
2. Validate health check + auth
3. Test markdown extraction (raw + fit_markdown)
4. Update multi-agent platform with endpoint

---

## Quick Reference

### Start Local Server
```bash
uvicorn deploy.docker.server:app --host 0.0.0.0 --port 11235
```

### Test Endpoints
```bash
# Health check
curl http://localhost:11235/health

# Crawl request
curl -X POST http://localhost:11235/crawl \
  -H "Content-Type: application/json" \
  -d '{"urls": "https://example.com", "priority": 10}'
```

### Run Tests
```bash
pytest test-aitosoft/                    # Aitosoft-specific tests
pytest -xvs test-aitosoft/test_fit_markdown.py  # Single test
```

---

## Development History

| Date | Summary |
|------|---------|
| 2026-01-19 | Fresh dev container setup with Windows filesystem mount, v0.8.0 verified |
| 2026-01-19 | Upgraded to v0.8.0, security hardening, token rotation |
| 2025-07-24 | Resolved v0.7.1 dependencies, version management strategy |
| 2025-07-23 | Moved tests to `test-aitosoft/` folder |
| 2025-07-21 | Added CI/CD pipeline with GitHub Actions |
| 2025-07 | Initial Azure Container Apps deployment |

---

*Add new entries to the Development History table with date and brief summary.*
