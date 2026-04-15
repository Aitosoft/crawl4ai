import json
import asyncio
from typing import List, Tuple, Dict
from functools import partial
from uuid import uuid4
from datetime import datetime, timezone
from base64 import b64encode

import logging
from typing import Optional, AsyncGenerator
from urllib.parse import unquote
import httpx
from fastapi import HTTPException, Request, status
from fastapi.background import BackgroundTasks
from fastapi.responses import JSONResponse
from redis import asyncio as aioredis

from crawl4ai import (
    AsyncWebCrawler,
    CrawlerRunConfig,
    LLMExtractionStrategy,
    CacheMode,
    BrowserConfig,
    MemoryAdaptiveDispatcher,
    RateLimiter,
    LLMConfig,
)
from crawl4ai.utils import perform_completion_with_backoff
from crawl4ai.content_filter_strategy import (
    PruningContentFilter,
    BM25ContentFilter,
    LLMContentFilter,
)
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy

from utils import (
    TaskStatus,
    FilterType,
    get_base_url,
    is_task_id,
    should_cleanup_task,
    decode_redis_hash,
    get_llm_api_key,
    validate_llm_provider,
    get_llm_temperature,
    get_llm_base_url,
    get_redis_task_ttl,
)
from webhook import WebhookDeliveryService

import psutil, time

logger = logging.getLogger(__name__)

# Aitosoft: hard per-request timeout to bound arun+patchright.
# Azure Container Apps ingress times out at 240s by default; if the backend
# keeps running past that, FastAPI does NOT cancel the coroutine on client
# disconnect, and `release_crawler` in the finally block never fires — so
# `active_requests` leaks in crawler_pool and the pool saturates over time.
# 180s leaves ~60s under the ingress ceiling for request setup, logging,
# cleanup, and JSON serialization of the 504 response.
CRAWL_REQUEST_TIMEOUT_S = 180

# Aitosoft: static-mode per-URL HTTP timeout. Separate from CRAWL_REQUEST_TIMEOUT_S
# because static fetches should be fast or fail fast — the whole point of static
# mode is a cheap alternative to Playwright. See tasks/done/static-html-fallback-mode-*.md.
STATIC_FETCH_TIMEOUT_S = 15


# --- Helper to get memory ---
def _get_memory_mb():
    try:
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception as e:
        logger.warning(f"Could not get memory info: {e}")
        return None


# ───────────────────── Aitosoft static-mode helpers ─────────────────────
# Module-scope httpx.AsyncClient reused across requests. Lazy-init on first
# use; closed from server.py's FastAPI lifespan shutdown.
_static_http_client: Optional[httpx.AsyncClient] = None
_static_http_client_lock = asyncio.Lock()
_STATIC_USER_AGENT_FALLBACK = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)
_static_user_agent_cached: Optional[str] = None


def _get_static_user_agent() -> str:
    """Mirror the full-mode UA from config.yml so static fetches don't look
    like a different client to target sites. Falls back to a Chrome UA if
    config is unavailable for any reason. Cached per-process."""
    global _static_user_agent_cached
    if _static_user_agent_cached is not None:
        return _static_user_agent_cached
    try:
        from utils import load_config

        cfg = load_config()
        ua = (
            (cfg.get("crawler", {}) or {})
            .get("browser", {})
            .get("kwargs", {})
            .get("user_agent")
        )
        _static_user_agent_cached = ua or _STATIC_USER_AGENT_FALLBACK
    except Exception:
        _static_user_agent_cached = _STATIC_USER_AGENT_FALLBACK
    return _static_user_agent_cached


async def _get_static_http_client() -> httpx.AsyncClient:
    """Return the module-scope httpx.AsyncClient, creating it on first use."""
    global _static_http_client
    if _static_http_client is None:
        async with _static_http_client_lock:
            if _static_http_client is None:
                _static_http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(STATIC_FETCH_TIMEOUT_S),
                    verify=False,  # match --ignore-certificate-errors in config.yml
                    follow_redirects=True,
                    headers={
                        "User-Agent": _get_static_user_agent(),
                        "Accept": (
                            "text/html,application/xhtml+xml,"
                            "application/xml;q=0.9,*/*;q=0.8"
                        ),
                        "Accept-Language": "fi,en;q=0.7",
                    },
                )
    return _static_http_client


async def close_static_http_client() -> None:
    """Close the module-scope httpx client. Called from server.py lifespan."""
    global _static_http_client
    if _static_http_client is not None:
        client = _static_http_client
        _static_http_client = None
        try:
            await client.aclose()
        except Exception as e:
            logger.warning(f"[static] client close raised (non-fatal): {e}")


def _static_error_result(
    url: str,
    *,
    status_code: int = 0,
    error_message: Optional[str] = None,
) -> dict:
    return {
        "url": url,
        "success": False,
        "status_code": status_code,
        "error_message": error_message,
        "render_mode": "static",
        "markdown": {"raw_markdown": "", "fit_markdown": ""},
        "links": {"internal": [], "external": []},
    }


