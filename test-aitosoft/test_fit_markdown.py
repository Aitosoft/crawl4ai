#!/usr/bin/env python3
"""
Test script to verify fit_markdown output with PruningContentFilter
"""
import asyncio
import json
import pytest
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator


@pytest.mark.asyncio
async def test_fit_markdown():
    """Test crawling with fit_markdown configuration"""
    print("🚀 Testing fit_markdown configuration...")

    # Your desired configuration
    config = CrawlerRunConfig(
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.6),
            options={"ignore_links": False},  # We want links for your use case
        )
    )

    browser_config = BrowserConfig(headless=True, verbose=True)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Test with example.com first
        result = await crawler.arun(url="https://example.com", config=config)

        print(f"✅ Success: {result.success}")
        print(f"📄 Status Code: {result.status_code}")
        print(f"🔗 URL: {result.url}")
        print(f"📝 Title: {result.metadata.get('title', 'No title')}")

        # Check what we have in the result
        print("\n" + "=" * 50)
        print("📋 Available Result Properties:")
        print("=" * 50)

        # Check markdown content
        if hasattr(result, "markdown"):
            raw_len = len(result.markdown.raw_markdown or "")
            fit_len = len(result.markdown.fit_markdown or "")
            print(f"📄 Raw Markdown Length: {raw_len}")
            print(f"✂️  Fit Markdown Length: {fit_len}")

        # Check links
        if hasattr(result, "links"):
            print(f"🔗 Internal Links: {len(result.links.get('internal', []))}")
            print(f"🔗 External Links: {len(result.links.get('external', []))}")

        # Show actual content (truncated for readability)
        print("\n" + "=" * 50)
        print("📄 Raw Markdown (first 300 chars):")
        print("=" * 50)
        if result.markdown.raw_markdown:
            print(
                result.markdown.raw_markdown[:300] + "..."
                if len(result.markdown.raw_markdown) > 300
                else result.markdown.raw_markdown
            )

        print("\n" + "=" * 50)
        print("✂️  Fit Markdown (first 300 chars):")
        print("=" * 50)
        if result.markdown.fit_markdown:
            print(
                result.markdown.fit_markdown[:300] + "..."
                if len(result.markdown.fit_markdown) > 300
                else result.markdown.fit_markdown
            )

        print("\n" + "=" * 50)
        print("🔗 Links Sample:")
        print("=" * 50)
        if result.links:
            print(
                f"Internal: {result.links.get('internal', [])[:3]}"
            )  # First 3 internal links
            print(
                f"External: {result.links.get('external', [])[:3]}"
            )  # First 3 external links

        # Return the data structure you'll need for the API
        api_response = {
            "success": result.success,
            "url": result.url,
            "title": result.metadata.get("title", ""),
            "markdown": result.markdown.raw_markdown,
            "fit_markdown": result.markdown.fit_markdown,
            "links": result.links,
            "status_code": result.status_code,
        }

        print("\n" + "=" * 50)
        print("📦 API Response Structure:")
        print("=" * 50)
        print(
            json.dumps(
                {
                    k: f"{type(v).__name__} ({len(str(v))} chars)"
                    if isinstance(v, str)
                    else v
                    for k, v in api_response.items()
                },
                indent=2,
            )
        )

        return api_response


if __name__ == "__main__":
    result = asyncio.run(test_fit_markdown())
    print("\n🎉 Test completed!")
