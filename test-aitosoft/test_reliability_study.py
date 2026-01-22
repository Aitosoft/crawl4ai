#!/usr/bin/env python3
"""
Crawl4AI Reliability Study - Master Test Script

Purpose: Gather 100+ data points to validate failure rates and solutions.

Usage:
    # Isolated requests (baseline)
    python test-aitosoft/test_reliability_study.py --mode isolated --url yhteystiedot --count 100
    python test-aitosoft/test_reliability_study.py --mode isolated --url yritys --count 100

    # Batched requests (solution validation)
    python test-aitosoft/test_reliability_study.py --mode batched --count 100

    # Retry logic (solution validation)
    python test-aitosoft/test_reliability_study.py --mode retry --url yhteystiedot --count 100
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime
from pathlib import Path
import requests

CRAWL4AI_URL = (
    "https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io"
)
CRAWL4AI_TOKEN = os.getenv("CRAWL4AI_API_TOKEN")

if not CRAWL4AI_TOKEN:
    print("❌ Error: CRAWL4AI_API_TOKEN not set")
    print("   Run: export CRAWL4AI_API_TOKEN='...'")
    sys.exit(1)

CRAWL4AI_V10_CONFIG = {
    "wait_until": "domcontentloaded",
    "remove_overlay_elements": True,
    "page_timeout": 60000,
    "magic": True,
    "scan_full_page": True,
}

URLS = {
    "yhteystiedot": "https://www.talgraf.fi/yhteystiedot/",
    "yritys": "https://www.talgraf.fi/yritys/",
}


def crawl_single_url(url: str) -> dict:
    """Crawl a single URL and return result."""
    start_time = time.time()

    try:
        response = requests.post(
            f"{CRAWL4AI_URL}/crawl",
            headers={"Authorization": f"Bearer {CRAWL4AI_TOKEN}"},
            json={"urls": [url], "crawler_config": CRAWL4AI_V10_CONFIG},
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        elapsed = time.time() - start_time

        if result.get("success"):
            data = result["results"][0]
            chars = len(data.get("markdown", {}).get("raw_markdown", ""))
            return {
                "success": True,
                "chars": chars,
                "elapsed": elapsed,
                "ok": chars > 100,
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Unknown"),
                "elapsed": elapsed,
                "ok": False,
            }

    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "success": False,
            "error": str(e),
            "elapsed": elapsed,
            "ok": False,
        }


def crawl_batched() -> dict:
    """Crawl both URLs in one batched request."""
    start_time = time.time()
    urls = [URLS["yhteystiedot"], URLS["yritys"]]

    try:
        response = requests.post(
            f"{CRAWL4AI_URL}/crawl",
            headers={"Authorization": f"Bearer {CRAWL4AI_TOKEN}"},
            json={"urls": urls, "crawler_config": CRAWL4AI_V10_CONFIG},
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        elapsed = time.time() - start_time

        if result.get("success"):
            yhteystiedot_chars = len(
                result["results"][0].get("markdown", {}).get("raw_markdown", "")
            )
            yritys_chars = len(
                result["results"][1].get("markdown", {}).get("raw_markdown", "")
            )

            return {
                "success": True,
                "yhteystiedot_chars": yhteystiedot_chars,
                "yritys_chars": yritys_chars,
                "yhteystiedot_ok": yhteystiedot_chars > 100,
                "yritys_ok": yritys_chars > 100,
                "elapsed": elapsed,
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Unknown"),
                "elapsed": elapsed,
            }

    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "success": False,
            "error": str(e),
            "elapsed": elapsed,
        }


def crawl_with_retry(url: str) -> dict:
    """Crawl URL with one retry on failure."""
    # First attempt
    result = crawl_single_url(url)

    if result["success"] and result["ok"]:
        return {**result, "retried": False}

    # Retry if failed or very short content
    print(f"      Retrying (first attempt: {result.get('chars', 'error')} chars)...")
    time.sleep(2)
    retry_result = crawl_single_url(url)

    return {**retry_result, "retried": True}


def run_isolated_test(url_key: str, count: int):
    """Run isolated single-URL requests."""
    url = URLS[url_key]
    print(f"\n{'=' * 80}")
    print(f"ISOLATED TEST: {url_key.upper()}")
    print(f"{'=' * 80}")
    print(f"URL: {url}")
    print(f"Count: {count}")
    print(f"Started: {datetime.now().isoformat()}\n")

    results = []
    for i in range(count):
        print(f"[{i+1:3d}/{count}] ", end="", flush=True)
        result = crawl_single_url(url)
        results.append({"iteration": i + 1, **result})

        if result["success"]:
            status = "✅" if result["ok"] else f"❌ ({result['chars']} chars)"
            print(f"{status} in {result['elapsed']:.1f}s")
        else:
            print(f"❌ Error: {result.get('error', 'Unknown')}")

        time.sleep(1)  # 1 second delay between requests

    return results


def run_batched_test(count: int):
    """Run batched multi-URL requests."""
    print(f"\n{'=' * 80}")
    print("BATCHED TEST")
    print(f"{'=' * 80}")
    print("URLs: yhteystiedot + yritys (2 per request)")
    print(f"Count: {count}")
    print(f"Started: {datetime.now().isoformat()}\n")

    results = []
    for i in range(count):
        print(f"[{i+1:3d}/{count}] ", end="", flush=True)
        result = crawl_batched()
        results.append({"iteration": i + 1, **result})

        if result["success"]:
            yhteystiedot_status = (
                "✅"
                if result["yhteystiedot_ok"]
                else f"❌ ({result['yhteystiedot_chars']} chars)"
            )
            yritys_status = (
                "✅" if result["yritys_ok"] else f"❌ ({result['yritys_chars']} chars)"
            )
            print(f"yhteystiedot: {yhteystiedot_status:25} | yritys: {yritys_status}")
        else:
            print(f"❌ Error: {result.get('error', 'Unknown')}")

        time.sleep(1)

    return results


def run_retry_test(url_key: str, count: int):
    """Run requests with retry logic."""
    url = URLS[url_key]
    print(f"\n{'=' * 80}")
    print(f"RETRY TEST: {url_key.upper()}")
    print(f"{'=' * 80}")
    print(f"URL: {url}")
    print(f"Count: {count}")
    print("Strategy: Retry once if content < 500 chars")
    print(f"Started: {datetime.now().isoformat()}\n")

    results = []
    for i in range(count):
        print(f"[{i+1:3d}/{count}] ", end="", flush=True)
        result = crawl_with_retry(url)
        results.append({"iteration": i + 1, **result})

        if result["success"]:
            status = "✅" if result["ok"] else f"❌ ({result['chars']} chars)"
            retry_marker = " (retried)" if result["retried"] else ""
            print(f"{status}{retry_marker} in {result['elapsed']:.1f}s")
        else:
            print(f"❌ Error: {result.get('error', 'Unknown')}")

        time.sleep(1)

    return results


def generate_summary(mode: str, url_key: str, results: list):
    """Generate summary statistics."""
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")

    if mode in ["isolated", "retry"]:
        successful = [r for r in results if r["success"]]
        ok_results = [r for r in successful if r["ok"]]
        failed_results = [r for r in successful if not r["ok"]]

        print(f"\nTotal Requests: {len(results)}")
        print(
            f"  ✅ Successes: {len(ok_results)}/{len(results)} ({len(ok_results)/len(results)*100:.1f}%)"
        )
        print(
            f"  ❌ Failures: {len(failed_results)}/{len(results)} ({len(failed_results)/len(results)*100:.1f}%)"
        )

        if ok_results:
            avg_chars = sum(r["chars"] for r in ok_results) / len(ok_results)
            avg_time = sum(r["elapsed"] for r in ok_results) / len(ok_results)
            print("\nSuccess Statistics:")
            print(f"  Avg chars: {avg_chars:,.0f}")
            print(f"  Avg response time: {avg_time:.1f}s")

        if failed_results:
            avg_chars = sum(r["chars"] for r in failed_results) / len(failed_results)
            print("\nFailure Statistics:")
            print(f"  Avg chars: {avg_chars:,.0f}")
            print(
                f"\n  Failed iterations: {', '.join(str(r['iteration']) for r in failed_results)}"
            )

        if mode == "retry":
            retried = [r for r in results if r.get("retried")]
            print("\nRetry Statistics:")
            print(f"  Total retries: {len(retried)}/{len(results)}")

    elif mode == "batched":
        successful = [r for r in results if r["success"]]
        yhteystiedot_ok = [r for r in successful if r["yhteystiedot_ok"]]
        yhteystiedot_failed = [r for r in successful if not r["yhteystiedot_ok"]]
        yritys_ok = [r for r in successful if r["yritys_ok"]]
        yritys_failed = [r for r in successful if not r["yritys_ok"]]

        print(f"\nTotal Batched Requests: {len(results)}")
        print("\n/yhteystiedot/:")
        print(
            f"  ✅ Successes: {len(yhteystiedot_ok)}/{len(successful)} ({len(yhteystiedot_ok)/len(successful)*100:.1f}%)"
        )
        print(
            f"  ❌ Failures: {len(yhteystiedot_failed)}/{len(successful)} ({len(yhteystiedot_failed)/len(successful)*100:.1f}%)"
        )

        print("\n/yritys/:")
        print(
            f"  ✅ Successes: {len(yritys_ok)}/{len(successful)} ({len(yritys_ok)/len(successful)*100:.1f}%)"
        )
        print(
            f"  ❌ Failures: {len(yritys_failed)}/{len(successful)} ({len(yritys_failed)/len(successful)*100:.1f}%)"
        )

    print(f"\n{'=' * 80}")


def save_results(mode: str, url_key: str, results: list):
    """Save results to JSON file."""
    results_dir = Path("test-aitosoft/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reliability-study-{mode}-{url_key or 'both'}-{timestamp}.json"
    filepath = results_dir / filename

    # Calculate summary stats
    if mode in ["isolated", "retry"]:
        successful = [r for r in results if r["success"]]
        ok_results = [r for r in successful if r["ok"]]
        failed_results = [r for r in successful if not r["ok"]]

        summary = {
            "total_requests": len(results),
            "successes": len(ok_results),
            "failures": len(failed_results),
            "success_rate": len(ok_results) / len(results) if results else 0,
            "failure_rate": len(failed_results) / len(results) if results else 0,
        }

        if ok_results:
            summary["avg_success_chars"] = sum(r["chars"] for r in ok_results) / len(
                ok_results
            )
            summary["avg_response_time"] = sum(r["elapsed"] for r in ok_results) / len(
                ok_results
            )

    elif mode == "batched":
        successful = [r for r in results if r["success"]]
        yhteystiedot_ok = [r for r in successful if r["yhteystiedot_ok"]]
        yhteystiedot_failed = [r for r in successful if not r["yhteystiedot_ok"]]

        summary = {
            "total_batches": len(results),
            "yhteystiedot_successes": len(yhteystiedot_ok),
            "yhteystiedot_failures": len(yhteystiedot_failed),
            "yhteystiedot_success_rate": len(yhteystiedot_ok) / len(successful)
            if successful
            else 0,
        }

    output = {
        "test_date": datetime.now().isoformat(),
        "mode": mode,
        "url": url_key,
        "summary": summary,
        "raw_results": results,
    }

    with open(filepath, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n💾 Results saved: {filepath}")


def main():
    parser = argparse.ArgumentParser(
        description="Crawl4AI Reliability Study",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Baseline testing
  python test-aitosoft/test_reliability_study.py --mode isolated --url yhteystiedot --count 100
  python test-aitosoft/test_reliability_study.py --mode isolated --url yritys --count 100

  # Solution validation
  python test-aitosoft/test_reliability_study.py --mode batched --count 100
  python test-aitosoft/test_reliability_study.py --mode retry --url yhteystiedot --count 100
        """,
    )

    parser.add_argument(
        "--mode",
        required=True,
        choices=["isolated", "batched", "retry"],
        help="Test mode",
    )
    parser.add_argument(
        "--url",
        choices=["yhteystiedot", "yritys"],
        help="URL to test (required for isolated/retry modes)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Number of requests to make (default: 100)",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.mode in ["isolated", "retry"] and not args.url:
        parser.error(f"--url is required for {args.mode} mode")

    # Run test
    if args.mode == "isolated":
        results = run_isolated_test(args.url, args.count)
    elif args.mode == "batched":
        results = run_batched_test(args.count)
    elif args.mode == "retry":
        results = run_retry_test(args.url, args.count)

    # Generate summary
    generate_summary(args.mode, args.url, results)

    # Save results
    save_results(args.mode, args.url, results)

    print("\n✅ Test complete!")


if __name__ == "__main__":
    main()
