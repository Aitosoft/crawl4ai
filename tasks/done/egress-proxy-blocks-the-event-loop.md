# The egress path: blocking DNS on the single loop, and two misattributions

**Status:** DONE and **DEPLOYED 2026-08-05** as `0.9.2-egress-dns-fix`
(revision `--0000036`). Tier 1 4/4. The first deploy that day shipped a
`NameError` — see "What went wrong on deploy day".
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

- **`RES_OPTIONS` — the mechanism is now verified end to end locally, the
  effect in-container is not.** Verified: supervisor's parser reads the line
  correctly, *and* a real `supervisord` run hands its child
  `RES_OPTIONS=timeout:2 attempts:2 ndots:1` with quotes stripped (42-var
  environment, checked from `/proc/self/environ`). Not verified: glibc honouring
  it inside the ACA container. That is documented glibc behaviour and the stall
  numbers came from a faithful replay of ACA's resolver config, so the risk is
  low — but the failure mode is **silence**, since glibc ignores options it
  cannot parse and the result looks identical to success.

  **`az containerapp exec` could not settle it** and the reason is worth
  recording: it requires a TTY (`termios.error` without one), and wrapping it in
  `script` hung past 180 s. If someone needs this in future, the cheap answer is
  a boot log line printing the resolver options rather than fighting `exec`.
  Note also that the check must target the **gunicorn** process, not PID 1 —
  PID 1 is supervisord, and `RES_OPTIONS` is set on the program, not globally.
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

## What went wrong on deploy day, and it was mine

**The first deploy (`0.9.2-egress-dns`, revision `--0000035`) shipped a
`NameError` and made a dead domain a 500.**

While implementing, I added an `EgressUnresolvable(EgressBlocked)` subclass to
`egress_broker.py`, then decided against it — the distinction belongs in
`api.py`, where it does not disturb the seven endpoints sharing
`validate_url_destination`. I reverted the class **and left its `raise`
behind**. `egress_broker._resolve`'s `except socket.gaierror` branch therefore
raised `NameError`, which is neither `EgressBlocked` nor `HTTPException`, so it
fell through every handler to `classify_exception` → `render_error` → **HTTP
500**. MAS retries 500s three times. That is strictly worse than the 400 the
change existed to remove.

**What did not catch it, which is the interesting part:**

- 229 offline tests, 54 browser-driven tests, 316 upstream security tests
- a green GitHub Actions Security run on the exact commit
- `pre-commit` (black, ruff, **mypy**)
- the deploy script's own invariant check, `/health`, and the 401 auth probe

**Why:** every test in the new suite monkeypatched `resolve_and_pin` or
`validate_url_destination` — the layer *above* the broken line. The branch only
executes for a name that genuinely does not resolve, and nothing in the suite
ever resolved one. Ruff does not flag an undefined name inside an `except`
body it cannot prove reachable, and mypy was scoped past this file.

**What caught it:** the first live probe after deploy — one request for a
made-up domain, which contacts no customer. ~8 minutes of exposure, no MAS
traffic in the window (they have no sweep running).

**Fixed** in `0.9.2-egress-dns-fix`, plus two tests that patch
**`socket.getaddrinfo`** instead — the C call, the lowest level there is — so
every one of our own functions above it runs for real. Both were verified to
fail against the shipped bug. They cost 0.00 s; the version that resolved a real
non-existent name cost 10–27 s per test, and `.invalid` (the principled-looking
choice) cost **20 s per lookup** because it is not delegated at all.

**The generalisable lesson, and it is not "test more":** *if every test patches a
function, that function's own error paths are untested.* Patch the layer below
the one under test. This sits alongside the existing "a fixture can be unfaithful
on exactly the load-bearing axis" — same failure, one level down.

**The second lesson is about me, not the code:** I reverted a design decision
mid-implementation and did not re-read the diff of what I was reverting. The
repo already knows this shape — "a claim can be right about the component and
wrong about the thing that ships". Here it was right about the design and wrong
about the file.

---

## Deploy — done 2026-08-05

**Deployed:** `0.9.2-egress-dns-fix`, revision `--0000036`, digest from ACR run
`cb13`. Superseded `0.9.2-egress-dns` / `--0000035`, which lasted ~8 minutes and
is the incident above. Previous good image was `0.9.2-collapse-recovery` /
`--0000034`.

MAS was told, not asked: the message announces the change as live and explains
why we did not hold it — the alternative was landing a reclassification between
two segments of a running sweep.
`tmp/mas-repo-messages/16-to-mas-a-dead-domain-was-never-an-ssrf-refusal.md` §0.

**Verification, in the order it was run:**

| check | result |
|---|---|
| render-capacity invariant (`deploy-image.sh`) | `render_capacity=2` == `http-renders` rule ✅ |
| revision `Running` at 100 % **before** any crawl (2026-07-30 lesson) | ✅ `--0000035` Deprovisioning |
| `/health` | 200 in 0.20 s ✅ |
| unauthenticated `POST /crawl` | 401 ✅ |
| **the contract change** — a lapsed domain | **HTTP 200, `success:false`, `failure_class: origin_unreachable`, `error_message: "DNS: host does not resolve"`, 0.23 s** ✅ |
| **the security boundary** — `169.254.169.254` and `127.0.0.1:8080` | both still **400** `URL blocked (SSRF protection)` ✅ |
| Tier 1 regression | **4/4** ✅ |
| production logs, 30 min | zero 500s, zero `RENDER DEFECT`, zero `COLLAPSE RECOVERED`; one `ORIGIN FAILURE` line — the probe above ✅ |

The lapsed-domain probe is worth keeping as a habit: **it verifies the whole
egress path and contacts no third party**, because the name does not resolve.
It is the cheapest production check we have, and it is the one that caught the
`NameError`.

**Still to watch, once MAS's first segment runs:** `origin_unreachable` should
*rise* against pre-2026-08-05 baselines. That is the reclassification, not a
regression. Query it per segment alongside `RESULT FAILURE` by class.