def _strip_hidden_decoys(html: str) -> str:
    """Remove CSS-hidden nodes before markdown conversion.

    Motivates: roadscanners.com (and other Odoo-powered sites) obfuscate
    emails by inlining a hidden ``<span class="oe_displaynone">null</span>``
    between the user and domain parts (e.g. ``name@<hidden>null</hidden>
    roadscanners.com``). Browsers hide the span via CSS; html2text, which
    has no CSS awareness, keeps the text, producing ``name@nullroadscanners.com``.

    We strip elements that are hidden via inline style or via the common
    display-none utility class conventions. We also drop <script>/<style>/
    <noscript> since html2text leaves their text out anyway but having BS4
    remove them keeps whitespace sane.
    """
    try:
        from bs4 import BeautifulSoup
    except Exception as e:  # pragma: no cover — BS4 is a crawl4ai dep
        logger.warning(f"[static] BeautifulSoup unavailable: {e}; skipping decoy strip")
        return html

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        # Fall back to the stdlib parser if lxml chokes on malformed input.
        soup = BeautifulSoup(html, "html.parser")

    for tag_name in ("script", "style", "noscript", "template"):
        for t in soup.find_all(tag_name):
            t.decompose()

    # Inline style="display:none" / "visibility:hidden".
    for t in soup.find_all(
        style=lambda v: bool(v)
        and (
            "display:none" in v.replace(" ", "").lower()
            or "visibility:hidden" in v.replace(" ", "").lower()
        )
    ):
        t.decompose()

    # Class-based display-none utilities commonly used to hide scraper decoys.
    # oe_displaynone is Odoo; d-none is Bootstrap 4+; is-hidden is the Bulma
    # equivalent. Deliberately NOT matching sr-only / visually-hidden — those
    # are accessibility utilities that legitimately hold screen-reader-only
    # content (skip links, form labels, "Contact us at ..." blocks) and
    # removing them can silently drop user-meaningful text. Note: BS4 calls
    # the class_ callable once per class name (as a string), not once per tag
    # with the class list.
    hidden_classes = {
        "oe_displaynone",
        "d-none",
        "is-hidden",
    }
    for t in soup.find_all(class_=lambda cs: cs in hidden_classes):
        t.decompose()

    return str(soup)


async def _fetch_static_one(url: str) -> dict:
    """Fetch a single URL with httpx and convert the body to markdown. Never
    raises — all failure modes are encoded into the returned dict so the
    caller can gather() without `return_exceptions=True`."""
    from crawl4ai.html2text import HTML2Text

    client = await _get_static_http_client()
    t0 = time.time()
    try:
        resp = await client.get(url)
    except httpx.TimeoutException:
        logger.info(f"[static] timeout after {STATIC_FETCH_TIMEOUT_S}s: {url}")
        return _static_error_result(
            url,
            error_message=f"static-fetch: timeout after {STATIC_FETCH_TIMEOUT_S}s",
        )
    except httpx.RequestError as e:
        logger.info(f"[static] request error: {url} {type(e).__name__}: {e}")
        return _static_error_result(
            url,
            error_message=f"static-fetch: {type(e).__name__}: {e}",
        )
    except Exception as e:
        logger.error(f"[static] unexpected error: {url} {e}", exc_info=True)
        return _static_error_result(
            url,
            error_message=f"static-fetch: {type(e).__name__}: {e}",
        )

    elapsed_ms = int((time.time() - t0) * 1000)
    final_url = str(resp.url)
    status_code = resp.status_code
    success = 200 <= status_code < 400

    try:
        body = resp.text
    except Exception as e:
        logger.warning(f"[static] body decode failed for {url}: {e}")
        body = ""

    cleaned_body = _strip_hidden_decoys(body) if body else body

    try:
        h = HTML2Text(baseurl=final_url)
        h.body_width = 0  # no hard-wrap; preserve paragraphs for downstream LLMs
        h.ignore_images = True  # MAS doesn't use images in static mode
        markdown = h.handle(cleaned_body)
    except Exception as e:
        # html2text has parser edge cases; fall back to raw HTML rather than
        # failing the request — MAS can still strip tags on its end.
        logger.warning(
            f"[static] html2text failed for {url}: {e}; returning raw HTML as markdown"
        )
        markdown = cleaned_body or body

    logger.info(
        f"[static] {status_code} {final_url} "
        f"({len(body)}B html, {len(markdown)}B md, {elapsed_ms}ms)"
    )

    return {
        "url": final_url,
        "success": success,
        "status_code": status_code,
        "error_message": None if success else f"HTTP {status_code}",
        "render_mode": "static",
        "markdown": {"raw_markdown": markdown, "fit_markdown": ""},
        "links": {"internal": [], "external": []},
    }


