# All 67 fixture tests run on a network path production does not use

> **The count in this title has been 54, then 66, and is 67 as of 2026-08-09.**
> It moves whenever a route is added, so treat it as "all of them", not as a
> number to check against.

**Status:** CLOSED 2026-08-17 — **not doing it.** The gap is real and the fix does
not buy what this file claims it buys. **Read "Why this is closed" at the bottom
first**; everything above it is the 2026-08-05 argument, preserved because the
finding is correct even though the conclusion is not.
Written 2026-08-05 by the session that shipped
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

---

## Why this is closed (2026-08-17)

Sent to a devil's-advocate review during the `capacity-gate` implementation session, on the
question "is this a perfectly safe improvement?". It is not, and more importantly it does not pay.
Three findings, each verified in the code rather than argued.

### The deciding fact: the proxy's interesting half is unreachable from any fixture test

`ProductionPath`'s origin is `http://{host}:{port}` (`fixture_origin.py:1094`) — **plain HTTP, and
always up.** Plain HTTP takes the proxy's `_handle_absolute` path (`egress_proxy.py:143`).
Everything this file cites as the payoff lives on the **CONNECT** path: the 15 s connect budget,
the `_BLOCKED` reply, the DNS-rebinding control (`egress_proxy.py:111-141`). None of it executes.

And **the 134 s vs 30 s number is a dead-host measurement.** The route table
(`fixture_origin.py:55-71`) contains no unreachable target; connect always succeeds in under a
millisecond. So the claim "a test without the proxy measures the wrong number by 4×" is true of a
test we do not have and are not planning. Every timing assertion in the suite has margins the extra hop cannot
move (`test_fixture_origin.py:216`, `:240`, `:1059`) — the original file's "~0.4 s per crawl" was
an estimate, never a measurement, and nothing here rests on its value.

**Which of the 67 tests would change answer? On inspection, none.** That is the whole decision.

### The proposed fix is actively wrong, in the "start with per-crawl" advice

`PinningProxy` binds an **ephemeral port** (`egress_proxy.py:57,74-78`), `enforce_egress` writes
that URL into `proxy_config` (`egress_broker.py:205-208`), and `crawler_pool._sig` is a sha1 over
`BrowserConfig.to_dict()` (`crawler_pool.py:121-124`) — which **does** include `proxy_config`
(verified by execution: `{'server': 'http://127.0.0.1:…', …}`). A new port per crawl is therefore
a new pool signature, i.e. **a fresh Chromium per test**, destroying `production_path`'s
session-scoped single-browser design (`fixture_origin.py:1289-1291`). The cost is 67 browser
launches, not the "+20 s" this file estimates.

### It would add artefacts, not only fidelity

The fixture origin is HTTP/1.1 keep-alive (`fixture_origin.py:985`) and the proxy parses one
request line then splices raw (`egress_proxy.py:182-239`), so **every reused socket delivers an
absolute-URI request to the origin.** It survives today only because `do_GET` happens to call
`urlsplit(self.path)` (`:992`) — an accident, not a design. Plus one `asyncio.to_thread`
`getaddrinfo` per connection (18 of them for `/heavy`). A suite that becomes flaky for these
reasons costs a future session more than the gap costs anyone now.

### Also stale

`loopback_allowed()` is at **`fixture_origin.py:1164`**, not 907 — the file grew 257 lines under
it. The single-caller claim (`egress_broker.py:170` / `server.py:181-183`) is still true, and
loopback pinning does work (already asserted at `test_fixture_origin.py:120`).

### What already covers the proxy, and what would reopen this

`test_egress_dns_offload.py` drives `PinningProxy` in-process at `:127, :250, :288, :320, :438` —
off-loop resolve, absolute-URI close, SSRF 403, connect timeout, the full NXDOMAIN chain. **The
80 % version of this task already exists**, which is the "do we already have something?" question
paying out again.

**Reopen if** a fixture route ever needs to be a dead host or an `https://` origin — at that point
the CONNECT path becomes reachable and the faithfulness gap starts costing something real. If you
do, make it **session-scoped**: start once in `ProductionPath.__init__` on `self._loop`,
`set_egress_proxy(None)` in `close()` (~8 lines), and watch for pending splice tasks at
`self._loop.close()` (`:1403`) and the leaked `_EGRESS_PROXY_URL` module global, which nothing in
`test_fixture_origin.py` currently guards.
