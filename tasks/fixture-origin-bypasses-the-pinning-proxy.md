# All 54 fixture tests run on a network path production does not use

**Status:** open, not started. Written 2026-08-05 by the session that shipped
`done/egress-proxy-blocks-the-event-loop.md`, from a reviewer's finding.
**Size:** S — ~12 lines in `fixture_origin.py`, plus whatever the truth costs.
**Gate:** none, and it is not urgent. But it is the highest-leverage *testing*
item we have, because it silently caps what every future fixture test can prove.

---

## The finding

`egress_broker.set_egress_proxy()` has exactly **one** caller: `server.py:183`,
inside the FastAPI lifespan. `ProductionPath` (`test-aitosoft/fixture_origin.py`)
calls `api.handle_crawl_request` directly, so the lifespan never runs,
`_EGRESS_PROXY_URL` stays `None`, and `enforce_egress` leaves `proxy_config`
`None`.

**So Chromium connects directly in every fixture test, and through the pinning
proxy in production.** That is not a detail: the proxy is where DNS resolution,
IP pinning, the connect timeout and the CONNECT/absolute-URI split all live.
Measured consequence from the same session — a dead host costs **134 s** direct
and **30 s** through the proxy. A test that does not start the proxy measures
the wrong number by 4×, and would happily validate a fix that does nothing.

The task file that led to this called it a "trap" for one new test. It is not.
**It is a standing faithfulness gap under all 54 existing tests** — the same
"unfaithful on exactly the load-bearing axis" failure as the `/block/padded-403`
fixture, but wider.

---

## What to do

Start the proxy in `ProductionPath` on the same loop the crawl runs on, call
`egress_broker.set_egress_proxy(url)`, and stop it in `close()`. Sketch only —
verify it rather than paste it:

- start inside whatever already owns the loop, so `asyncio.start_server` binds
  to the right one (the production bug this whole family is about);
- `set_egress_proxy(None)` on teardown, or the next test in the same process
  inherits a dead proxy URL — this is a module global;
- `loopback_allowed()` (`fixture_origin.py:907`) already flips `ALLOW_INTERNAL`,
  and `resolve_and_pin` still resolves and pins under it, so `127.0.0.1` targets
  work through the proxy. Verify that, do not assume it.

Cost estimate from the reviewer: ~0.4 s per crawl, so roughly +20 s on a 220 s
suite. Cheap.

---

## What makes this bigger than 12 lines

**Expect some of the 54 to change behaviour, and treat that as the payoff, not
the problem.** Anything asserting on `net::ERR_*` strings, timing, or redirect
handling is now measuring a different network path. A test that flips is telling
you production differs from what the suite has been claiming — write down which
one, and why, before "fixing" it.

Two known interactions to check first:

- `test_egress_dns_offload.py` drives the proxy directly with a raw asyncio
  client. It does not need this change and should keep working; if it does not,
  the module-global teardown above is the likely cause.
- The four `unrenderable_content` download tests and the fence test are the most
  timing-sensitive in the suite (`flaky-fence-test-margin.md` is about the fence
  one). Run the suite three times, not once, before believing a new flake rate.

---

## What I am least sure of

- Whether the proxy can be started once per session rather than per crawl.
  Per-crawl is obviously correct and costs 0.4 s; per-session is cheaper and
  risks leaking a proxy bound to a closed loop between tests. Start with
  per-crawl.
- Whether any existing test *depends* on the direct path without saying so.
  That is exactly what the run will reveal.
