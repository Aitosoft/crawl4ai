#!/usr/bin/env python3
"""
Test concurrent requests to the same domain to reproduce the talgraf.fi issue.

This simulates what the MAS agent does when it makes parallel tool calls:
- Two simultaneous HTTP requests to crawl4ai
- Same domain (talgraf.fi)
- Same config (CRAWL4AI_V10_CONFIG)
- Should expose race conditions in browser pooling
"""

import os
import sys
import asyncio
import requests
from datetime import datetime

CRAWL4AI_URL = (
    "https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io"
)
CRAWL4AI_TOKEN = os.getenv("CRAWL4AI_API_TOKEN")

if not CRAWL4AI_TOKEN:
    print("❌ Error: CRAWL4AI_API_TOKEN not set")
    sys.exit(1)

# Same config as MAS uses
CRAWL4AI_V10_CONFIG = {
    "wait_until": "domcontentloaded",
    "remove_overlay_elements": True,
    "page_timeout": 60000,
    "magic": True,
    "scan_full_page": True,
}


def crawl_url(url: str, label: str) -> dict:
    """Crawl a single URL and return result."""
    print(f"[{label}] Starting: {url}")
    start_time = datetime.now()

    try:
        response = requests.post(
            f"{CRAWL4AI_URL}/crawl",
            headers={"Authorization": f"Bearer {CRAWL4AI_TOKEN}"},
            json={"urls": [url], "crawler_config": CRAWL4AI_V10_CONFIG},
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()

        elapsed = (datetime.now() - start_time).total_seconds()

        if result.get("success"):
            data = result["results"][0]
            raw_len = len(data.get("markdown", {}).get("raw_markdown", ""))
            print(
                f"[{label}] ✅ Success in {elapsed:.1f}s: {raw_len} chars (~{raw_len // 4} tokens)"
            )
            return {
                "label": label,
                "url": url,
                "success": True,
                "chars": raw_len,
                "elapsed": elapsed,
            }
        else:
            print(
                f"[{label}] ❌ Failed in {elapsed:.1f}s: {result.get('error', 'Unknown')}"
            )
            return {
                "label": label,
                "url": url,
                "success": False,
                "error": result.get("error"),
                "elapsed": elapsed,
            }

    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[{label}] ❌ Exception in {elapsed:.1f}s: {e}")
        return {
            "label": label,
            "url": url,
            "success": False,
            "error": str(e),
            "elapsed": elapsed,
        }


async def test_concurrent_same_domain():
    """Test concurrent requests to the same domain (talgraf.fi)."""
    print("\n" + "=" * 80)
    print("TEST 1: Concurrent Requests to Same Domain (talgraf.fi)")
    print("=" * 80)
    print("Simulating MAS parallel tool calls:")
    print("  - call_1 → /yhteystiedot/")
    print("  - call_2 → /yritys/")
    print()

    urls = [
        ("https://www.talgraf.fi/yhteystiedot/", "yhteystiedot"),
        ("https://www.talgraf.fi/yritys/", "yritys"),
    ]

    # Run concurrently using asyncio
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, crawl_url, url, label) for url, label in urls]
    results = await asyncio.gather(*tasks)

    print("\n" + "-" * 80)
    print("RESULTS:")
    print("-" * 80)
    for r in results:
        if r["success"]:
            print(f"  {r['label']:15} ✅ {r['chars']:6} chars in {r['elapsed']:.1f}s")
        else:
            print(
                f"  {r['label']:15} ❌ {r.get('error', 'Failed')} in {r['elapsed']:.1f}s"
            )

    # Check for the bug
    success_count = sum(1 for r in results if r["success"])
    short_content = [r for r in results if r["success"] and r["chars"] < 100]

    print()
    if short_content:
        print("⚠️  BUG REPRODUCED!")
        for r in short_content:
            print(
                f"  → {r['label']} returned only {r['chars']} chars (race condition?)"
            )
    elif success_count == len(results):
        print("✅ No race condition detected (both succeeded)")
    else:
        print("❌ Some requests failed, but not due to short content")


async def test_batched_request():
    """Test sending both URLs in a single request (batched)."""
    print("\n" + "=" * 80)
    print("TEST 2: Batched Request (both URLs in one call)")
    print("=" * 80)
    print("Sending both URLs to crawl4ai in a single HTTP request")
    print()

    urls = [
        "https://www.talgraf.fi/yhteystiedot/",
        "https://www.talgraf.fi/yritys/",
    ]

    start_time = datetime.now()
    try:
        response = requests.post(
            f"{CRAWL4AI_URL}/crawl",
            headers={"Authorization": f"Bearer {CRAWL4AI_TOKEN}"},
            json={"urls": urls, "crawler_config": CRAWL4AI_V10_CONFIG},
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        elapsed = (datetime.now() - start_time).total_seconds()

        if result.get("success"):
            print(f"✅ Success in {elapsed:.1f}s")
            print("\nRESULTS:")
            print("-" * 80)
            for i, data in enumerate(result["results"]):
                raw_len = len(data.get("markdown", {}).get("raw_markdown", ""))
                url_path = urls[i].split("/")[-2] or "homepage"
                print(f"  {url_path:15} {raw_len:6} chars (~{raw_len // 4} tokens)")

            short_content = [
                (i, urls[i], len(r.get("markdown", {}).get("raw_markdown", "")))
                for i, r in enumerate(result["results"])
                if len(r.get("markdown", {}).get("raw_markdown", "")) < 100
            ]

            print()
            if short_content:
                print("⚠️  BUG FOUND!")
                for i, url, chars in short_content:
                    print(f"  → URL {i + 1} ({url}) returned only {chars} chars")
            else:
                print("✅ Both URLs returned full content (no race condition)")
        else:
            print(f"❌ Failed: {result.get('error', 'Unknown')}")

    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"❌ Exception in {elapsed:.1f}s: {e}")


async def test_sequential():
    """Test sequential requests (control group)."""
    print("\n" + "=" * 80)
    print("TEST 3: Sequential Requests (control group)")
    print("=" * 80)
    print("Sending requests one after another (no concurrency)")
    print()

    urls = [
        ("https://www.talgraf.fi/yhteystiedot/", "yhteystiedot"),
        ("https://www.talgraf.fi/yritys/", "yritys"),
    ]

    results = []
    for url, label in urls:
        result = crawl_url(url, label)
        results.append(result)

    print("\n" + "-" * 80)
    print("RESULTS:")
    print("-" * 80)
    for r in results:
        if r["success"]:
            print(f"  {r['label']:15} ✅ {r['chars']:6} chars in {r['elapsed']:.1f}s")
        else:
            print(
                f"  {r['label']:15} ❌ {r.get('error', 'Failed')} in {r['elapsed']:.1f}s"
            )

    short_content = [r for r in results if r["success"] and r["chars"] < 100]
    print()
    if short_content:
        print("⚠️  BUG FOUND in sequential requests!")
    else:
        print("✅ Both succeeded with full content")


async def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("CONCURRENCY TEST SUITE")
    print("=" * 80)
    print("Testing crawl4ai behavior with concurrent requests")
    print(f"Target: {CRAWL4AI_URL}")
    print()

    # Test 1: Concurrent requests (reproduces MAS scenario)
    await test_concurrent_same_domain()

    # Test 2: Batched request (potential solution)
    await test_batched_request()

    # Test 3: Sequential requests (control)
    await test_sequential()

    print("\n" + "=" * 80)
    print("TEST SUITE COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
