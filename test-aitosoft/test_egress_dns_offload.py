"""
The egress path — OFFLINE, no server, no browser, no customer site.

Three defects, all found 2026-08-05 while reviewing
`tasks/done/egress-proxy-blocks-the-event-loop.md`, all on the path every MAS
request takes:

1. **Every DNS resolution ran on the app's single event loop.**
   `egress_broker._resolve` is a bare blocking `socket.getaddrinfo`, and it was
   awaited nowhere — it was *called*. Under `gunicorn --workers 1
   --worker-class uvicorn.workers.UvicornWorker` that loop also serves
   `/health` (the ACA readiness **and** startup probe), the render-admission
   gate and every wall-clock fence. Measured against ACA's own resolver config
   (4 search domains + `ndots:5`, read off a live replica) with a nameserver
   that receives and never answers: **22.75 s** of frozen loop per resolve.

   The seed check is the one that matters most and the one the task file
   missed: it runs on *every* `/crawl`, and it runs **before** render
   admission, so it is not even bounded by render capacity.

2. **A lapsed domain was reported as an SSRF refusal.** NXDOMAIN and "resolved,
   but policy refused it" shared one opaque HTTP 400. A company-registry sweep
   is mostly lapsed domains.

3. **On plain `http://`, a failed connect was answered with a renderable 403**
   whose body is our own string `URL blocked` — which our own antibot detector
   then read as the customer's site blocking us.

These tests are hermetic: every resolution is monkeypatched, every socket is
loopback. Nothing here performs DNS or leaves the machine.

    pytest test-aitosoft/test_egress_dns_offload.py -q

See tasks/done/egress-proxy-blocks-the-event-loop.md.
"""

import asyncio
import os
import socket
import sys
import time

import pytest
from fastapi import HTTPException

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "docker"
    ),
)

import api  # noqa: E402
import egress_proxy  # noqa: E402
from aitosoft_failure_class import (  # noqa: E402
    ORIGIN_UNREACHABLE,
    NON_RETRYABLE_CLASSES,
    OriginUnresolvable,
    classify_exception,
    http_status_for,
)
from egress_broker import EgressBlocked, PinnedTarget  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: How long a monkeypatched "slow resolver" blocks for. Long enough that a
#: blocked loop is unambiguous, short enough to keep the suite fast.
SLOW_RESOLVE_S = 0.4


def _closed_port() -> int:
    """A port on loopback with nothing listening — connect fails instantly.

    Deliberately not a blackhole (an unaccepted backlog): the point of these
    tests is the *classification* of a failed connect, not its duration, and an
    instant refusal keeps them fast.
    """
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _heartbeat(stop: asyncio.Event, ticks: list) -> None:
    """Ticks every 10 ms for as long as the loop is actually free to run it."""
    while not stop.is_set():
        ticks.append(time.monotonic())
        await asyncio.sleep(0.01)


# ───────────────────────── 1. the loop stays free ─────────────────────────


@pytest.mark.asyncio
async def test_seed_validation_does_not_block_the_event_loop(monkeypatch):
    """The pre-admission seed check must not freeze the loop it shares.

    This is the call that fires for a dead nameserver — the proxy never sees a
    CONNECT, because the seed check raises first.
    """

    def slow_validate(url):
        time.sleep(SLOW_RESOLVE_S)

    monkeypatch.setattr(api, "validate_url_destination", slow_validate)

    stop = asyncio.Event()
    ticks: list = []
    beat = asyncio.create_task(_heartbeat(stop, ticks))
    await asyncio.sleep(0.02)  # let the heartbeat establish itself

    await api._normalize_and_validate_seeds(["https://example.test/"])

    stop.set()
    await beat

    # A blocked loop yields ~2 ticks (the ones either side of the freeze). A
    # free loop yields ~40. Assert well clear of the blocked case.
    assert len(ticks) >= 10, (
        f"event loop was blocked during seed validation: only {len(ticks)} "
        f"heartbeat ticks in {SLOW_RESOLVE_S}s"
    )


