# Enforce single-URL /crawl requests (MAS contract decision 2026-07-17)

**Status:** Open — DECIDED, ready to implement (rescoped 2026-07-17 after MAS's answer)
**Priority:** Medium — small change, closes the last latent capacity-invariant gap
**Effort:** S. **Risk:** low (rejects a request shape nobody sends).

## Decision (MAS, relayed via Tero 2026-07-17)

> We commit to single-URL /crawl requests long-term — enforce it at the
> boundary (400 on multi-URL) and document it in the contract; no change
> needed on our side.

Their reasoning, recorded for posterity: their client is structurally
single-URL (`src/lib/crawl4ai-client.ts` always sends `urls: [url]` and reads
only `results[0]`, so a multi-URL response would be silently truncated on
their side anyway); WAA is a ReAct loop, so requests are inherently
sequential per agent; their parallelism is multiple agents each sending
single-URL requests, already governed by the 2-renders-per-replica +
429/Retry-After contract. A 400 keeps the assumption visible instead of
silently violable.

## Original problem (now closed by enforcement rather than implementation)

`RenderGate.acquire` clamps weight to capacity, so a multi-URL request
admitted at weight ≤2 could render at up to GLOBAL_SEM(5) concurrency —
violating the 2-renders-per-replica invariant. With multi-URL requests
rejected at the boundary, the gap becomes structurally unreachable. The
weight-coherence implementation options considered are in this file's git
history (pre-2026-07-17 rescope) if batching ever returns as a deliberate
contract revision.

## Plan

1. Guard in `deploy/docker/api.py` `handle_crawl_request`: `len(urls) > 1` →
   HTTP **400** (not 422 — MAS expects 400) with a message naming the
   contract, e.g. `"multi-URL requests not supported: MAS contract is
   single-URL per request (AITOSOFT_CHANGES.md, 2026-07-17)"`. api.py is the
   right spot because it covers /crawl and is offline-testable the way
   test_admission.py already exercises `handle_crawl_request`.
2. Pin it offline in `test-aitosoft/test_mas_contract.py`: 2-URL request →
   400; 1-URL request unaffected.
3. Update the KNOWN LIMITATION note in `aitosoft_admission.py`'s
   `acquire()` docstring: the multi-URL path is now rejected upstream of the
   gate; keep one line pointing here.
4. Docs: AITOSOFT_CHANGES.md entry (contract addendum + MAS ack);
   CLAUDE.md per-request section gets a one-liner ("one URL per request —
   contract-enforced"); AITOSOFT_FILES.md api.py line count refresh.
5. Deploy + verify: single-URL crawl works, 2-URL request → 400, Tier 1.

## Progress

- 2026-07-17: Task created from audit; limitation documented in acquire()
  docstring; scope question sent to MAS.
- 2026-07-17: MAS committed to single-URL long-term; task rescoped from
  "weight coherence implementation" to "boundary enforcement + contract pin".
