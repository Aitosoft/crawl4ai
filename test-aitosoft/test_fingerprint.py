#!/usr/bin/env python3
"""
Fingerprint diagnostic — capture what bot-detection sites see when our crawl4ai
deployment visits them. Used for before/after comparison when landing stealth
improvements.

Usage:
    python test-aitosoft/test_fingerprint.py --label baseline
    python test-aitosoft/test_fingerprint.py --label stealth-v1
    python test-aitosoft/test_fingerprint.py --label stealth-v1 \
        --url http://localhost:11235

Artifacts land in test-aitosoft/stealth-<label>/:
    <site>.html        — raw HTML of the fingerprint page
    <site>.md          — markdown (often tells the story at a glance)
    <site>.png         — screenshot (base64-decoded from the API response)
    <site>.probe.json  — JS probe result: navigator.webdriver, plugins, etc.
    summary.json       — consolidated per-target status + probe digest
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests

DEFAULT_URL = os.getenv(
    "CRAWL4AI_API_URL",
    "https://crawl4ai-service.wonderfulsea-6a581e75.westeurope.azurecontainerapps.io",
)
TOKEN = os.getenv("CRAWL4AI_API_TOKEN")

# JS probe: direct readout of the signals that matter. Returned via
# result.js_execution_result. Run AFTER the page renders so sannysoft etc.
# have already populated their tables.
#
# IMPORTANT: crawl4ai wraps this in `async () => { <script> }` and takes the
# `return` value — so we use a top-level `return`, NOT an IIFE (whose return
# value would be discarded and replaced by `{success: true}`).
JS_PROBE = r"""
  const safe = (f) => { try { return f(); } catch (e) { return `ERR: ${e.message}`; } };
  return {
    webdriver: safe(() => navigator.webdriver),
    userAgent: safe(() => navigator.userAgent),
    platform: safe(() => navigator.platform),
    vendor: safe(() => navigator.vendor),
    languages: safe(() => navigator.languages),
    language: safe(() => navigator.language),
    pluginsLen: safe(() => navigator.plugins.length),
    mimeTypesLen: safe(() => navigator.mimeTypes.length),
    hardwareConcurrency: safe(() => navigator.hardwareConcurrency),
    deviceMemory: safe(() => navigator.deviceMemory),
    maxTouchPoints: safe(() => navigator.maxTouchPoints),
    timezone: safe(() => Intl.DateTimeFormat().resolvedOptions().timeZone),
    locale: safe(() => Intl.DateTimeFormat().resolvedOptions().locale),
    screen: safe(() => ({
      width: screen.width, height: screen.height,
      availWidth: screen.availWidth, availHeight: screen.availHeight,
      colorDepth: screen.colorDepth, pixelDepth: screen.pixelDepth,
    })),
    window: safe(() => ({
      innerWidth: window.innerWidth, innerHeight: window.innerHeight,
      outerWidth: window.outerWidth, outerHeight: window.outerHeight,
      devicePixelRatio: window.devicePixelRatio,
    })),
    chromeRuntime: safe(() => typeof window.chrome?.runtime !== 'undefined'),
    chromeLoadTimes: safe(() => typeof window.chrome?.loadTimes === 'function'),
    permissionsQuery: safe(() => typeof navigator.permissions?.query === 'function'),
    notificationPermission: safe(() => Notification?.permission),
    webglVendor: safe(() => {
      const c = document.createElement('canvas').getContext('webgl');
      if (!c) return 'no-webgl';
      const ext = c.getExtension('WEBGL_debug_renderer_info');
      return ext ? c.getParameter(ext.UNMASKED_VENDOR_WEBGL) : 'no-debug-info';
    }),
    webglRenderer: safe(() => {
      const c = document.createElement('canvas').getContext('webgl');
      if (!c) return 'no-webgl';
      const ext = c.getExtension('WEBGL_debug_renderer_info');
      return ext ? c.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'no-debug-info';
    }),
    canvasFp: safe(() => {
      const c = document.createElement('canvas');
      c.width = 200; c.height = 50;
      const ctx = c.getContext('2d');
      ctx.textBaseline = 'top';
      ctx.font = "14px 'Arial'";
      ctx.fillStyle = '#f60';
      ctx.fillRect(0, 0, 200, 50);
      ctx.fillStyle = '#069';
      ctx.fillText('fingerprint-probe-\u2603', 2, 2);
      return c.toDataURL().slice(-64);
    }),
    audioContext: safe(() =>
      typeof (window.AudioContext || window.webkitAudioContext) !== 'undefined'
    ),
    iframeContentWindow: safe(() => {
      const f = document.createElement('iframe');
      document.body.appendChild(f);
      const w = f.contentWindow;
      const ok = w && w.self === w;
      document.body.removeChild(f);
      return ok;
    }),
  };
