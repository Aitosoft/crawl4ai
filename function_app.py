import azure.functions as func
import logging
import json
import os
import sys
import asyncio

# Add crawl4ai to sys.path if needed (assumes crawl4ai is one directory up)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'crawl4ai')))

from crawl4ai.async_webcrawler import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="http_trigger", methods=["POST"])
async def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Crawl4AI HTTP trigger function received a request.')

    try:
        req_body = req.get_json()
    except Exception:
        return func.HttpResponse(
            json.dumps({"success": False, "error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json"
        )

    url = req_body.get("url")
    if not url:
        return func.HttpResponse(
            json.dumps({"success": False, "error": "Missing 'url' in request body"}),
            status_code=400,
            mimetype="application/json"
        )

    # Minimal configs for crawl4ai
    browser_cfg = BrowserConfig(headless=True, verbose=False)
    crawler_cfg = CrawlerRunConfig(verbose=False)

    try:
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            result = await crawler.arun(url=url, config=crawler_cfg)
            markdown = getattr(result, "markdown", None)
            return func.HttpResponse(
                json.dumps({"success": True, "markdown": markdown}),
                mimetype="application/json"
            )
    except Exception as e:
        logging.exception("Crawl4AI error")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )