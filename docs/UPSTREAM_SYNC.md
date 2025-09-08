Upstream Sync Guide

Goal
- Safely adopt new upstream Crawl4AI Docker images without rebuilding custom images or refactoring core code.

What We Track
- Production uses upstream Docker image `unclecode/crawl4ai:<tag>` (currently `latest`, mapping to ~v0.6.0 per upstream).
- Local repo may include newer code/tests for evaluation only.

Update Flow (image bump)
1) Check upstream image availability
   - See GitHub Action: `.github/workflows/monitor-crawl4ai-releases.yml` (auto-issue when new release is detected).
   - Confirm the image tag exists on Docker Hub if updating to a specific version.

2) Change deployment image tag
   - Edit `azure-deployment/keyvault-deploy.sh` and set `IMAGE="unclecode/crawl4ai:<new_tag>"`.

3) Validate locally
   - Run internal tests: `python -m pytest -q test-aitosoft/` or run `python test-aitosoft/test_fit_markdown.py`.

4) Deploy
   - Use the workflow: Actions → “Update Crawl4AI and Test” → enter the new version and run.
   - Or run locally: `./azure-deployment/keyvault-deploy.sh --update-only` (requires Azure CLI auth).

5) Verify
   - Health check: `GET /health` (no auth).
   - Crawl test with Authorization header: `POST /crawl` with `Authorization: Bearer <token>`.

Rollback
- Use `keyvault-deploy.sh --rollback [REVISION]` to revert to a previous active revision.
- The GitHub Action also performs rollback if production validation fails.

When Code Diffs Matter
- If upstream releases contain breaking API changes that affect our tests:
  - Update Aitosoft tests in `test-aitosoft/` accordingly.
  - Prefer adapting configuration or deployment scripts; avoid patching upstream core under `crawl4ai/` unless necessary.

Optional: Tracking upstream repo
- You can add an upstream remote to inspect changes:
  - `git remote add upstream https://github.com/unclecode/crawl4ai.git`
  - `git fetch upstream`
  - Diff: `git log --oneline --decorate --graph upstream/main..main`
  - Name-only diff: `git diff --name-status upstream/main...main`

Notes
- Do not commit secrets. Use placeholders in docs and Key Vault for runtime values.
