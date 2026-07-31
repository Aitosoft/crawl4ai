# Batch preflight endpoint (MAS Q3: "yes, and batch")

**Status:** Open — unblocked by MAS's answer 2026-07-30, but **sequenced behind
`tasks/detector-round3-evidence-vs-inference.md`** (2026-07-31 — the
challenge-blindspot task it originally waited on has shipped, and round 3
replaced it as the gate). MAS measured four hosts where an 80,671-byte
`403 - Forbidden` body passed as `success: true` at status 202. A
`blocked_suspect` computed by today's detector returns `false` for exactly those,
which is the failure mode their hard requirement below was written to prevent.

**Pacing input needed:** MAS have already adopted single-URL static mode as their
pre-delete gate, so this endpoint is now a throughput fix rather than a
correctness gate. Its urgency is entirely "when is the ~15,000-company sweep
scheduled" — asked in `tmp/mas-repo-messages/08-*`. Do not build ahead of that
answer.
**Priority:** Medium-high, and time-boxed by MAS's planned ~15,000-company
re-enrichment sweep — this is the gate that stops that sweep destroying good
captures.
**Effort:** M. **Risk:** low-medium (new public surface; relaxes the single-URL
contract in one controlled place).
**Evidence:** `tmp/crawl4ai-reply-2.md` §5 Q3.

## What MAS asked for, verbatim in effect

- **Batch of up to ~100 URLs per call**, returning per URL
  `{reachable, status, final_url, bytes, elapsed_ms, blocked_suspect}`.
- **No markdown conversion.**
- **`blocked_suspect` must cover the challenge family**, not just the block-page
  family. Their words: *"If it only implements the current `antibot_detector`
  list it will return `false` for the 371 pages that are our actual problem, and
  a preflight that misses the dominant failure is worse than none because it
  licenses the delete."*
- If batching is contentious, per-URL still helps — but say so, because it
  changes whether they gate the whole sweep or only companies with a prior
  capture worth protecting.

Rationale for batch: 15,000 preflight calls at 0.3–2 s each is a serial hour or
a concurrency problem against our autoscaler.

## Design notes

- **This is the one justified exception to the single-URL contract**
  (`api.py handle_crawl_request`, multi-URL ⇒ 400, MAS ack 2026-07-17). Preflight
  does no browser work, so the reason for that contract — render admission
  accounting — does not apply. Implement it as a **separate endpoint**, not by
  relaxing `/crawl`. The single-URL guard on `/crawl` stays exactly as it is,
  and `test_mas_contract.py` must keep pinning it.
- Reuse `aitosoft_static_mode`'s client and its per-hop `egress_broker`
  redirect validation. Do **not** write a second HTTP path — every SSRF property
  we have lives in that function.
- Bound the fan-out (`STATIC_FETCH_MAX_CONCURRENCY = 10` is the existing
  precedent) and the per-URL timeout. A 100-URL call must not monopolise a
  2 vCPU replica; size it so the whole call finishes well inside the Azure
  ingress limit.
- Skip markdown conversion entirely — that is most of static mode's CPU.
- The gate does **not** need a browser, so it must **not** take a RenderGate
  slot. Confirm that explicitly; a preflight that consumes render capacity would
  defeat its own purpose during a sweep.
- `blocked_suspect` should reuse `antibot_detector` (post-blindspot fix), fed
  the **effective final status** — `antibot_detector.effective_status()` already
  exists from the redirect work.

## Sequencing

1. `tasks/antibot-detector-challenge-blindspot.md` — otherwise `blocked_suspect`
   lies in exactly the case that matters.
2. This task.

## Verification

- Offline suite: batch shaping, per-URL error isolation (one bad URL must not
  fail the batch), concurrency bound, and that a blocked/challenge fixture sets
  `blocked_suspect: true`.
- Assert no RenderGate acquisition on this path.
- Assert the `/crawl` single-URL guard is untouched.
- Load-shape check: one 100-URL call against benign hosts, measuring replica CPU
  and wall time. Use hosts we already hit routinely, not fresh ones.