@pytest.mark.asyncio
async def test_proxy_resolves_off_the_loop(monkeypatch):
    """Two concurrent CONNECTs must resolve in parallel, not in series.

    A serialized pair is the signature of a blocking call on the loop: the
    second connection cannot even be *accepted* while the first is resolving.
    """

    def slow_resolve(url):
        time.sleep(SLOW_RESOLVE_S)
        raise EgressBlocked()  # reply and close; we only care about timing

    monkeypatch.setattr(egress_proxy, "resolve_and_pin", slow_resolve)

    proxy = egress_proxy.PinningProxy()
    await proxy.start()
    try:

        async def one():
            reader, writer = await asyncio.open_connection(
                proxy.bound_host, proxy.bound_port
            )
            writer.write(b"CONNECT example.test:443 HTTP/1.1\r\n\r\n")
            await writer.drain()
            await reader.read(4096)
            writer.close()

        started = time.monotonic()
        await asyncio.gather(one(), one())
        elapsed = time.monotonic() - started
    finally:
        await proxy.stop()

    assert elapsed < SLOW_RESOLVE_S * 1.8, (
        f"two CONNECTs took {elapsed:.2f}s for a {SLOW_RESOLVE_S}s resolve each "
        "— they serialized, so the resolve is still on the event loop"
    )


def test_resolve_is_documented_as_blocking():
    """`_resolve`'s contract is load-bearing — keep the warning next to it.

    Four call sites on the crawl path had to be found by reading; the next one
    added should not have to.
    """
    src = open(os.path.join(REPO_ROOT, "deploy", "docker", "egress_broker.py")).read()
    body = src[src.index("def _resolve(") :]
    assert "MUST offload" in body[:600]


# ──────────────── 2. a dead domain is an origin failure ────────────────


def test_unresolvable_classifies_as_origin_unreachable():
    """The class whose own comment has always claimed DNS."""
    assert (
        classify_exception(OriginUnresolvable("DNS: host does not resolve"))
        == ORIGIN_UNREACHABLE
    )
    assert http_status_for([ORIGIN_UNREACHABLE]) == 200
    assert ORIGIN_UNREACHABLE in NON_RETRYABLE_CLASSES


@pytest.mark.asyncio
async def test_nxdomain_seed_becomes_origin_unreachable(monkeypatch):
    """A lapsed domain must not reach MAS as `URL blocked (SSRF protection)`."""

    def refuse(url):
        raise HTTPException(
            status_code=400, detail="URL blocked (SSRF protection): URL blocked"
        )

    monkeypatch.setattr(api, "validate_url_destination", refuse)
    monkeypatch.setattr(api, "_host_has_no_address", lambda url: True)

    with pytest.raises(OriginUnresolvable):
        await api._normalize_and_validate_seeds(["https://lapsed.example/"])


@pytest.mark.asyncio
async def test_real_ssrf_refusal_still_returns_400(monkeypatch):
    """The security verdict is untouched: a host that RESOLVES and is refused
    keeps its opaque 400. Only "there is no address at all" is reclassified."""

    def refuse(url):
        raise HTTPException(
            status_code=400, detail="URL blocked (SSRF protection): URL blocked"
        )

    monkeypatch.setattr(api, "validate_url_destination", refuse)
    monkeypatch.setattr(api, "_host_has_no_address", lambda url: False)

    with pytest.raises(HTTPException) as exc:
        await api._normalize_and_validate_seeds(
            ["https://169.254.169.254/latest/meta-data/"]
        )
    assert exc.value.status_code == 400


def test_host_has_no_address_distinguishes_the_two_cases(monkeypatch):
    """The predicate itself, without touching a real resolver."""
    monkeypatch.setattr(
        api.socket if hasattr(api, "socket") else socket,
        "getaddrinfo",
        lambda *a, **k: (_ for _ in ()).throw(socket.gaierror()),
        raising=True,
    )
    assert api._host_has_no_address("https://lapsed.example/") is True

    monkeypatch.setattr(
        api.socket if hasattr(api, "socket") else socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))],
        raising=True,
    )
    assert api._host_has_no_address("https://resolves.example/") is False
    # No hostname at all is not a DNS failure — it must keep the 400.
    assert api._host_has_no_address("not-a-url") is False


# ──────── 3. a failed connect is not the customer blocking us ────────


@pytest.mark.asyncio
async def test_absolute_uri_connect_failure_closes_instead_of_replying(monkeypatch):
    """On plain `http://` a proxy reply is an ORDINARY RESPONSE the browser
    renders as the page. Replying 403 `URL blocked` made our own antibot
    detector report `origin_blocked` — the customer's site refusing us — and
    burned a patchright retry on it. Measured: 403 -> origin_blocked in 16.1s
    vs close -> origin_http_error in 0.5s.

    A 5xx does NOT work either: an empty body trips our own inference tier and
    the retry fires anyway. Only closing works.
    """
    dead = _closed_port()
    monkeypatch.setattr(
        egress_proxy,
        "resolve_and_pin",
        lambda url: PinnedTarget("http", "dead.example", dead, "127.0.0.1"),
    )

    proxy = egress_proxy.PinningProxy()
    await proxy.start()
    try:
        reader, writer = await asyncio.open_connection(
            proxy.bound_host, proxy.bound_port
        )
        writer.write(
            f"GET http://dead.example:{dead}/yhteystiedot HTTP/1.1\r\n"
            f"Host: dead.example:{dead}\r\n\r\n".encode()
        )
        await writer.drain()
        body = await asyncio.wait_for(reader.read(4096), timeout=5)
        writer.close()
    finally:
        await proxy.stop()

    assert body == b"", f"expected a bare close, got a renderable reply: {body!r}"
    assert b"URL blocked" not in body


