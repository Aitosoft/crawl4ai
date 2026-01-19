#!/usr/bin/env bash
set -euo pipefail

echo "[devcontainer] Setup starting..."

# Install browser dependencies for Playwright/Chromium
echo "[devcontainer] Installing browser dependencies..."
sudo apt-get update
sudo apt-get install -y \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgbm1 \
    libgtk-3-0 \
    libxss1 \
    libasound2 \
    libdrm2 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libcups2 \
    fonts-liberation \
    libappindicator3-1 \
    xdg-utils

# Upgrade pip
echo "[devcontainer] Upgrading pip..."
pip install --upgrade pip

# Install uvicorn with standard extras
echo "[devcontainer] Installing uvicorn..."
pip install "uvicorn[standard]"

# Install Docker API requirements
echo "[devcontainer] Installing Docker API requirements..."
pip install -r deploy/docker/requirements.txt

# Install crawl4ai in editable mode
echo "[devcontainer] Installing crawl4ai..."
pip install -e ".[dev]" || pip install -e .

# Install dev tools
echo "[devcontainer] Installing dev tools..."
pip install ruff black mypy pytest pytest-asyncio pre-commit

# Setup pre-commit hooks
echo "[devcontainer] Setting up pre-commit hooks..."
pre-commit install || echo "pre-commit install skipped (may already be configured)"

# Run crawl4ai setup
echo "[devcontainer] Running crawl4ai setup..."
crawl4ai-setup || echo "crawl4ai-setup skipped (may already be configured)"
crawl4ai-doctor || echo "crawl4ai-doctor check completed"

# Install Claude Code CLI (use npm, not pnpm - updater compatibility)
if ! command -v claude >/dev/null 2>&1; then
    echo "[devcontainer] Installing Claude Code CLI..."
    npm install -g @anthropic-ai/claude-code
else
    echo "[devcontainer] Claude Code CLI already installed"
fi

# Print versions for verification
echo ""
echo "[devcontainer] ====== Installed Versions ======"
echo "Python: $(python --version)"
echo "Node: $(node --version)"
echo "npm: $(npm --version)"
claude --version 2>/dev/null || echo "Claude Code: run 'claude auth' to authenticate"
az --version 2>/dev/null | head -1 || echo "Azure CLI: not available"
gh --version 2>/dev/null || echo "GitHub CLI: not available"
echo ""

echo "[devcontainer] Setup complete!"
echo ""
echo "[devcontainer] Next steps:"
echo "  1. Run 'claude auth' to authenticate Claude Code"
echo "  2. Run 'az login' to authenticate with Azure"
echo "  3. Run 'gh auth login' to authenticate with GitHub"
echo "  4. Create .env.local with your API tokens"