"""

# Targets: public bot-detection test pages. Each is purpose-built for this.
TARGETS = [
    {
        "slug": "sannysoft",
        "url": "https://bot.sannysoft.com/",
        "note": "Classic fingerprint table (PASS/FAIL rows for each signal)",
    },
    {
        "slug": "areyouheadless",
        "url": "https://arh.antoinevastel.com/bots/areyouheadless",
        "note": "Simple headless detection (one-line verdict)",
    },
    {
        "slug": "creepjs",
        "url": "https://abrahamjuliot.github.io/creepjs/",
        "note": "Comprehensive fingerprint dump (trust score)",
    },
    {
        "slug": "browserleaks-js",
        "url": "https://browserleaks.com/javascript",
        "note": "navigator properties, webdriver, canvas, webgl, audio",
    },
]


def run_one(target: Dict[str, str], api_url: str, token: str) -> Dict[str, Any]:
    """Hit one fingerprint target through crawl4ai, return raw result dict."""
    payload = {
        "urls": [target["url"]],
        "crawler_config": {
            "wait_until": "networkidle",
            "page_timeout": 90000,
            "delay_before_return_html": 8.0,
            "screenshot": True,
            "remove_consent_popups": True,
            "js_code": JS_PROBE,
        },
    }
    print(f"\n  → {target['slug']:<18} {target['url']}")
    t0 = datetime.now(timezone.utc)
    try:
        resp = requests.post(
            f"{api_url.rstrip('/')}/crawl",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=180,
        )
    except requests.RequestException as e:
        return {"error": f"request_failed: {e}"}
    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()

    if resp.status_code != 200:
        body = resp.text[:500]
        print(f"     HTTP {resp.status_code} — {body}")
        return {"error": f"http_{resp.status_code}", "body": body, "elapsed": elapsed}

    data = resp.json()
    if not data.get("success"):
        err = data.get("error") or data.get("results", [{}])[0].get("error_message", "")
        print(f"     success=False — {err[:200]}")
        return {"error": "not_success", "detail": err, "elapsed": elapsed, "raw": data}

    results = data.get("results", [])
    if not results:
        return {"error": "empty_results", "elapsed": elapsed}
    first = results[0]
    print(
        f"     HTTP {first.get('status_code')} — {elapsed:.1f}s — "
        f"html={len(first.get('html') or '')}B"
    )
    first["_elapsed"] = elapsed
    return first


def save_artifacts(
    target: Dict[str, str], result: Dict[str, Any], out_dir: Path
) -> Dict[str, Any]:
    """Write html/md/screenshot/probe to disk, return a probe digest."""
    slug = target["slug"]
    out_dir.mkdir(parents=True, exist_ok=True)

    if "error" in result:
        (out_dir / f"{slug}.error.txt").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        return {"slug": slug, "status": "ERROR", "error": result.get("error")}

    html = result.get("html") or result.get("cleaned_html") or ""
    (out_dir / f"{slug}.html").write_text(html, encoding="utf-8")

    md_obj = result.get("markdown") or {}
    raw_md = (md_obj.get("raw_markdown") if isinstance(md_obj, dict) else md_obj) or ""
    (out_dir / f"{slug}.md").write_text(raw_md, encoding="utf-8")

    shot_b64 = result.get("screenshot")
    if shot_b64:
        try:
            (out_dir / f"{slug}.png").write_bytes(base64.b64decode(shot_b64))
        except Exception as e:
            (out_dir / f"{slug}.png.error").write_text(str(e))

    probe: Any = None
    jsr = result.get("js_execution_result")
    if isinstance(jsr, dict):
        # crawl4ai wraps js_code results under "results" list
        inner = jsr.get("results") if "results" in jsr else jsr
        probe = inner[0] if isinstance(inner, list) and inner else inner
    elif isinstance(jsr, list) and jsr:
        probe = jsr[0]
    else:
        probe = jsr

    (out_dir / f"{slug}.probe.json").write_text(
        json.dumps(probe, indent=2, default=str), encoding="utf-8"
    )

    digest = {
        "slug": slug,
        "status": "OK",
        "status_code": result.get("status_code"),
        "elapsed_s": round(result.get("_elapsed", 0), 2),
        "html_bytes": len(html),
        "markdown_bytes": len(raw_md),
        "has_screenshot": bool(shot_b64),
    }
    if isinstance(probe, dict):
        digest["probe"] = {
            "webdriver": probe.get("webdriver"),
            "userAgent": probe.get("userAgent"),
            "platform": probe.get("platform"),
            "vendor": probe.get("vendor"),
            "languages": probe.get("languages"),
            "timezone": probe.get("timezone"),
            "locale": probe.get("locale"),
            "pluginsLen": probe.get("pluginsLen"),
            "hardwareConcurrency": probe.get("hardwareConcurrency"),
            "deviceMemory": probe.get("deviceMemory"),
            "webglVendor": probe.get("webglVendor"),
            "webglRenderer": probe.get("webglRenderer"),
            "chromeRuntime": probe.get("chromeRuntime"),
            "chromeLoadTimes": probe.get("chromeLoadTimes"),
            "screen": probe.get("screen"),
            "window": probe.get("window"),
        }
    return digest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--label",
        required=True,
        help="Artifact dir suffix, e.g. 'baseline' or 'stealth-v1'",
    )
    p.add_argument("--url", default=DEFAULT_URL, help="crawl4ai API base URL")
    p.add_argument("--only", help="Run only this target slug (for debugging)")
    args = p.parse_args()

    if not TOKEN:
        print("ERROR: CRAWL4AI_API_TOKEN not set in environment", file=sys.stderr)
        sys.exit(2)

    out_dir = Path(__file__).parent / f"stealth-{args.label}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 72}")
    print(f"Fingerprint diagnostic — label: {args.label}")
    print(f"API: {args.url}")
    print(f"Out: {out_dir}")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'=' * 72}")

    digests = []
    for t in TARGETS:
        if args.only and t["slug"] != args.only:
            continue
        result = run_one(t, args.url, TOKEN)
        digest = save_artifacts(t, result, out_dir)
        digests.append(digest)

    summary = {
        "label": args.label,
        "api_url": args.url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": digests,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    print(f"\n{'-' * 72}\nSUMMARY\n{'-' * 72}")
    for d in digests:
        if d.get("status") == "OK":
            probe = d.get("probe") or {}
            wd = probe.get("webdriver")
            ua = (probe.get("userAgent") or "")[:80]
            plat = probe.get("platform")
            print(
                f"  {d['slug']:<18} OK  {d['status_code']}  "
                f"{d['elapsed_s']}s  webdriver={wd}  platform={plat}"
            )
            print(f"                     UA: {ua}")
            print(
                f"                     TZ={probe.get('timezone')}  "
                f"locale={probe.get('locale')}  "
                f"plugins={probe.get('pluginsLen')}  "
                f"cores={probe.get('hardwareConcurrency')}"
            )
            webgl_v = probe.get("webglVendor")
            webgl_r = probe.get("webglRenderer")
            print(f"                     webgl={webgl_v} / {webgl_r}")
        else:
            print(f"  {d['slug']:<18} ERR  {d.get('error')}")
    print(f"\nArtifacts: {out_dir}\n")


if __name__ == "__main__":
    main()
