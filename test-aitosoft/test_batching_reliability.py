#!/usr/bin/env python3
"""
Test if batching really has 100% success rate or if it was just luck.

Since yhteystiedot fails ~7-10% of the time when requested alone,
does batching improve reliability?
"""

import os
import sys
import time
import requests

CRAWL4AI_URL = (
    "https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io"
)
CRAWL4AI_TOKEN = os.getenv("CRAWL4AI_API_TOKEN")

if not CRAWL4AI_TOKEN:
    print("❌ Error: CRAWL4AI_API_TOKEN not set")
    sys.exit(1)

CRAWL4AI_V10_CONFIG = {
    "wait_until": "domcontentloaded",
    "remove_overlay_elements": True,
    "page_timeout": 60000,
    "magic": True,
    "scan_full_page": True,
}


def test_batched_request():
    """Test sending both URLs in one request."""
    urls = [
        "https://www.talgraf.fi/yhteystiedot/",
        "https://www.talgraf.fi/yritys/",
    ]

    try:
        response = requests.post(
            f"{CRAWL4AI_URL}/crawl",
            headers={"Authorization": f"Bearer {CRAWL4AI_TOKEN}"},
            json={"urls": urls, "crawler_config": CRAWL4AI_V10_CONFIG},
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()

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
            }
        else:
            return {"success": False, "error": result.get("error", "Unknown")}

    except Exception as e:
        return {"success": False, "error": str(e)}


print("\n" + "=" * 80)
print("BATCHING RELIABILITY TEST")
print("=" * 80)
print("Testing if batching truly improves yhteystiedot success rate")
print("Expected: yhteystiedot fails ~7-10% when alone, batching should reduce this\n")

iterations = 20
print(f"Running {iterations} batched requests...\n")

results = []
for i in range(iterations):
    print(f"[{i+1:2d}] ", end="", flush=True)
    result = test_batched_request()
    results.append(result)

    if result["success"]:
        yhteystiedot_status = (
            "✅"
            if result["yhteystiedot_ok"]
            else f"❌ ({result['yhteystiedot_chars']} chars)"
        )
        yritys_status = (
            "✅" if result["yritys_ok"] else f"❌ ({result['yritys_chars']} chars)"
        )
        print(f"yhteystiedot: {yhteystiedot_status:20} | yritys: {yritys_status}")
    else:
        print(f"❌ Error: {result['error']}")

    time.sleep(1)  # 1 second between batches

# Analysis
print("\n" + "=" * 80)
print("ANALYSIS")
print("=" * 80)

successful_requests = [r for r in results if r["success"]]
yhteystiedot_successes = [r for r in successful_requests if r["yhteystiedot_ok"]]
yhteystiedot_failures = [r for r in successful_requests if not r["yhteystiedot_ok"]]
yritys_successes = [r for r in successful_requests if r["yritys_ok"]]
yritys_failures = [r for r in successful_requests if not r["yritys_ok"]]

print(f"\n📊 Results ({len(successful_requests)} successful batched requests):")
print("\n/yhteystiedot/:")
print(
    f"   ✅ Success: {len(yhteystiedot_successes)}/{len(successful_requests)} ({len(yhteystiedot_successes)/len(successful_requests)*100:.1f}%)"
)
print(
    f"   ❌ Failure: {len(yhteystiedot_failures)}/{len(successful_requests)} ({len(yhteystiedot_failures)/len(successful_requests)*100:.1f}%)"
)
if yhteystiedot_successes:
    avg_chars = sum(r["yhteystiedot_chars"] for r in yhteystiedot_successes) / len(
        yhteystiedot_successes
    )
    print(f"   Success avg: {avg_chars:,.0f} chars")
if yhteystiedot_failures:
    avg_chars = sum(r["yhteystiedot_chars"] for r in yhteystiedot_failures) / len(
        yhteystiedot_failures
    )
    print(f"   Failure avg: {avg_chars:,.0f} chars")

print("\n/yritys/:")
print(
    f"   ✅ Success: {len(yritys_successes)}/{len(successful_requests)} ({len(yritys_successes)/len(successful_requests)*100:.1f}%)"
)
print(
    f"   ❌ Failure: {len(yritys_failures)}/{len(successful_requests)} ({len(yritys_failures)/len(successful_requests)*100:.1f}%)"
)

print("\n🔍 Conclusions:")

baseline_failure_rate = 0.07  # 7% from isolation test
batched_failure_rate = len(yhteystiedot_failures) / len(successful_requests)

if batched_failure_rate == 0:
    print("   ✅ BATCHING WORKS: 0% failure rate vs 7% baseline")
    print("   • Batching may improve reliability through arun_many() coordination")
elif batched_failure_rate < baseline_failure_rate:
    print(
        f"   ⚠️  BATCHING HELPS: {batched_failure_rate*100:.1f}% failure rate vs {baseline_failure_rate*100:.1f}% baseline"
    )
    print("   • Batching reduces but doesn't eliminate failures")
elif batched_failure_rate > baseline_failure_rate:
    print(
        f"   ❌ BATCHING WORSE: {batched_failure_rate*100:.1f}% failure rate vs {baseline_failure_rate*100:.1f}% baseline"
    )
    print("   • Batching may not help or could make it worse")
else:
    print(
        f"   ⚠️  NO DIFFERENCE: {batched_failure_rate*100:.1f}% failure rate (same as baseline)"
    )
    print("   • Batching doesn't affect reliability")

print(
    f"\n   Sample size: {len(successful_requests)} batched requests (each containing 2 URLs)"
)

if len(yhteystiedot_failures) > 0:
    print("\n   ⚠️  yhteystiedot still failed even with batching")
    print("   • Bug is not solved by batching")
    print("   • Retry logic or timeout adjustments may be needed")

print("\n" + "=" * 80)
