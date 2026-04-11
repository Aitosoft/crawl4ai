/**
 * Deterministic browser persona generator for crawl4ai requests.
 *
 * Reference implementation for the aitosoft-platform MAS team.
 *
 * Design
 * ------
 * Every Finnish company in our database (master_company_id: UUID) gets a
 * stable "browser identity" that crawl4ai uses when visiting that company's
 * website. Same company → same persona, every month. Different companies →
 * different personas. Rotating the PERSONA_SALT constant shifts every
 * company's persona to a new value (for when we want to re-seed the fleet,
 * e.g. after a year).
 *
 * Why stable-per-company beats random-per-request:
 * - Cloudflare's bot-management builds a reputation profile per (fingerprint,
 *   origin IP). A fingerprint that returns monthly from the same IP looks like
 *   a regular user bookmarking a site. A fingerprint that rotates on every
 *   request looks like fingerprint evasion, which is itself a scraping signal.
 *
 * The persona pool is deliberately Chromium-family only (Chrome + Edge).
 * Firefox/Safari personas would mismatch the underlying Playwright Chromium
 * engine and expose detectable quirks (WebGL renderer, audio fingerprint,
 * navigator.plugins format).
 *
 * Output shape matches crawl4ai's /crawl API:
 *   { browser_config: { user_agent, viewport_width, viewport_height, headers },
 *     crawler_config: { locale, timezone_id, ... } }
 *
 * Usage
 * -----
 *   import { personaForCompany } from "./persona_generator";
 *   const p = personaForCompany(company.master_company_id);
 *   await fetch(`${CRAWL4AI_URL}/crawl`, {
 *     method: "POST",
 *     headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
 *     body: JSON.stringify({
 *       urls: [companyUrl],
 *       browser_config: p.browser_config,
 *       crawler_config: { ...p.crawler_config, wait_until: "domcontentloaded", max_retries: 2 },
 *     }),
 *   });
 */

import { createHash } from "node:crypto";

// --- Types ------------------------------------------------------------------

export interface Persona {
  name: string;
  weight: number;
  browser_config: {
    user_agent: string;
    viewport_width: number;
    viewport_height: number;
    headers: {
      "Accept-Language": string;
      "sec-ch-ua": string;
      "sec-ch-ua-mobile": string;
      "sec-ch-ua-platform": string;
    };
  };
  crawler_config: {
    locale: string;
    timezone_id: string;
  };
}

export interface PersonaChoice {
  persona_name: string;
  browser_config: Persona["browser_config"];
  crawler_config: Persona["crawler_config"];
}

// --- Constants --------------------------------------------------------------

/**
 * Rotate this to reshuffle every company's persona assignment.
 * Change only when you want a full fleet re-seed (e.g., annual rotation, or
 * after a known fingerprint-based incident). DO NOT rotate casually — the
 * whole point is that companies see a STABLE identity month-over-month.
 */
const PERSONA_SALT = "aitosoft-crawl4ai-v1-2026";

/**
 * Finnish geographic/cultural defaults — applied to ALL personas because
 * we only crawl Finnish company websites. No variation here: a Finnish site
 * visited by "Helsinki time, fi-FI locale" is the expected pattern.
 */
const FINNISH_CRAWLER_CONFIG = {
  locale: "fi-FI",
  timezone_id: "Europe/Helsinki",
} as const;

const FINNISH_ACCEPT_LANGUAGE = "fi-FI,fi;q=0.9,en;q=0.8";

// --- Persona pool -----------------------------------------------------------
//
// Weights reflect approximate desktop browser+OS share in EMEA, 2026:
//   - Windows:   ~72% (Chrome 45%, Edge 20%, others 7%)
//   - macOS:     ~18% (Chrome 12%, others 6%)
//   - Linux:     ~4%  (Chrome 3%, others 1%)
//   - Others:    ~6%  (not represented — always the wrong tail to ride)
//
// We only ship Chromium-family personas because crawl4ai runs Playwright
// Chromium/Chrome under the hood. Shipping a Firefox UA with a Chromium
// engine is a clean fingerprint tell.
//
// Chrome versions: keep the distribution recent. When Chrome N+1 ships stable,
// add it and age out Chrome N-2. This file is meant to be updated ~quarterly.

