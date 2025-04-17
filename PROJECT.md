# PROJECT.md – crawl4ai Azure Function Deployment Guide

This document is a complete, up-to-date, step-by-step guide for deploying the crawl4ai web scraper as a serverless, HTTP-triggered Azure Function. It covers all required Azure, Playwright, and Python configuration details, so you can reproduce a working deployment from scratch.

---

## Overview

- **Goal:** Deploy crawl4ai as an Azure Function that accepts a POST request with a URL and returns extracted Markdown (and optionally links) as JSON.
- **Stack:** Python 3.11, Playwright (Chromium), Azure Functions (Linux Consumption Plan)
- **Authentication:** Custom API key via x-api-key header
- **Async:** All scraping is async for performance

---

## Folder Structure

```
<project-root>/
├── crawl4ai/            # The crawl4ai library (copied here)
├── HttpTrigger1/        # Main Azure Function (entry: __init__.py, function.json)
├── requirements.txt     # All dependencies, including playwright
├── host.json            # Azure Functions host config
├── postbuild.sh         # Installs Playwright Chromium after deploy
├── local.settings.json  # Local dev settings (not used in Azure)
└── PROJECT.md           # This file
```

---

## 1. Prerequisites

- Azure subscription
- Python 3.11 (locally, for packaging)
- VS Code with Azure Functions extension (recommended)
- The crawl4ai codebase (copy the crawl4ai/ folder into your function app root)

---

## 2. Azure Function App Setup

1. **Create a new Azure Function App** (Python 3.11, Linux, Consumption Plan) in the Azure Portal or with VS Code.
2. **Copy crawl4ai code** into your function app folder (so crawl4ai/ is at the root, not nested).
3. **Create the HTTP trigger:**
   - Folder: `HttpTrigger1/`
   - Files:
     - `__init__.py` (async, uses crawl4ai to scrape and return markdown)
     - `function.json` (defines HTTP POST trigger, anonymous auth)

---

## 3. requirements.txt

Include all dependencies, especially:
- `azure-functions`
- `playwright`
- `aiohttp`
- All crawl4ai dependencies

Example (snippet):
```
azure-functions
playwright
aiohttp
# ...other dependencies...
```

---

## 4. Playwright/Chromium Setup for Azure

Azure Functions does NOT include browser binaries by default. You must:

1. **Add postbuild.sh to your project root:**
   ```bash
   #!/usr/bin/env bash
   echo "[postbuild.sh] Starting post-build script."
   which python
   python -m playwright install chromium
   if [ $? -eq 0 ]; then
     echo "[postbuild.sh] Playwright Chromium installed successfully."
   else
     echo "[postbuild.sh] Playwright Chromium install failed!"
     exit 1
   fi
   echo "[postbuild.sh] Finished post-build script."
   ```
2. **In Azure Portal → Function App → Configuration → Application settings, add:**
   - `PLAYWRIGHT_BROWSERS_PATH` = `/home/site/wwwroot`
   - `SCM_DO_BUILD_DURING_DEPLOYMENT` = `1`
   - `SCM_POST_BUILD_SCRIPT_PATH` = `postbuild.sh`
   - Remove any `POST_BUILD_COMMAND` setting (not used by Oryx)

This ensures Chromium is installed and available to Playwright at runtime.

---

## 5. API Key Authentication

- Add an `API_KEY` setting in Azure App Settings (Configuration).
- The function checks for `x-api-key` header in each request and returns 401 if missing/incorrect.
- Set `authLevel` to `anonymous` in function.json (auth is handled in code).

---

## 6. Deploying

1. **Deploy using VS Code** (right-click function app → Deploy to Function App) or use Azure CLI/zip deploy.
2. **Check deployment logs** for `[postbuild.sh]` output and Playwright install logs.
3. **After deployment, test** by POSTing to your function endpoint:
   - URL: `https://<your-func-app>.azurewebsites.net/api/HttpTrigger1`
   - Headers: `Content-Type: application/json`, `x-api-key: <your-api-key>`
   - Body: `{ "url": "https://example.com" }`

---

## 7. Example: HttpTrigger1/__init__.py

```python
import os
import json
import logging
import azure.functions as func
from crawl4ai.async_webcrawler import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

API_KEY = os.getenv("API_KEY")

async def main(req: func.HttpRequest) -> func.HttpResponse:
    if req.method != "POST":
        return func.HttpResponse("Method Not Allowed", status_code=405)
    if not API_KEY or req.headers.get("x-api-key") != API_KEY:
        return func.HttpResponse("Unauthorized", status_code=401)
    try:
        body = req.get_json()
        url = body.get("url")
        if not url or not url.startswith("http"):
            raise ValueError("Invalid URL")
        browser_cfg = BrowserConfig(headless=True, verbose=False)
        crawler_cfg = CrawlerRunConfig(verbose=False)
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            result = await crawler.arun(url=url, config=crawler_cfg)
        return func.HttpResponse(
            json.dumps({
                "success": getattr(result, "success", True),
                "markdown": getattr(result, "markdown", None),
                "links": getattr(result, "links", None)
            }),
            mimetype="application/json"
        )
    except Exception as e:
        logging.exception("Crawl4AI error")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            mimetype="application/json",
            status_code=400
        )
```

---

## 8. Troubleshooting

- **Chromium not found error:**
  - Ensure postbuild.sh exists at the project root and is referenced by SCM_POST_BUILD_SCRIPT_PATH.
  - Confirm PLAYWRIGHT_BROWSERS_PATH is set to /home/site/wwwroot.
  - Check deployment logs for Playwright install output.
- **Function not visible in Azure:**
  - Ensure you are using the v1 folder structure (HttpTrigger1/ with __init__.py and function.json).
  - Remove function_app.py if using v1 model.
- **500 errors:**
  - Check logs in Azure Portal for Python exceptions.
  - Confirm API_KEY is set and matches your request header.

---

## 9. Summary Checklist

- [x] crawl4ai/ code present in function app root
- [x] HttpTrigger1/ with __init__.py and function.json
- [x] requirements.txt includes playwright, azure-functions, aiohttp, etc.
- [x] postbuild.sh in project root
- [x] Azure App Settings: PLAYWRIGHT_BROWSERS_PATH, SCM_DO_BUILD_DURING_DEPLOYMENT, SCM_POST_BUILD_SCRIPT_PATH, API_KEY
- [x] Deploy via VS Code or CLI
- [x] Test with real URL and API key

---

## 10. References
- [Playwright on Azure Functions (GitHub issues, docs)](https://github.com/microsoft/playwright-python/issues/1336)
- [Azure Functions Python developer guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python)
- [Oryx post-build scripts](https://github.com/microsoft/Oryx/blob/main/doc/post-build-script.md)

---

This guide is all you need to deploy crawl4ai as a robust, async, browser-based web scraping Azure Function. If you follow every step, you will have a working, production-ready deployment on the first try.
