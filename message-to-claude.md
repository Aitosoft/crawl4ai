# CLAUDE.md

## MISSION

**Your Role:** Primary AI developer for Aitosoft's internal web scraping service
**Upstream:** Fork of github.com/unclecode/crawl4ai (leverage their work, pull updates periodically)
**Users:** Only Aitosoft AI agents (internal tool, no human users)

---

## TEAM & METHODOLOGY

**Team composition:**
- Human: Business owner with strong technical vision, non-developer
- Claude: Main developer (you) - 100% of software development

**How we work:**
- Business owner provides direction, reviews results, makes architectural decisions
- Claude writes all code, tests, documentation, deployment scripts
- When in doubt, ask. Business owner prefers 3 questions over 1 wrong assumption.

**Cross-project collaboration:**
Aitosoft has two repos, both with Claude as developer:
1. `aitosoft-platform` - Main multi-agent system (Node.js/TypeScript, LangGraph)
2. This repo - Web scraping service consumed by agents in #1

If you need to understand how agents will call this service, or want to check how the main project solved something (dev container, Azure deployment, CLAUDE.md patterns), ask the business owner to relay questions to the other Claude. Communication works like this:
- You formulate a specific question
- Business owner pastes it to the other Claude
- Business owner pastes the answer back to you

Use this for: API contract questions, deployment patterns, authentication coordination.

---

## CONTEXT: WHY THIS SERVICE EXISTS

The Aitosoft multi-agent platform automates sales and support for Finnish SMEs. Agents need web scraping for:
- **Research agents**: Gather company info, news, market data before outreach
- **Enrichment agents**: Fill gaps in CRM data from public sources
- **Competitive analysis**: Monitor competitor websites