export const PERSONAS: Persona[] = [
  // --- Windows 11 Chrome (most common) -----------------------------------
  {
    name: "chrome133-win11-1920x1080",
    weight: 18,
    browser_config: {
      user_agent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
      viewport_width: 1920,
      viewport_height: 1080,
      headers: {
        "Accept-Language": FINNISH_ACCEPT_LANGUAGE,
        "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
      },
    },
    crawler_config: FINNISH_CRAWLER_CONFIG,
  },
  {
    name: "chrome133-win11-1536x864",
    weight: 12,
    browser_config: {
      user_agent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
      viewport_width: 1536,
      viewport_height: 864,
      headers: {
        "Accept-Language": FINNISH_ACCEPT_LANGUAGE,
        "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
      },
    },
    crawler_config: FINNISH_CRAWLER_CONFIG,
  },
  {
    name: "chrome132-win11-1920x1080",
    weight: 10,
    browser_config: {
      user_agent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
      viewport_width: 1920,
      viewport_height: 1080,
      headers: {
        "Accept-Language": FINNISH_ACCEPT_LANGUAGE,
        "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="132", "Chromium";v="132"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
      },
    },
    crawler_config: FINNISH_CRAWLER_CONFIG,
  },
  {
    name: "chrome131-win11-1366x768",
    weight: 6,
    browser_config: {
      user_agent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      viewport_width: 1366,
      viewport_height: 768,
      headers: {
        "Accept-Language": FINNISH_ACCEPT_LANGUAGE,
        "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="131", "Chromium";v="131"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
      },
    },
    crawler_config: FINNISH_CRAWLER_CONFIG,
  },

  // --- Windows 11 Edge (Chromium-based, 20% of Windows) ------------------
  {
    name: "edge133-win11-1920x1080",
    weight: 12,
    browser_config: {
      user_agent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
      viewport_width: 1920,
      viewport_height: 1080,
      headers: {
        "Accept-Language": FINNISH_ACCEPT_LANGUAGE,
        "sec-ch-ua": '"Not A(Brand";v="99", "Microsoft Edge";v="133", "Chromium";v="133"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
      },
    },
    crawler_config: FINNISH_CRAWLER_CONFIG,
  },
  {
    name: "edge132-win11-1536x864",
    weight: 8,
    browser_config: {
      user_agent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0",
      viewport_width: 1536,
      viewport_height: 864,
      headers: {
        "Accept-Language": FINNISH_ACCEPT_LANGUAGE,
        "sec-ch-ua": '"Not A(Brand";v="99", "Microsoft Edge";v="132", "Chromium";v="132"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
      },
    },
    crawler_config: FINNISH_CRAWLER_CONFIG,
  },

  // --- Windows 10 (still ~20% share) -------------------------------------
  {
    name: "chrome133-win10-1920x1080",
    weight: 8,
    browser_config: {
      user_agent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
      viewport_width: 1920,
      viewport_height: 1080,
      headers: {
        "Accept-Language": FINNISH_ACCEPT_LANGUAGE,
        "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
      },
    },
    crawler_config: FINNISH_CRAWLER_CONFIG,
  },

  // --- macOS Chrome (16% of desktop) -------------------------------------
  {
    name: "chrome133-macos-1728x1117", // MacBook Pro 14"
    weight: 8,
    browser_config: {
      user_agent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
      viewport_width: 1728,
      viewport_height: 1117,
      headers: {
        "Accept-Language": FINNISH_ACCEPT_LANGUAGE,
        "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
      },
    },
    crawler_config: FINNISH_CRAWLER_CONFIG,
  },
  {
    name: "chrome133-macos-1440x900", // MacBook Air / older MBP 13"
    weight: 6,
    browser_config: {
      user_agent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
      viewport_width: 1440,
      viewport_height: 900,
      headers: {
        "Accept-Language": FINNISH_ACCEPT_LANGUAGE,
        "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
      },
    },
    crawler_config: FINNISH_CRAWLER_CONFIG,
  },
  {
    name: "chrome132-macos-1680x1050", // iMac 21.5 / 24
    weight: 4,
    browser_config: {
      user_agent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
      viewport_width: 1680,
      viewport_height: 1050,
      headers: {
        "Accept-Language": FINNISH_ACCEPT_LANGUAGE,
        "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="132", "Chromium";v="132"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
      },
    },
    crawler_config: FINNISH_CRAWLER_CONFIG,
  },

  // --- Linux Chrome (4% of desktop, but present) -------------------------
  {
    name: "chrome133-linux-1920x1080",
    weight: 4,
    browser_config: {
      user_agent:
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
      viewport_width: 1920,
      viewport_height: 1080,
      headers: {
        "Accept-Language": FINNISH_ACCEPT_LANGUAGE,
        "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
      },
    },
    crawler_config: FINNISH_CRAWLER_CONFIG,
  },
];

