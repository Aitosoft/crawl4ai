# Antibot minimal_text heuristic: full mode 500s on legitimately tiny pages

**Status:** Open (created 2026-07-17 from the TLS task's side observation)
**Priority:** Low — latent; no MAS report yet. Pick up if MAS reports a
missing tiny page, or bundle with the next antibot_detector work.
**Effort:** S-M. **Risk:** medium — this touches block detection, where a
false NEGATIVE (block page treated as content) silently poisons MAS's data
and costs more than the current false positive (a loud 500).

## Problem

Full mode returns HTTP 500 for any legitimately tiny page: the structural
`minimal_text` heuristic in `crawl4ai/antibot_detector.py` flags small
low-text pages as block pages; the patchright fallback then fetches the same
tiny content, gets flagged the same way, and the request fails. Static mode
has no such check and returns the content fine.

Evidence (prod, 2026-07-17): expired.badssl.com — 490 bytes, 18 visible
chars, fetch succeeded in 0.78s, then
`Blocked by anti-bot protection: Structural: minimal_text on small page`
→ HTTP 500 in full mode; HTTP 200 with correct markdown in static mode.
Full record: `tasks/done/tls-broken-cert-regression-2026-07-17.md`.

## Direction (decide when picking up — don't just weaken the heuristic)

The heuristic exists because real block pages are ALSO tiny. Candidate
approaches, roughly in order of appeal:

1. **Two-engine agreement:** when the pool browser and the patchright
   fallback return byte-identical (or near-identical) tiny content, treat it
   as a real page — a Cloudflare-style block would differ per engine or
   carry block markers. We already have both fetches by the time we 500.
2. **Low-confidence pass-through:** tiny-page "blocked" verdicts return the
   content with a `blocked_suspect: true` flag instead of failing, letting
   MAS decide. Requires a MAS-side contract addition — coordinate first.
3. **Document-only:** keep full mode strict; document "tiny pages → use
   `render_mode: static`" in the MAS contract. Zero code risk.

Whatever is chosen: Tier 1 + fingerprint gates must stay green, and blocked-
page detection needs a regression check using recorded fixtures — do NOT
live-test against blocked sites (site-safety rules).

## Progress

- 2026-07-17: Task created from Session-A finding. No code changes yet.