@pytest.mark.asyncio
async def test_ssrf_refusal_on_the_absolute_path_still_replies_403(monkeypatch):
    """The `_BLOCKED` reply stays where it belongs — the policy branch. This is
    the difference between "we refuse to fetch this" and "we could not reach
    it", and closing on both would erase it."""

    def refuse(url):
        raise EgressBlocked()

    monkeypatch.setattr(egress_proxy, "resolve_and_pin", refuse)

    proxy = egress_proxy.PinningProxy()
    await proxy.start()
    try:
        reader, writer = await asyncio.open_connection(
            proxy.bound_host, proxy.bound_port
        )
        writer.write(
            b"GET http://internal.example/x HTTP/1.1\r\nHost: internal.example\r\n\r\n"
        )
        await writer.drain()
        body = await asyncio.wait_for(reader.read(4096), timeout=5)
        writer.close()
    finally:
        await proxy.stop()

    assert b"403" in body and b"URL blocked" in body


# ─────────────────────── the constants, pinned ───────────────────────


@pytest.mark.asyncio
async def test_connect_timeout_is_honoured(monkeypatch):
    """The connect budget is a real timer, not a decorative constant."""
    # NB: `egress_proxy.asyncio` is the global asyncio module, so a blanket
    # patch of `open_connection` also breaks this test's own client. Hang only
    # for the sentinel upstream port and delegate everything else.
    sentinel = 65123
    real_open_connection = asyncio.open_connection

    async def hang_for_sentinel(host=None, port=None, *a, **k):
        if port == sentinel:
            await asyncio.sleep(60)
        return await real_open_connection(host, port, *a, **k)

    monkeypatch.setattr(
        egress_proxy,
        "resolve_and_pin",
        lambda url: PinnedTarget("https", "slow.example", sentinel, "127.0.0.1"),
    )
    monkeypatch.setattr(asyncio, "open_connection", hang_for_sentinel)

    proxy = egress_proxy.PinningProxy(connect_timeout_s=0.2)
    await proxy.start()
    try:
        started = time.monotonic()
        reader, writer = await asyncio.open_connection(
            proxy.bound_host, proxy.bound_port
        )
        writer.write(b"CONNECT slow.example:443 HTTP/1.1\r\n\r\n")
        await writer.drain()
        # The proxy closes without replying when the upstream connect fails, so
        # read() returns b"" at the timeout rather than a body.
        await asyncio.wait_for(reader.read(4096), timeout=5)
        elapsed = time.monotonic() - started
        writer.close()
    finally:
        await proxy.stop()

    assert elapsed < 1.5, f"connect timeout did not fire: {elapsed:.2f}s"


def test_default_connect_timeout_stays_under_chromiums():
    """Chromium's own proxy-connect timer is 30 s and starts *before* ours, so
    at 30 s ours could never win and a dead host cost 30 s of a render slot per
    leg. It must stay meaningfully below that — and not so low that a
    slow-but-alive origin becomes a silent `origin_unreachable`.
    """
    assert 5.0 <= egress_proxy.PinningProxy.DEFAULT_CONNECT_TIMEOUT_S <= 20.0


def test_resolver_options_are_pinned_in_supervisord():
    """`RES_OPTIONS` is the cheapest lever we have on this whole path and it
    lives in a config file nothing else reads. Measured against ACA's real
    resolver with a dead nameserver: 22.75 s as shipped, ~4 s with this line.

    `ndots:1` also removes 4 speculative NXDOMAIN lookups per resolve on the
    HAPPY path — every name we resolve is a customer FQDN.
    """
    conf = open(os.path.join(REPO_ROOT, "deploy", "docker", "supervisord.conf")).read()
    gunicorn = conf[conf.index("[program:gunicorn]") :]
    env_line = next(ln for ln in gunicorn.splitlines() if ln.startswith("environment="))
    assert "RES_OPTIONS" in env_line
    assert "ndots:1" in env_line
    assert "timeout:2" in env_line and "attempts:2" in env_line
    # timeout:1/attempts:1 was measured at 2.00s but turns any nameserver
    # slower than 1s into a hard failure for a healthy customer domain.
    assert "timeout:1" not in env_line