// --- Selection --------------------------------------------------------------

/**
 * Pick a persona deterministically from a company UUID.
 *
 * The hash is SHA-256 of "<PERSONA_SALT>:<companyId>", first 8 bytes
 * interpreted as a big-endian uint64, then modulo the cumulative weight.
 * Stable across runtimes, stable across Node versions, stable across
 * process restarts.
 *
 * @param companyId  UUID (or any stable string) identifying the target company.
 * @returns PersonaChoice ready to splat into the crawl4ai /crawl request body.
 */
export function personaForCompany(companyId: string): PersonaChoice {
  if (!companyId) {
    // Defensive default: never throw — return the highest-weight persona.
    const fallback = PERSONAS[0];
    return {
      persona_name: fallback.name,
      browser_config: fallback.browser_config,
      crawler_config: fallback.crawler_config,
    };
  }

  const hash = createHash("sha256")
    .update(`${PERSONA_SALT}:${companyId}`)
    .digest();
  // First 8 bytes → BigInt, then mod by total weight.
  const u64 = hash.readBigUInt64BE(0);
  const totalWeight = PERSONAS.reduce((sum, p) => sum + p.weight, 0);
  let cursor = Number(u64 % BigInt(totalWeight));

  for (const persona of PERSONAS) {
    cursor -= persona.weight;
    if (cursor < 0) {
      return {
        persona_name: persona.name,
        browser_config: persona.browser_config,
        crawler_config: persona.crawler_config,
      };
    }
  }

  // Unreachable if PERSONAS has at least one entry.
  const fallback = PERSONAS[0];
  return {
    persona_name: fallback.name,
    browser_config: fallback.browser_config,
    crawler_config: fallback.crawler_config,
  };
}

// --- Self-test (run: `ts-node persona_generator.ts` or similar) ------------

if (require.main === module) {
  const samples = [
    "00000000-0000-0000-0000-000000000001",
    "00000000-0000-0000-0000-000000000002",
    "11111111-2222-3333-4444-555555555555",
    "a1b2c3d4-e5f6-7890-abcd-ef0123456789",
    "caverna-fi",
    "baxter-fi",
    "lundbeck-fi",
    "pedelux-fi",
    "rederiabeckero-ax",
  ];

  console.log("Persona distribution test (determinism + spread):\n");
  for (const id of samples) {
    const p1 = personaForCompany(id);
    const p2 = personaForCompany(id); // Second call must match.
    const deterministic = p1.persona_name === p2.persona_name;
    console.log(
      `  ${id.padEnd(40)} → ${p1.persona_name.padEnd(30)} ${deterministic ? "✓" : "✗ NONDETERMINISTIC"}`,
    );
  }

  // Large-sample distribution check: does the pool spread reasonably?
  const counts: Record<string, number> = {};
  for (let i = 0; i < 10_000; i++) {
    const p = personaForCompany(`synthetic-${i}`);
    counts[p.persona_name] = (counts[p.persona_name] || 0) + 1;
  }
  console.log("\nDistribution over 10,000 synthetic IDs (expected vs actual):");
  const totalWeight = PERSONAS.reduce((s, p) => s + p.weight, 0);
  for (const persona of PERSONAS) {
    const expected = (persona.weight / totalWeight) * 10_000;
    const actual = counts[persona.name] || 0;
    const drift = (((actual - expected) / expected) * 100).toFixed(1);
    console.log(
      `  ${persona.name.padEnd(32)} expected ${expected.toFixed(0).padStart(5)}  actual ${String(actual).padStart(5)}  drift ${drift.padStart(6)}%`,
    );
  }
}
