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
        # Optionally support 'formats' for future extension
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