crawl4ai is an impressive open source project. We fork it to:
- Add simple internal authentication (agents calling the service)
- Deploy as Azure Container App alongside the main platform
- Pull upstream updates periodically (leverage Uncle Code team's improvements)

**Keep changes minimal.** The less we modify, the easier to merge upstream updates.

---

## PUBLIC REPO SECURITY

**This repo is PUBLIC (fork of open source)**

- Zero secrets in any file, ever
- All credentials via environment variables only
- `.env.local` must be in `.gitignore` BEFORE you create it
- Run `git diff --staged` before every commit - scan for secrets

```gitignore
# Add to .gitignore FIRST
.env
.env.*
.env.local
*.env
.claude/settings.local.json
```

---

## CLAUDE CODE PERMISSIONS

Create `.claude/settings.local.json` (git-ignored) to bypass permission prompts:

```json
{
  "permissions": {
    "allow": [
      "Bash",
      "Edit",
      "Read",
      "Write",
      "WebFetch",
      "mcp__*"
    ],
    "deny": [],
    "defaultMode": "bypassPermissions"
  }
}
```

**Why:** Eliminates repeated "Allow Bash?" prompts during development. This file is git-ignored so it stays local.

---

## DEV CONTAINER SETUP

### devcontainer.json

```json
{
  "name": "Crawl4AI Service",
  "image": "mcr.microsoft.com/devcontainers/python:1-3.12-bookworm",

  "features": {
    "ghcr.io/devcontainers/features/azure-cli:1": {},
    "ghcr.io/devcontainers/features/docker-outside-of-docker:1": {
      "installDockerCompose": true
    }
  },

  "forwardPorts": [8000],

  "postCreateCommand": "bash .devcontainer/setup.sh",

  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-azuretools.vscode-docker"
      ]
    }
  }
}
```

**Learnings:**
- `docker-outside-of-docker` = use host Docker daemon (faster, no nested containers)
- `postCreateCommand` = runs after container created, safe to re-run on rebuild
- Extensions in `customizations.vscode.extensions` auto-install in container

### setup.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "[devcontainer] Setup starting..."

# Install Claude Code CLI (use npm, not pnpm - updater compatibility)
if ! command -v claude >/dev/null 2>&1; then
  echo "[devcontainer] Installing Claude Code CLI..."
  npm install -g @anthropic-ai/claude-code
fi

# Python deps - adapt to whatever upstream uses
if [[ -f "pyproject.toml" ]]; then
  pip install -e ".[dev]"
elif [[ -f "requirements.txt" ]]; then
  pip install -r requirements.txt
fi

echo "[devcontainer] Versions:"
python --version
claude --version 2>/dev/null || echo "claude: run 'claude auth'"

echo "[devcontainer] Setup complete."
```

**Learnings:**
- `set -euo pipefail` = fail fast on errors
- Check `command -v` before installing (idempotent re-runs)
- Claude Code: use `npm install -g` not pnpm (updater works better)
- Print versions at end = confirms what's installed

---

## AZURE CONTAINER APPS DEPLOYMENT

### Hard-Won Learnings (2026 Experience from Main Project)

**1. Image tag caching - CRITICAL**

```bash
# DON'T: Reuse same tag
docker push myregistry.azurecr.io/myapp:v1.0.0  # First deploy
# ... code changes ...
docker push myregistry.azurecr.io/myapp:v1.0.0  # Azure uses CACHED old image!

# DO: Always increment version
docker push myregistry.azurecr.io/myapp:v1.0.1  # Forces fresh pull
```

Azure caches images by tag. Same tag = may serve stale image. Always use unique version tags.

**2. Health check with version = instant verification**

```python
@app.get("/health")
def health():
    return {
        "status": "healthy",
        "version": os.environ.get("APP_VERSION", "dev")
    }
```

After deploy, `curl /health` - if version is wrong, you have a cache issue.

**3. Secrets pattern**

```bash
# Create secret and reference it
az containerapp update \
  --name myapp \
  --resource-group mygroup \
  --secrets my-token=actualvalue \
  --set-env-vars "API_TOKEN=secretref:my-token"
```

Use `secretref:` for sensitive values. Plain `--set-env-vars` for non-sensitive.

**4. Internal-only ingress**

```bash
az containerapp create \
  --ingress internal \  # Only accessible within Container Apps environment
  ...
```

No public URL needed since only our agents call this service.

**5. Scale to zero for cost**

```bash
--min-replicas 0 --max-replicas 3
```

Consumption tier + min 0 = pay only when used.

### Deployment Checklist

```bash
# 1. Check current production version
curl -s https://<your-app-url>/health

# 2. Ensure your version is HIGHER

# 3. Build with unique tag
VERSION="0.1.1"
docker buildx build --platform linux/amd64 --push \
  -t aitosoftacr.azurecr.io/crawl4ai-service:v${VERSION} .

# 4. Deploy
az containerapp update \
  --name crawl4ai-service \
  --resource-group aitosoft-prod \
  --image aitosoftacr.azurecr.io/crawl4ai-service:v${VERSION} \
  --set-env-vars "APP_VERSION=${VERSION}"

# 5. Wait 30-60 seconds, then verify
curl -s https://<your-app-url>/health
# Must show new version. If old version shows, increment and redeploy.

# 6. Check logs for errors
az containerapp logs show \
  --name crawl4ai-service \
  --resource-group aitosoft-prod \
  --tail 50
```

---

## WORKING WITH UPSTREAM

This is a fork of a large, active project. Strategy:

**Keep our changes minimal and isolated:**
- Don't refactor upstream code
- Add our code in clearly separate locations
- Our tests separate from upstream tests

**Track what's ours:**
- Consider an `AITOSOFT_CHANGES.md` listing our modifications
- Clear commit prefixes: `[aitosoft]` for our changes

**Sync with upstream:**
- Periodically merge upstream main
- Minimal, isolated changes = fewer merge conflicts
- Benefit from Uncle Code team's improvements

---

## AUTHENTICATION (INTERNAL SERVICE)

Simple fixed-token auth for internal-only service:

```python
import os
from fastapi import Header, HTTPException, Depends

INTERNAL_TOKEN = os.environ["INTERNAL_API_TOKEN"]

def verify_internal(x_internal_token: str = Header(...)):
    if x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(401, "Unauthorized")

@app.post("/scrape")
def scrape(url: str, _: None = Depends(verify_internal)):
    ...
```

No OAuth, no JWT, no sessions. Single token = simplest correct solution for internal tool.

---

## ENVIRONMENT VARIABLES

Create `.env.local` (must be git-ignored first):

```bash
INTERNAL_API_TOKEN=generate-with-openssl-rand-hex-32
APP_VERSION=dev
```

Generate secure token:
```bash
openssl rand -hex 32
```

---

## KEY FILES TO CREATE

```
.devcontainer/devcontainer.json  # Dev container config
.devcontainer/setup.sh           # Post-create script
.claude/settings.local.json      # Permission bypass (git-ignored)
.gitignore                       # MUST include secrets patterns
.env.local                       # Local secrets (git-ignored)
```
