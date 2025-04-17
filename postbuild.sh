cat > postbuild.sh <<'EOF'
#!/usr/bin/env bash
set -euxo pipefail

echo "[postbuild] installing Playwright Chromium"
export PLAYWRIGHT_BROWSERS_PATH="./.playwright"        # will be /home/site/wwwroot/.playwright
python -m playwright install chromium

# make sure the binary is executable just in case
chromepath=$(find "$PLAYWRIGHT_BROWSERS_PATH" -type f -name chrome | head -n1)
chmod +x "$chromepath"
echo "[postbuild] done – chromium at $chromepath"
EOF

git add postbuild.sh
git commit -m "Use relative .playwright install path"
