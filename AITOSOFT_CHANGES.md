# Aitosoft Changes Log

This file tracks all modifications made to the crawl4ai fork for Aitosoft's internal use.
Keeping this log helps when syncing with upstream updates.

---

## Change Log

### 2026-01-19: Repository Cleanup and Test Fixes

**Purpose:** Clean up development notes and fix async test support

**Files Modified:**
- `DEVELOPMENT_NOTES.md` - Cleaned up, removed outdated sections, updated for current state
- `test-aitosoft/test_fit_markdown.py` - Added `@pytest.mark.asyncio` decorator for async test support

**Dependencies Added:**
- `pytest-asyncio` - Required for running async tests with pytest

**Verification:**
- ✅ `crawl4ai-doctor` passes (v0.8.0)
- ✅ All 3 test-aitosoft/ tests pass

---

### 2026-01-19: Initial Repository Setup

**Purpose:** Configure development environment for Aitosoft team

**Files Modified:**
- `.devcontainer/devcontainer.json` - Refactored to use setup.sh, added GitHub CLI feature, renamed container
- `.gitignore` - Added exception for `.devcontainer/setup.sh`

**Files Created:**
- `.devcontainer/setup.sh` - Extracted setup logic into maintainable script
- `CLAUDE.md` - Project guidance for Claude (git-ignored)
- `AITOSOFT_CHANGES.md` - This file (change tracking)
- `message-to-claude.md` - Detailed patterns from platform repo (handoff document)

**Files Updated (local only, git-ignored):**
- `.claude/settings.local.json` - Configured broader permissions for Claude Code
- `.env.local` - Fresh API token for local development

---

## Inherited from Previous Work (July 2025)

These files were created in the original Aitosoft fork and are still useful:

| File/Directory | Purpose | Status |
|----------------|---------|--------|
| `test-aitosoft/` | Aitosoft-specific tests (separate from upstream) | ✅ Working |
| `azure-deployment/` | Azure Container Apps deployment guides | Needs review |
| `run_validation_tests.py` | Test orchestration script | May need update |
| `.github/workflows/` | CI/CD pipelines | May need update |

---

## Upstream Sync Notes

When merging upstream updates:
1. Check if `.devcontainer/devcontainer.json` has upstream changes
2. Our `setup.sh` approach may need reconciliation with upstream's inline commands
3. Review any changes to `deploy/docker/` which we depend on
4. Test that `test-aitosoft/` tests still pass after merge

---

## Current State

- **Version**: v0.8.0 (synced with upstream)
- **Dev Environment**: Windows filesystem mount, working correctly
- **Tests**: 3/3 passing
- **Production**: Pending deployment

---

## Planned Changes

- [ ] Deploy v0.8.0 to Azure production
- [ ] Verify production health check + auth
- [ ] Connect to multi-agent platform