async def handle_static_crawl_request(
    urls: List[str],
    config: dict,
) -> dict:
    """Static-mode handler: httpx + html2text, no Playwright.

    Returns the same top-level envelope shape as ``handle_crawl_request`` so
    MAS's client code can treat full and static responses uniformly. Each
    inner result carries ``render_mode: "static"`` and its own ``success``
    flag. Network failures do NOT raise — they produce success=False
    results, keeping the HTTP status at 200.
    """
    start_mem_mb = _get_memory_mb()
    start_time = time.time()

    results = await asyncio.gather(*(_fetch_static_one(u) for u in urls))

    end_time = time.time()
    end_mem_mb = _get_memory_mb()

    mem_delta_mb = None
    if start_mem_mb is not None and end_mem_mb is not None:
        mem_delta_mb = end_mem_mb - start_mem_mb

    logger.info(
        f"[static] batch done: {len(urls)} url(s) in "
        f"{end_time - start_time:.2f}s, mem Δ {mem_delta_mb}MB"
    )

    return {
        "success": True,
        "results": list(results),
        "server_processing_time_s": end_time - start_time,
        "server_memory_delta_mb": mem_delta_mb,
        "server_peak_memory_mb": end_mem_mb,
    }


async def hset_with_ttl(redis, key: str, mapping: dict, config: dict):
    """Set Redis hash with automatic TTL expiry.

    Args:
        redis: Redis client instance
        key: Redis key (e.g., "task:abc123")
        mapping: Hash field-value mapping
        config: Application config containing redis.task_ttl_seconds
    """
    await redis.hset(key, mapping=mapping)
    ttl = get_redis_task_ttl(config)
    if ttl > 0:
        await redis.expire(key, ttl)


async def handle_llm_qa(
    url: str,
    query: str,
    config: dict,
    provider: Optional[str] = None,
    temperature: Optional[float] = None,
    base_url: Optional[str] = None,
) -> str:
    """Process QA using LLM with crawled content as context."""
    from crawler_pool import get_crawler, release_crawler

    crawler = None
    try:
        if not url.startswith(("http://", "https://")) and not url.startswith(
            ("raw:", "raw://")
        ):
            url = "https://" + url
        # Extract base URL by finding last '?q=' occurrence
        last_q_index = url.rfind("?q=")
        if last_q_index != -1:
            url = url[:last_q_index]

        # Get markdown content (use default config)
        from utils import load_config

        cfg = load_config()
        browser_cfg = BrowserConfig(
            extra_args=cfg["crawler"]["browser"].get("extra_args", []),
            **cfg["crawler"]["browser"].get("kwargs", {}),
        )
        crawler = await get_crawler(browser_cfg)
        result = await crawler.arun(url)
        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.error_message,
            )
        content = result.markdown.fit_markdown or result.markdown.raw_markdown

        # Create prompt and get LLM response
        prompt = f"""Use the following content as context to answer the question.
    Content:
    {content}

    Question: {query}

    Answer:"""

        resolved_provider = provider or config["llm"]["provider"]
        response = perform_completion_with_backoff(
            provider=resolved_provider,
            prompt_with_variables=prompt,
            api_token=get_llm_api_key(config, resolved_provider),
            temperature=temperature or get_llm_temperature(config, resolved_provider),
            base_url=base_url or get_llm_base_url(config, resolved_provider),
            base_delay=config["llm"].get("backoff_base_delay", 2),
            max_attempts=config["llm"].get("backoff_max_attempts", 3),
            exponential_factor=config["llm"].get("backoff_exponential_factor", 2),
        )

        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"QA processing error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
    finally:
        if crawler:
            await release_crawler(crawler)


async def process_llm_extraction(
    redis: aioredis.Redis,
    config: dict,
    task_id: str,
    url: str,
    instruction: str,
    schema: Optional[str] = None,
    cache: str = "0",
    provider: Optional[str] = None,
    webhook_config: Optional[Dict] = None,
    temperature: Optional[float] = None,
    base_url: Optional[str] = None,
) -> None:
    """Process LLM extraction in background."""
    # Initialize webhook service
    webhook_service = WebhookDeliveryService(config)

    try:
        # Validate provider
        is_valid, error_msg = validate_llm_provider(config, provider)
        if not is_valid:
            await hset_with_ttl(
                redis,
                f"task:{task_id}",
                {"status": TaskStatus.FAILED, "error": error_msg},
                config,
            )

            # Send webhook notification on failure
            await webhook_service.notify_job_completion(
                task_id=task_id,
                task_type="llm_extraction",
                status="failed",
                urls=[url],
                webhook_config=webhook_config,
                error=error_msg,
            )
            return
        api_key = get_llm_api_key(
            config, provider
        )  # Returns None to let litellm handle it
        llm_strategy = LLMExtractionStrategy(
            llm_config=LLMConfig(
                provider=provider or config["llm"]["provider"],
                api_token=api_key,
                temperature=temperature or get_llm_temperature(config, provider),
                base_url=base_url or get_llm_base_url(config, provider),
            ),
            instruction=instruction,
            schema=json.loads(schema) if schema else None,
        )

        cache_mode = CacheMode.ENABLED if cache == "1" else CacheMode.WRITE_ONLY

        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    extraction_strategy=llm_strategy,
                    scraping_strategy=LXMLWebScrapingStrategy(),
                    cache_mode=cache_mode,
                ),
            )

        if not result.success:
            await hset_with_ttl(
                redis,
                f"task:{task_id}",
                {"status": TaskStatus.FAILED, "error": result.error_message},
                config,
            )

            # Send webhook notification on failure
            await webhook_service.notify_job_completion(
                task_id=task_id,
                task_type="llm_extraction",
                status="failed",
                urls=[url],
                webhook_config=webhook_config,
                error=result.error_message,
            )
            return

        try:
            content = json.loads(result.extracted_content)
        except json.JSONDecodeError:
            content = result.extracted_content

        result_data = {"extracted_content": content}

        await hset_with_ttl(
            redis,
            f"task:{task_id}",
            {"status": TaskStatus.COMPLETED, "result": json.dumps(content)},
            config,
        )

        # Send webhook notification on successful completion
        await webhook_service.notify_job_completion(
            task_id=task_id,
            task_type="llm_extraction",
            status="completed",
            urls=[url],
            webhook_config=webhook_config,
            result=result_data,
        )

    except Exception as e:
        logger.error(f"LLM extraction error: {str(e)}", exc_info=True)
        await hset_with_ttl(
            redis,
            f"task:{task_id}",
            {"status": TaskStatus.FAILED, "error": str(e)},
            config,
        )

        # Send webhook notification on failure
        await webhook_service.notify_job_completion(
            task_id=task_id,
            task_type="llm_extraction",
            status="failed",
            urls=[url],
            webhook_config=webhook_config,
            error=str(e),
        )


