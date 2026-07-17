# RenderGate vs dispatcher: multi-URL batches can exceed render capacity

**Status:** Open (created 2026-07-17 from the repo audit) — LATENT, not urgent
**Priority:** Low until MAS batches URLs; then it blocks them
**Effort:** M. **Risk:** medium (hot path; needs a bench re-run).

## Problem

`RenderGate.acquire` clamps weight to capacity
(`deploy/docker/aitosoft_admission.py`, see the KNOWN LIMITATION note in the
docstring). A 10-URL `/crawl` request is admitted at weight 2, but
`arun_many` + MemoryAdaptiveDispatcher + upstream's GLOBAL_SEM(5) can then
run up to 5 concurrent renders on the replica — violating the "max 2
concurrent renders per replica" invariant the gate exists to enforce (the
2-vCPU benchmark, CLAUDE.md Key Findings).

Latent today because MAS sends single-URL requests (pinned by
test_mas_contract.py). The docstring documents the limitation.

## Options (decide when picking this up)

1. **Acquire uncapped weight:** a request for N URLs waits for N slots (or
   429s if N > capacity — forces MAS to chunk batches ≤2). Simple, strict,
   but large batches would always 429.
2. **Clamp dispatcher concurrency to granted weight:** thread the granted
   weight into the crawl call chain so the dispatcher's internal semaphore
   matches. Keeps big batches possible at correct pacing; more invasive.

Option 2 is the better end state; option 1 is an acceptable stopgap.

## Plan

1. Coordinate with MAS first — if they commit to single-URL requests
   long-term, documenting the constraint in the contract (and asserting
   `len(urls) == 1` per request at the trust boundary) may be all this needs.
2. Otherwise implement the chosen option + offline tests (multi-URL request
   holds/receives correct concurrency) + re-run the 2-vCPU render bench.

## Progress

- 2026-07-17: Task created; limitation documented in the acquire() docstring.
