# The egress path: blocking DNS on the single loop, and two misattributions

**Status:** DONE 2026-08-05. Code, tests and docs shipped to `main`.
**Not yet deployed** — see "Deploy" at the bottom; one change is a wire-status
change and this repo's own rule is that behaviour changes wait for the relay.
**Size:** planned S, delivered S. Six files, ~60 lines of behaviour.

Planned by the 2026-08-05 research session, implemented the same day by a
separate session after three parallel reviews (upstream prior-art, fresh-eyes
simplicity, claim verification). **The reviews changed the work substantially**
— what shipped is not what the file proposed, and the differences are recorded
here rather than smoothed over.

---

## What shipped

| # | Change | File |
|---|---|---|
| 1 | Seed SSRF check moved off the event loop, and a dead domain now reports `origin_unreachable` at HTTP 200 instead of an SSRF 400 | `api.py` |
| 2 | Both proxy resolves moved off the event loop | `egress_proxy.py` |
| 3 | Static-mode redirect check moved off the event loop | `aitosoft_static_mode.py` |
| 4 | `RES_OPTIONS="timeout:2 attempts:2 ndots:1"` | `supervisord.conf` |
| 5 | Upstream connect budget 30 s → 15 s, as a class constant + ctor arg | `egress_proxy.py` |
| 6 | On the `http://` path a failed connect **closes** instead of replying with a renderable 403 | `egress_proxy.py` |
| 7 | `OriginUnresolvable` + its mapping to `ORIGIN_UNREACHABLE` | `aitosoft_failure_class.py` |

Tests: `test-aitosoft/test_egress_dns_offload.py`, 12 hermetic tests, 2.5 s, no
network and no browser. **Verified against the pre-change code**: the three
behavioural tests fail on it and pass after, which is the only evidence that a
regression test is worth having.

Gates: 229 offline + 54 browser-driven fixture tests + **316 upstream security
tests** all green.

---

## What the task file got wrong

Seven consecutive sessions had found the previous session's file materially
wrong about something load-bearing. This is the eighth, and it is the largest
count so far — but note the shape: **every error was in the file's framing and
sizing, and none in its core claim.** Item 1's mechanism was real and correctly
diagnosed from source.

1. **"a file we own outright. No upstream patch, no merge cost" — false, and it
   was the first line.** `egress_proxy.py` and `egress_broker.py` are
   **byte-identical to `upstream/develop`**, introduced by upstream commit
   `60886d1` (unclecode's 0.9.0 secure-by-default hardening). Compounding it:
   upstream ships 37 tests over these files, and `.github/workflows/security.yml`
   runs `pytest deploy/docker/tests/test_security_*.py` on push to `main`
   filtered on `deploy/docker/**` — a **live CI gate** on our fork, with 12
   successful runs behind it. So there is both a merge cost and a gate, and the
   file asserted neither existed. It is also a fifth upstream PR candidate.
2. **"Three changes, all in `egress_proxy.py`" — the dominant call site is in
   `api.py`.** `_normalize_and_validate_seeds` → `validate_url_destination` →
   the same blocking `getaddrinfo`, on **every** `/crawl`, and — this is the
   part that matters — **before the RenderGate acquire**, so it is not bounded
   by render capacity at all. For a host whose nameserver does not answer, this
   is the call that stalls: the proxy never sees a CONNECT because the seed
   check raises first. Fixing only the proxy would have left the headline
   scenario fully intact.
3. **"This is the whole change" understated the surface.** At least ten on-loop
   call sites funnel into `egress_broker._resolve`, none in a thread. The four
   on MAS's path are fixed; the rest (`webhook.py`, `job.py`, `/execute_js`, the
   LLM and screenshot routes) are named in "Deliberately not done".
4. **The stall estimate ("~5 s or ~20 s") guessed the wrong environment.** A
   reviewer read the running replica's resolver config:
   `options ndots:5` plus **four** search domains. Replayed exactly against a
   nameserver that receives and never answers: **22.75 s per `getaddrinfo`, 8
   UDP queries** — against 12.74 s for this devcontainer's single-nameserver
   config. Date and *locate* the environment, not just the number.
