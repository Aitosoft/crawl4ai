# Aitosoft Files Reference

Quick reference for what's ours vs upstream. **Read this before making changes.**

---

## 100% Aitosoft Code (Safe to Modify)

### Documentation
- `CLAUDE.md` - Claude Code guidance (entry point for new sessions)
- `AITOSOFT_CHANGES.md` - Change tracking and current state
- `DEPLOYMENT_INFO.md` - Production deployment info (endpoint, token, examples)
- `AITOSOFT_FILES.md` - This file

### Deployment
- `azure-deployment/deploy-aitosoft-prod.sh` - Production deployment script
- `azure-deployment/SIMPLE_AUTH_DEPLOY.md` - Auth implementation guide
- `azure-deployment/production-config.yml` - Production config
- `azure-deployment/deploy.sh` - Legacy North Europe script (deprecated)
- `azure-deployment/DEPLOYMENT_GUIDE.md` - Legacy guide (deprecated)
- `azure-deployment/TOKEN_ROTATION_GUIDE.md` - Legacy guide (deprecated)
- `azure-deployment/V0.8.0_UPGRADE_SUMMARY.md` - Legacy notes
- `azure-deployment/keyvault-deploy.sh` - KeyVault deployment (not used)
- `azure-deployment/*.py` - Test and helper scripts

### Testing
- `test-aitosoft/` - All files (our test suite)

### Development Environment
- `.devcontainer/` - All files (our dev container setup)

---

## Modified Upstream Files (Minimal Changes)

**IMPORTANT**: Only 42 lines total changed from upstream!

### deploy/docker/server.py
**Lines modified**: 3 lines added (lines 227-229)
```python
# Add simple token auth if CRAWL4AI_API_TOKEN is set
from simple_token_auth import SimpleTokenAuthMiddleware
app_.add_middleware(SimpleTokenAuthMiddleware)
```
**Why**: Enable our custom auth middleware
**Upstream sync**: Check for conflicts in `_setup_security()` function

### deploy/docker/config.yml
**Lines modified**: 2 lines (lines 45-46)
```yaml
security:
  enabled: true  # Changed from: false
  jwt_enabled: false  # We use simple token auth, not JWT
```
**Why**: Enable security in production
**Upstream sync**: Check `security:` section for new options

### deploy/docker/simple_token_auth.py
**Status**: NEW FILE (39 lines)
**Why**: Our custom authentication middleware
**Upstream sync**: No conflicts (new file)

---

## 100% Upstream (Never Modify)

### Core Library
- `crawl4ai/` - All files

### Docker Server (except files listed above)
- `deploy/docker/api.py`
- `deploy/docker/crawler_pool.py`
- `deploy/docker/auth.py` - JWT auth (we don't use)
- `deploy/docker/utils.py`
- `deploy/docker/schemas.py`
- `deploy/docker/monitor.py`
- `deploy/docker/mcp_bridge.py`
- `deploy/docker/job.py`
- All other files in `deploy/docker/`

### Tests
- `tests/` - Upstream test suite

### Configuration
- `pyproject.toml`
- `setup.py`
- `Dockerfile`
- All other root-level config files

---

## When Syncing with Upstream

1. **Read AITOSOFT_CHANGES.md** - Know what we've modified
2. **Check these files for conflicts:**
   - `deploy/docker/server.py` (3 lines near line 227)
   - `deploy/docker/config.yml` (security section)
3. **Our new file won't conflict:**
   - `deploy/docker/simple_token_auth.py` (new file)
4. **Merge strategy:**
   ```bash
   git fetch upstream
   git merge upstream/main
   # If conflicts in server.py or config.yml, keep our changes
   # Then rebuild and test
   ```

---

## Summary

**Total modifications**: 42 lines across 3 files
- `server.py`: 3 lines added
- `config.yml`: 2 lines changed
- `simple_token_auth.py`: 39 lines (new file)

**Why so minimal?**
- Easy to maintain when upstream updates
- Clear separation of concerns
- Minimal merge conflicts

**All other work** is in `azure-deployment/`, `test-aitosoft/`, and `.devcontainer/` directories which don't exist in upstream.