async def handle_markdown_request(
    url: str,
    filter_type: FilterType,
    query: Optional[str] = None,
    cache: str = "0",
    config: Optional[dict] = None,
    provider: Optional[str] = None,
    temperature: Optional[float] = None,
    base_url: Optional[str] = None,
) -> str:
    """Handle markdown generation requests."""
    crawler = None
    try:
        # Validate provider if using LLM filter
        if filter_type == FilterType.LLM:
            is_valid, error_msg = validate_llm_provider(config, provider)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg
                )
        decoded_url = unquote(url)
        if not decoded_url.startswith(
            ("http://", "https://")
        ) and not decoded_url.startswith(("raw:", "raw://")):
            decoded_url = "https://" + decoded_url

        if filter_type == FilterType.RAW:
            md_generator = DefaultMarkdownGenerator()
        else:
            content_filter = {
                FilterType.FIT: PruningContentFilter(),
                FilterType.BM25: BM25ContentFilter(user_query=query or ""),
                FilterType.LLM: LLMContentFilter(
                    llm_config=LLMConfig(
                        provider=provider or config["llm"]["provider"],
                        api_token=get_llm_api_key(
                            config, provider
                        ),  # Returns None to let litellm handle it
                        temperature=temperature
                        or get_llm_temperature(config, provider),
                        base_url=base_url or get_llm_base_url(config, provider),
                    ),
                    instruction=query or "Extract main content",
                ),
            }[filter_type]
            md_generator = DefaultMarkdownGenerator(content_filter=content_filter)

        cache_mode = CacheMode.ENABLED if cache == "1" else CacheMode.WRITE_ONLY

        from crawler_pool import get_crawler, release_crawler
        from utils import load_config as _load_config

        _cfg = _load_config()
        browser_cfg = BrowserConfig(
            extra_args=_cfg["crawler"]["browser"].get("extra_args", []),
            **_cfg["crawler"]["browser"].get("kwargs", {}),
        )
        crawler = await get_crawler(browser_cfg)
        result = await crawler.arun(
            url=decoded_url,
            config=CrawlerRunConfig(
                markdown_generator=md_generator,
                scraping_strategy=LXMLWebScrapingStrategy(),
                cache_mode=cache_mode,
            ),
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.error_message,
            )

        return (
            result.markdown.raw_markdown
            if filter_type == FilterType.RAW
            else result.markdown.fit_markdown
        )

    except Exception as e:
        logger.error(f"Markdown error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
    finally:
        if crawler:
            await release_crawler(crawler)


async def handle_llm_request(
    redis: aioredis.Redis,
    background_tasks: BackgroundTasks,
    request: Request,
    input_path: str,
    query: Optional[str] = None,
    schema: Optional[str] = None,
    cache: str = "0",
    config: Optional[dict] = None,
    provider: Optional[str] = None,
    webhook_config: Optional[Dict] = None,
    temperature: Optional[float] = None,
    api_base_url: Optional[str] = None,
) -> JSONResponse:
    """Handle LLM extraction requests."""
    base_url = get_base_url(request)

    try:
        if is_task_id(input_path):
            return await handle_task_status(redis, input_path, base_url)

        if not query:
            return JSONResponse(
                {
                    "message": "Please provide an instruction",
                    "_links": {
                        "example": {
                            "href": f"{base_url}/llm/{input_path}?q=Extract+main+content",
                            "title": "Try this example",
                        }
                    },
                }
            )

        return await create_new_task(
            redis,
            background_tasks,
            input_path,
            query,
            schema,
            cache,
            base_url,
            config,
            provider,
            webhook_config,
            temperature,
            api_base_url,
        )

    except Exception as e:
        logger.error(f"LLM endpoint error: {str(e)}", exc_info=True)
        return JSONResponse(
            {"error": str(e), "_links": {"retry": {"href": str(request.url)}}},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


async def handle_task_status(
    redis: aioredis.Redis, task_id: str, base_url: str, *, keep: bool = False
) -> JSONResponse:
    """Handle task status check requests."""
    task = await redis.hgetall(f"task:{task_id}")
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )

    task = decode_redis_hash(task)
    response = create_task_response(task, task_id, base_url)

    if task["status"] in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
        if not keep and should_cleanup_task(task["created_at"]):
            await redis.delete(f"task:{task_id}")

    return JSONResponse(response)


async def create_new_task(
    redis: aioredis.Redis,
    background_tasks: BackgroundTasks,
    input_path: str,
    query: str,
    schema: Optional[str],
    cache: str,
    base_url: str,
    config: dict,
    provider: Optional[str] = None,
    webhook_config: Optional[Dict] = None,
    temperature: Optional[float] = None,
    api_base_url: Optional[str] = None,
) -> JSONResponse:
    """Create and initialize a new task."""
    decoded_url = unquote(input_path)
    if not decoded_url.startswith(
        ("http://", "https://")
    ) and not decoded_url.startswith(("raw:", "raw://")):
        decoded_url = "https://" + decoded_url

    from datetime import datetime

    task_id = f"llm_{int(datetime.now().timestamp())}_{id(background_tasks)}"

    task_data = {
        "status": TaskStatus.PROCESSING,
        "created_at": datetime.now().isoformat(),
        "url": decoded_url,
    }

    # Store webhook config if provided
    if webhook_config:
        task_data["webhook_config"] = json.dumps(webhook_config)

    await hset_with_ttl(redis, f"task:{task_id}", task_data, config)

    background_tasks.add_task(
        process_llm_extraction,
        redis,
        config,
        task_id,
        decoded_url,
        query,
        schema,
        cache,
        provider,
        webhook_config,
        temperature,
        api_base_url,
    )

    return JSONResponse(
        {
            "task_id": task_id,
            "status": TaskStatus.PROCESSING,
            "url": decoded_url,
            "_links": {
                "self": {"href": f"{base_url}/llm/{task_id}"},
                "status": {"href": f"{base_url}/llm/{task_id}"},
            },
        }
    )


def create_task_response(task: dict, task_id: str, base_url: str) -> dict:
    """Create response for task status check."""
    response = {
        "task_id": task_id,
        "status": task["status"],
        "created_at": task["created_at"],
        "url": task["url"],
        "_links": {
            "self": {"href": f"{base_url}/llm/{task_id}"},
            "refresh": {"href": f"{base_url}/llm/{task_id}"},
        },
    }

    if task["status"] == TaskStatus.COMPLETED:
        response["result"] = json.loads(task["result"])
    elif task["status"] == TaskStatus.FAILED:
        response["error"] = task["error"]

    return response


async def stream_results(
    crawler: AsyncWebCrawler, results_gen: AsyncGenerator
) -> AsyncGenerator[bytes, None]:
    """Stream results with heartbeats and completion markers."""
    import json
    from utils import datetime_handler
    from crawler_pool import release_crawler

    try:
        async for result in results_gen:
            try:
                server_memory_mb = _get_memory_mb()
                result_dict = result.model_dump()
                result_dict["server_memory_mb"] = server_memory_mb
                # Ensure fit_html is JSON-serializable
                if "fit_html" in result_dict and not (
                    result_dict["fit_html"] is None
                    or isinstance(result_dict["fit_html"], str)
                ):
                    result_dict["fit_html"] = None
                # If PDF exists, encode it to base64
                if result_dict.get("pdf") is not None:
                    result_dict["pdf"] = b64encode(result_dict["pdf"]).decode("utf-8")
                logger.info(f"Streaming result for {result_dict.get('url', 'unknown')}")
                data = json.dumps(result_dict, default=datetime_handler) + "\n"
                yield data.encode("utf-8")
            except Exception as e:
                logger.error(f"Serialization error: {e}")
                error_response = {
                    "error": str(e),
                    "url": getattr(result, "url", "unknown"),
                }
                yield (json.dumps(error_response) + "\n").encode("utf-8")

        yield json.dumps({"status": "completed"}).encode("utf-8")

    except asyncio.CancelledError:
        logger.warning("Client disconnected during streaming")
    finally:
        if crawler:
            await release_crawler(crawler)


async def handle_crawl_request(
    urls: List[str],
    browser_config: dict,
    crawler_config: dict,
    config: dict,
    hooks_config: Optional[dict] = None,
    crawler_configs: Optional[List[dict]] = None,
    render_mode: str = "full",
) -> dict:
    """Handle non-streaming crawl requests with optional hooks.

    ``render_mode`` selects the rendering strategy:
      - "full" (default): Playwright via the browser pool (existing path)
      - "static":        httpx + html2text, no browser (Aitosoft fallback)

    The "static" branch short-circuits before any browser-pool work so a
    hung browser can never affect static-mode latency.
    """
    # Track request start
    request_id = f"req_{uuid4().hex[:8]}"
    crawler = None
    try:
        from monitor import get_monitor

        await get_monitor().track_request_start(
            request_id, "/crawl", urls[0] if urls else "batch", browser_config
        )
    except:
        pass  # Monitor not critical

    start_mem_mb = _get_memory_mb()  # <--- Get memory before
    start_time = time.time()
    mem_delta_mb = None
    peak_mem_mb = start_mem_mb
    hook_manager = None

    try:
        urls = [
            ("https://" + url)
            if not url.startswith(("http://", "https://"))
            and not url.startswith(("raw:", "raw://"))
            else url
            for url in urls
        ]

        # Aitosoft: static-mode short-circuit. Completely bypass the browser
        # pool, patchright retry, and timeout fence — those all target
        # Playwright-level failures which, by definition, don't apply here.
        # Note: we do NOT cap concurrency inside handle_static_crawl_request
        # even though urls can be up to 100. MAS's current pattern is 1 URL
        # per request, so a per-URL burst is the theoretical upper bound; add
        # a Semaphore later if usage patterns shift and a single target host
        # starts rate-limiting us.
        if render_mode == "static":
            static_result = None
            try:
                static_result = await handle_static_crawl_request(
                    urls=urls, config=config
                )
                return static_result
            finally:
                try:
                    from monitor import get_monitor

                    any_success = bool(static_result) and any(
                        bool(r.get("success")) for r in static_result.get("results", [])
                    )
                    await get_monitor().track_request_end(
                        request_id, success=any_success, status_code=200
                    )
                except Exception:
                    pass

        browser_config = BrowserConfig.load(browser_config)
        crawler_config = CrawlerRunConfig.load(crawler_config)

        dispatcher = MemoryAdaptiveDispatcher(
            memory_threshold_percent=config["crawler"]["memory_threshold_percent"],
            rate_limiter=RateLimiter(
                base_delay=tuple(config["crawler"]["rate_limiter"]["base_delay"])
            )
            if config["crawler"]["rate_limiter"]["enabled"]
            else None,
        )

        from crawler_pool import get_crawler, release_crawler

        crawler = await get_crawler(browser_config)

        # Attach hooks if provided
        hooks_status = {}
        if hooks_config:
            from hook_manager import attach_user_hooks_to_crawler, UserHookManager

            hook_manager = UserHookManager(timeout=hooks_config.get("timeout", 30))
            hooks_status, hook_manager = await attach_user_hooks_to_crawler(
                crawler,
                hooks_config.get("code", {}),
                timeout=hooks_config.get("timeout", 30),
                hook_manager=hook_manager,
            )
            logger.info(f"Hooks attachment status: {hooks_status['status']}")

        base_config = config["crawler"]["base_config"]

        # Build the config(s) to pass to arun/arun_many
        if crawler_configs and len(urls) > 1:
            # Per-URL config list: deserialize each and apply base_config
            config_list = [CrawlerRunConfig.load(cc) for cc in crawler_configs]
            for cfg in config_list:
                for key, value in base_config.items():
                    if hasattr(cfg, key):
                        current_value = getattr(cfg, key)
                        if current_value is None or current_value == "":
                            setattr(cfg, key, value)
            effective_config = config_list
        else:
            # Single config (original behavior)
            for key, value in base_config.items():
                if hasattr(crawler_config, key):
                    current_value = getattr(crawler_config, key)
                    if current_value is None or current_value == "":
                        setattr(crawler_config, key, value)
            effective_config = crawler_config

        results = []
        func = getattr(crawler, "arun" if len(urls) == 1 else "arun_many")
        partial_func = partial(
            func,
            urls[0] if len(urls) == 1 else urls,
            config=effective_config,
            dispatcher=dispatcher,
        )

        async def _crawl_with_patchright():
            r = await partial_func()
            if not isinstance(r, list):
                r = [r]
            # Aitosoft: second-tier retry via patchright for any results that the
            # antibot_detector marked as blocked. Replaces blocked entries with
            # patchright results when the retry succeeds, otherwise preserves the
            # first-tier diagnostic. See aitosoft_patchright_fallback.py.
            try:
                from aitosoft_patchright_fallback import maybe_retry_blocked

                r = await maybe_retry_blocked(
                    results=r,
                    urls=urls,
                    crawler_config=crawler_config,
                    base_browser_config=browser_config,
                )
            except Exception as _e:
                logger.warning(f"[patchright] retry pass raised (non-fatal): {_e}")
            return r

        # Aitosoft: bounded timeout. On TimeoutError the wait_for cancels the
        # inner task, which unwinds back to our finally block that calls
        # release_crawler — no more leaked active_requests counters.
        try:
            results = await asyncio.wait_for(
                _crawl_with_patchright(), timeout=CRAWL_REQUEST_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            logger.error(
                f"[aitosoft] Crawl exceeded {CRAWL_REQUEST_TIMEOUT_S}s timeout "
                f"(urls={urls[:2]}{'...' if len(urls) > 2 else ''}). "
                f"Releasing pool slot via finally."
            )
            end_mem_mb_to = _get_memory_mb()
            if start_mem_mb is not None and end_mem_mb_to is not None:
                mem_delta_mb = end_mem_mb_to - start_mem_mb
            try:
                from monitor import get_monitor

                await get_monitor().track_request_end(
                    request_id, success=False, error="timeout", status_code=504
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=json.dumps(
                    {
                        "error": (
                            f"Crawl exceeded {CRAWL_REQUEST_TIMEOUT_S}s server timeout"
                        ),
                        "server_memory_delta_mb": mem_delta_mb,
                        "server_peak_memory_mb": max(
                            peak_mem_mb if peak_mem_mb else 0, end_mem_mb_to or 0
                        ),
                    }
                ),
            )

        end_mem_mb = _get_memory_mb()  # <--- Get memory after
        end_time = time.time()

        if start_mem_mb is not None and end_mem_mb is not None:
            mem_delta_mb = end_mem_mb - start_mem_mb  # <--- Calculate delta
            peak_mem_mb = max(
                peak_mem_mb if peak_mem_mb else 0, end_mem_mb
            )  # <--- Get peak memory
        logger.info(
            f"Memory usage: Start: {start_mem_mb} MB, End: {end_mem_mb} MB, Delta: {mem_delta_mb} MB, Peak: {peak_mem_mb} MB"
        )

        # Process results to handle PDF bytes
        processed_results = []
        for result in results:
            try:
                # Check if result has model_dump method (is a proper CrawlResult)
                if hasattr(result, "model_dump"):
                    result_dict = result.model_dump()
                elif isinstance(result, dict):
                    result_dict = result
                else:
                    # Handle unexpected result type
                    logger.warning(f"Unexpected result type: {type(result)}")
                    result_dict = {
                        "url": str(result) if hasattr(result, "__str__") else "unknown",
                        "success": False,
                        "error_message": f"Unexpected result type: {type(result).__name__}",
                    }

                # if fit_html is not a string, set it to None to avoid serialization errors
                if "fit_html" in result_dict and not (
                    result_dict["fit_html"] is None
                    or isinstance(result_dict["fit_html"], str)
                ):
                    result_dict["fit_html"] = None

                # If PDF exists, encode it to base64
                if result_dict.get("pdf") is not None and isinstance(
                    result_dict.get("pdf"), bytes
                ):
                    result_dict["pdf"] = b64encode(result_dict["pdf"]).decode("utf-8")

                # Aitosoft: tag every full-mode result so MAS can distinguish
                # responses produced by Playwright vs static-mode fallback.
                result_dict["render_mode"] = "full"

                processed_results.append(result_dict)
            except Exception as e:
                logger.error(f"Error processing result: {e}")
                processed_results.append(
                    {
                        "url": "unknown",
                        "success": False,
                        "error_message": str(e),
                        "render_mode": "full",
                    }
                )

        response = {
            "success": True,
            "results": processed_results,
            "server_processing_time_s": end_time - start_time,
            "server_memory_delta_mb": mem_delta_mb,
            "server_peak_memory_mb": peak_mem_mb,
        }

        # Track request completion
        try:
            from monitor import get_monitor

            await get_monitor().track_request_end(
                request_id, success=True, pool_hit=True, status_code=200
            )
        except:
            pass

        # Add hooks information if hooks were used
        if hooks_config and hook_manager:
            from hook_manager import UserHookManager

            if isinstance(hook_manager, UserHookManager):
                try:
                    # Ensure all hook data is JSON serializable
                    hook_data = {
                        "status": hooks_status,
                        "execution_log": hook_manager.execution_log,
                        "errors": hook_manager.errors,
                        "summary": hook_manager.get_summary(),
                    }
                    # Test that it's serializable
                    json.dumps(hook_data)
                    response["hooks"] = hook_data
                except (TypeError, ValueError) as e:
                    logger.error(f"Hook data not JSON serializable: {e}")
                    response["hooks"] = {
                        "status": {
                            "status": "error",
                            "message": "Hook data serialization failed",
                        },
                        "execution_log": [],
                        "errors": [{"error": str(e)}],
                        "summary": {},
                    }

        return response

    except HTTPException:
        # Already-structured responses (e.g. our 504 timeout) must propagate
        # unchanged. Do NOT rewrap as 500 in the generic handler below.
        raise
    except Exception as e:
        logger.error(f"Crawl error: {str(e)}", exc_info=True)

        # Track request error
        try:
            from monitor import get_monitor

            await get_monitor().track_request_end(
                request_id, success=False, error=str(e), status_code=500
            )
        except:
            pass

        # Measure memory even on error if possible
        end_mem_mb_error = _get_memory_mb()
        if start_mem_mb is not None and end_mem_mb_error is not None:
            mem_delta_mb = end_mem_mb_error - start_mem_mb

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=json.dumps(
                {  # Send structured error
                    "error": str(e),
                    "server_memory_delta_mb": mem_delta_mb,
                    "server_peak_memory_mb": max(
                        peak_mem_mb if peak_mem_mb else 0, end_mem_mb_error or 0
                    ),
                }
            ),
        )
    finally:
        if crawler:
            await release_crawler(crawler)


async def handle_stream_crawl_request(
    urls: List[str],
    browser_config: dict,
    crawler_config: dict,
    config: dict,
    hooks_config: Optional[dict] = None,
) -> Tuple[AsyncWebCrawler, AsyncGenerator, Optional[Dict]]:
    """Handle streaming crawl requests with optional hooks."""
    hooks_info = None
    crawler = None
    try:
        browser_config = BrowserConfig.load(browser_config)
        browser_config.verbose = False
        crawler_config = CrawlerRunConfig.load(crawler_config)
        crawler_config.scraping_strategy = LXMLWebScrapingStrategy()
        crawler_config.stream = True

        # Deep crawl streaming supports exactly one start URL
        if crawler_config.deep_crawl_strategy is not None and len(urls) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Deep crawling with stream currently supports exactly one URL per request. "
                    f"Received {len(urls)} URLs."
                ),
            )

        from crawler_pool import get_crawler, release_crawler

        crawler = await get_crawler(browser_config)

        # Attach hooks if provided
        if hooks_config:
            from hook_manager import attach_user_hooks_to_crawler, UserHookManager

            hook_manager = UserHookManager(timeout=hooks_config.get("timeout", 30))
            hooks_status, hook_manager = await attach_user_hooks_to_crawler(
                crawler,
                hooks_config.get("code", {}),
                timeout=hooks_config.get("timeout", 30),
                hook_manager=hook_manager,
            )
            logger.info(
                f"Hooks attachment status for streaming: {hooks_status['status']}"
            )
            # Include hook manager in hooks_info for proper tracking
            hooks_info = {"status": hooks_status, "manager": hook_manager}

        # Deep crawl with single URL: use arun() which returns an async generator
        # mirroring the Python library's streaming behavior
        if crawler_config.deep_crawl_strategy is not None and len(urls) == 1:
            results_gen = await crawler.arun(
                urls[0],
                config=crawler_config,
            )
        else:
            # Default multi-URL streaming via arun_many
            dispatcher = MemoryAdaptiveDispatcher(
                memory_threshold_percent=config["crawler"]["memory_threshold_percent"],
                rate_limiter=RateLimiter(
                    base_delay=tuple(config["crawler"]["rate_limiter"]["base_delay"])
                ),
            )
            results_gen = await crawler.arun_many(
                urls=urls, config=crawler_config, dispatcher=dispatcher
            )

        return crawler, results_gen, hooks_info

    except Exception as e:
        # Release crawler on setup error (for successful streams,
        # release happens in stream_results finally block)
        if crawler:
            await release_crawler(crawler)
        logger.error(f"Stream crawl error: {str(e)}", exc_info=True)
        # Raising HTTPException here will prevent streaming response
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