5. **The executor size was wrong twice over.** Not `min(32, cpu+4)` ≈ 6:
   `os.cpu_count()` reports the **host node's** CPUs, not the cgroup limit, and
   Python 3.12 (`Dockerfile:1`) has no `os.process_cpu_count()`. Measured inside
   the replica: 4 → **8 threads**. The conclusion ("blocking the pool beats
   blocking the loop") survives and gets stronger, but see #6.
6. **`asyncio.to_thread` relocates the stall; it does not bound it.** The
   executor queue is unbounded and FIFO, so healthy resolves queue behind dead
   ones — and **cancelling the request does not reclaim the thread**, which
   parks in `getaddrinfo` for the full timeout. With 2 concurrent renders ×
   10–40 uncached resolves per page, 8 slots saturate on *healthy* traffic
   routinely; that is harmless at 5 ms and fatal at 22.75 s. This is why item 4
   (`RES_OPTIONS`) is not optional garnish — **it is what bounds the queue
   `to_thread` creates**, and the two only work together.
7. **"lower both literals" — there are five `timeout=30` in the file.** Only
   `:105`/`:134` are the upstream connect; `:68`/`:153`/`:163` are client-side
   readlines against Chromium over loopback. A `sed` would have swept all five
   and silently changed client-read semantics.
8. **Item 3 was framed as a timeout problem; it is a dead-domain problem.**
   `_BLOCKED` is *also* the reply when `resolve_and_pin` raises — i.e. on
   NXDOMAIN — so on `http://` the misattribution fired on **every** dead host
   immediately, not only on the ones that black-hole SYNs for 30 s. Item 2's
   fix reduces its cost ~3× but cannot close it.
9. **`loop.getaddrinfo` is not the equivalent the file offered.** Through
   `egress_broker` it forces `async def`, which breaks 12+ upstream tests, and
   it is not a drop-in for `resolve_and_pin` (which also does the scheme check,
   the blocked-hostname set, the `is_global` sweep and the pinning). The upstream
   tests monkeypatch `egress_proxy.resolve_and_pin` with a **synchronous**
   callable, so `await asyncio.to_thread(resolve_and_pin, …)` referencing the
   module global is the *only* test-safe shape.
10. **The arithmetic conflated two populations.** "Dead domain" splits into
    NXDOMAIN — **0.09 s, HTTP 400, no render slot, never reached the gate** —
    and resolves-but-refuses-TCP, which is the 60 s case. Registry data is mostly
    the first. The 39 %/57 % render-time figures are upper bounds on a
    population smaller than the file assumed.

---

## The thing the file did not contain at all

**A lapsed domain reached MAS as `URL blocked (SSRF protection)`, HTTP 400, with
no `failure_class`.** `egress_broker._resolve` maps `socket.gaierror` onto the
same `EgressBlocked` as a policy refusal (`:95`), `utils.py:366` turns that into
a 400, and `api.py`'s `except HTTPException: raise` passes it through
deliberately. Confirmed by running it: 0.078 s, terminal.

It is cheap — no render slot — so this is a **labelling** defect, not a cost one.
But:

- It is the `norex.com` inversion exactly: our own policy string blaming a
  customer's domain, which CLAUDE.md already records as a lesson.
- It violates our own rule that origin failures are 200 + `success:false` +
  a class, and `ORIGIN_UNREACHABLE`'s own comment has always read
  *"DNS / TCP / TLS never got there"*.
- A company-registry sweep is **mostly** lapsed domains. MAS is building a
  per-page record right now; without this, several hundred to a couple of
  thousand companies would be filed as "SSRF blocked".

Fixed in `api.py` alone, deliberately: `validate_url_destination` is shared by
seven other endpoints whose opaque 400 is correct for them, and
`validate_webhook_url` funnels into `except ValueError` handlers in `job.py:80`
and `server.py:830` that would have turned into 500s. So the failure path — and
only the failure path — re-asks whether the host has any address at all. One
extra fast resolve on a request that is already failing; the happy path still
resolves exactly once.

The streaming handler keeps the 400 (`api.py`), because it must raise before the
response body starts and has no 200-envelope machinery. MAS never streams.

---

## Measurements worth keeping

Dead nameserver, ACA's exact resolver config, local UDP sink:

| resolver options | stall | UDP queries |
|---|---:|---:|
| ACA as shipped (`ndots:5`, 4 search domains) | **22.75 s** | 8 |
| `timeout:2 attempts:2 ndots:1` (shipped) | ~4 s | 4 |
| `timeout:1 attempts:1 ndots:1` | 2.00 s | 4 |

`timeout:1 attempts:1` was rejected: any authoritative nameserver slower than
1 s becomes `gaierror` → `EgressBlocked` → a hard failure for a **healthy**
customer domain. `ndots:1` is the free part — every name we resolve is a
customer FQDN, so 4 speculative NXDOMAIN lookups per resolve were pure waste, on
the happy path too, at 10–40 resolves per page render.

The `http://` connect-failure reply, real Chromium against a closed local port:

| proxy reply | class | status | elapsed | patchright retry? |
|---|---|---|---:|---|
| `_BLOCKED` 403 (before) | `origin_blocked` | 403 | 16.1 s | **yes** |
| `502` / `504` + empty body | `origin_http_error` | 502/504 | 13–15 s | **yes** |
| **close, write nothing** (shipped) | `origin_http_error` | None | **0.5 s** | no |

The obvious fix — answer with a 5xx — **does not work**: an empty body trips our
own inference tier (`minimal_text, no_content_elements`) and the retry fires
anyway. Only closing works. The `https://` CONNECT path was already correct:
Chromium turns a non-200 reply to a CONNECT into `ERR_TUNNEL_CONNECTION_FAILED`
and never renders it, so it classifies as `origin_unreachable` — which is why
`_BLOCKED` stays on the policy branch and on the CONNECT path.

Item 2's original bench (30 s Chromium proxy-connect binds; ours pre-empts it
linearly; 134 s with no proxy at all) was independently corroborated — a
reviewer reproduced `ERR_TUNNEL_CONNECTION_FAILED` by the same mechanism. It
stands.

