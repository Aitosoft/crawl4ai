Internal Overview

Scope
- Summarizes Aitosoft-specific components, owners, and how they relate to upstream Crawl4AI.
- Use alongside DEVELOPMENT_NOTES.md and AGENTS.md.

Directories (ours)
- `azure-deployment/`: Azure Container Apps deployment scripts, Key Vault integration, simple auth (`simple_auth.py`), and helper tests.
- `test-aitosoft/`: Internal tests for API behavior, production auth checks, and fit_markdown validation.
- `.github/workflows/`: CI/CD workflows to monitor upstream releases and perform image bump + validation.

Key Files (ours)
- `azure-deployment/keyvault-deploy.sh`: Main deployment/update script. Contains `IMAGE` tag for upstream Docker image and helper flags (dry-run, rollback, list revisions).
- `azure-deployment/simple_auth.py`: FastAPI dependency for simple bearer token auth via `CRAWL4AI_API_TOKEN`.
- `azure-deployment/custom_server.py`: Local customization hook for server/runtime when needed.
- `run_validation_tests.py`: Orchestrates internal validation runs.
- `test-aitosoft/test_*`: Internal tests (API, auth, fit_markdown).

Upstream Code (do not modify unless necessary)
- `crawl4ai/`: Core library code from upstream.
- `deploy/docker/`: Upstream server implementation used by their image.

Production Environment (sanitized)
- Platform: Azure Container Apps (North Europe).
- Auth: Bearer token read from Azure Key Vault and exposed as env `CRAWL4AI_API_TOKEN` in the container.
- Health: `/health` unauthenticated. Core crawl endpoints require `Authorization: Bearer <token>`.
- Secrets: Stored in Key Vault; do not hardcode. See secret name references in `azure-deployment/` docs/scripts.

How We Work
- Prefer configuration and wrapper changes under `azure-deployment/`.
- Keep Aitosoft tests in `test-aitosoft/` to avoid mixing with upstream’s test suite.
- Document any new internal files or folders here when added.

Ownership
- Aitosoft: `azure-deployment/`, `test-aitosoft/`, `.github/workflows/*`, validation scripts, and all internal docs.
- Upstream: Everything under `crawl4ai/` and most of `deploy/docker/`.
