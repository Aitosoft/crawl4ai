#!/usr/bin/env bash
# -------------------------------------------------------------------
# Azure Functions (Linux Consumption) post‑build hook
# Installs Playwright Chromium into the function content folder
# and guarantees the browser binary is executable.
# -------------------------------------------------------------------
set -eux   # e = stop on first error, u = undefined var is error, x = echo commands

echo "[postbuild.sh] ⏳  Starting Playwright post‑build step"

# Tell Playwright where to drop the browsers.
export PLAYWRIGHT_BROWSERS_PATH=/home/site/wwwroot

# Install **only** Chromium for Playwright 1.51.0 (rev 1161).
python -m playwright install chromium

echo "[postbuild.sh] ✅  Chromium downloaded"

# Make sure the chrome binary has its executable bit (+x).
chromepath=$(find "$PLAYWRIGHT_BROWSERS_PATH" -type f \( -name chrome -o -name chromium \) | head -n 1)
chmod +x "$chromepath"

echo "[postbuild.sh] ✅  Executable bit ensured on $chromepath"
echo "[postbuild.sh] 🎉  Post‑build script completed successfully"