---

## Deliberately not done

- **The other six on-loop `resolve_and_pin` call sites** (`webhook.py:157,175`,
  `job.py:79,124`, `api.py:144,260,359,550`, `server.py:465,823`). None is on
  MAS's path; each one costs upstream divergence. If any becomes hot, the fix is
  the same one line.
- **A DNS cache.** There is none anywhere in our path — Chromium's is bypassed
  by construction — so a page render performs 10–40 uncached resolves. `ndots:1`
  already removed 80 % of the queries; a cache is the next lever if DNS ever
  shows up in a profile, and it would need a think about pin freshness.
- **Bounding `to_thread` with `wait_for`.** It would bound the *caller*, not the
  thread, so it does not solve #6 — `RES_OPTIONS` does.
- **A `blackhole()` fixture helper.** The file called for one; none of the three
  items needed it. A closed local port reproduces item 3 instantly, and
  upstream's own `test_security_egress_proxy.py` is already the harness for
  items 1 and 2.
- **Promoting the connect timeout to `config.yml`.** One consumer, and
  `config.yml` ships inside the image anyway, so there is no operational
  benefit — a class constant with a constructor argument is the testable seam.
- **Wiring the `PinningProxy` into `ProductionPath`.** Real, and bigger than it
  looks — see `tasks/fixture-origin-bypasses-the-pinning-proxy.md`.

---

## What I am least sure of

- **`RES_OPTIONS` is the one change that cannot be fully tested from here.**
  The quoting *is* verified — supervisor's own parser
  (`supervisor.datatypes.dict_of_key_value_pairs`) reads the line as
  `{'PYTHONUNBUFFERED': '1', 'RES_OPTIONS': 'timeout:2 attempts:2 ndots:1'}`,
  quotes stripped. What is not verified is glibc honouring it *in the ACA
  container*; the stall measurement was a faithful replay of ACA's resolver
  config, not the container itself. The failure mode is **silence** — glibc
  ignores options it cannot parse and we simply keep the old behaviour, which
  looks identical to success. **First thing to check after deploy:**
  `az containerapp exec … --command "cat /proc/1/environ"`.
- **`ndots:1` assumes nothing in the container resolves a short name.** Redis is
  `localhost` via `/etc/hosts` and every outbound name is a customer FQDN, so
  this should be safe — but it is an assumption about the whole container, not
  just our code.
- **15 s vs 10 s for the connect budget was a judgement call, not a
  measurement.** The residual risk is an origin whose handshake completes
  between our timer and Chromium's 30 s: it becomes `origin_unreachable` at
  200 — a silently dropped page. 15 s keeps 3× more headroom than 10 s for 5 s
  more per dead leg. If a sweep shows `origin_unreachable` above the ~8 %
  MAS measured, suspect this constant first.
- **The NXDOMAIN reclassification is a small DNS oracle** — a caller can now
  distinguish "does not resolve" (200) from "resolved and refused" (400). That
  is acceptable *only* because this API is fail-closed behind a token with one
  trusted consumer. It must not be ported upstream as-is.
- **Item 3's remaining population is still unknown.** After the NXDOMAIN fix it
  needs an `http://` seed **and** a host that resolves but refuses TCP. The
  question is in the MAS reply; the fix shipped anyway because it is one line
  and strictly better.

---

## Deploy

**Not deployed as of 2026-08-05.** `main` is ahead of production.

The hold is deliberate and follows this repo's own rule (`tasks/README.md`,
"How to run this exchange"): *additive changes ship and get announced; behaviour
changes wait for the relay.* Six of the seven changes are invisible to MAS. The
seventh moves a class from HTTP 400 to HTTP 200, and "one class, two wire
statuses" is the exact defect that cost both repos weeks in July — so MAS gets
told before it lands, not after.

`tasks/mas-reply-owed-message-16.md` carries the announcement in its first
section, including the ask for a go-ahead.

**Sequence:**

1. Relay the MAS message; get the one-line ack on the 400 → 200 change.
2. `./azure-deployment/deploy-image.sh <tag>` — suggested tag `0.9.2-egress-dns`.
3. Tier 1 regression 4/4 (`test_regression.py --tier 1 --version egress-dns`).
4. **Confirm `RES_OPTIONS` actually arrived** —
   `az containerapp exec … --command "cat /proc/1/environ"`. Its failure mode is
   silence, so nothing else will tell you.
5. First `RESULT FAILURE` query after the sweep's segment 1: watch
   `origin_unreachable` **rise**. That is the reclassification landing, not a
   regression — the same URLs were 400s before and were not in that class at all.

If the sweep starts before the ack lands, deploying is still the better of the
two risks: both statuses are terminal and non-retryable for MAS, and the
un-deployed state is the one that freezes a replica on a dead nameserver. That
is a judgement for whoever is holding the relay, not a rule.