async def handle_crawl_job(
    redis,
    background_tasks: BackgroundTasks,
    urls: List[str],
    browser_config: Dict,
    crawler_config: Dict,
    config: Dict,
    webhook_config: Optional[Dict] = None,
) -> Dict:
    """
    Fire-and-forget version of handle_crawl_request.
    Creates a task in Redis, runs the heavy work in a background task,
    lets /crawl/job/{task_id} polling fetch the result.
    """
    task_id = f"crawl_{uuid4().hex[:8]}"

    # Store task data in Redis
    task_data = {
        "status": TaskStatus.PROCESSING,  # <-- keep enum values consistent
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "url": json.dumps(urls),  # store list as JSON string
        "result": "",
        "error": "",
    }

    # Store webhook config if provided
    if webhook_config:
        task_data["webhook_config"] = json.dumps(webhook_config)

    await hset_with_ttl(redis, f"task:{task_id}", task_data, config)

    # Initialize webhook service
    webhook_service = WebhookDeliveryService(config)

    async def _runner():
        try:
            result = await handle_crawl_request(
                urls=urls,
                browser_config=browser_config,
                crawler_config=crawler_config,
                config=config,
            )
            await hset_with_ttl(
                redis,
                f"task:{task_id}",
                {
                    "status": TaskStatus.COMPLETED,
                    "result": json.dumps(result),
                },
                config,
            )

            # Send webhook notification on successful completion
            await webhook_service.notify_job_completion(
                task_id=task_id,
                task_type="crawl",
                status="completed",
                urls=urls,
                webhook_config=webhook_config,
                result=result,
            )

            await asyncio.sleep(5)  # Give Redis time to process the update
        except Exception as exc:
            await hset_with_ttl(
                redis,
                f"task:{task_id}",
                {
                    "status": TaskStatus.FAILED,
                    "error": str(exc),
                },
                config,
            )

            # Send webhook notification on failure
            await webhook_service.notify_job_completion(
                task_id=task_id,
                task_type="crawl",
                status="failed",
                urls=urls,
                webhook_config=webhook_config,
                error=str(exc),
            )

    background_tasks.add_task(_runner)
    return {"task_id": task_id}
