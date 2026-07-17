"""
Static-mode hardening tests — OFFLINE, no server, no network.

Pins the SSRF/robustness contract of aitosoft_static_mode.py (see
tasks/done/static-mode-hardening-*.md):

  * redirects are followed manually and every Location is re-validated with
    egress_broker.check_redirect — a public page redirecting to a private or
    link-local target (Azure IMDS) is refused, never fetched;
  * a refused redirect is an inner success=false result with an OPAQUE
    error_message (no target echo), consistent with static mode's
    "one bad URL never fails the whole request" semantics;
  * public→public redirects (absolute and relative Location) still work;
  * more than STATIC_MAX_REDIRECT_HOPS hops → refused;
  * per-batch fan-out is bounded by STATIC_FETCH_MAX_CONCURRENCY;
  * the api.py static branch records the real aggregate outcome to the
    monitor (non-200 when every URL failed), not an unconditional 200;
  * the shared client is built redirect-unsafe (follow_redirects=False) and
    the fetch timeout comes from config.yml crawler.static_fetch_timeout_s.

All target hosts are IP literals so egress_broker's getaddrinfo resolves
locally — no DNS, no sockets (httpx.MockTransport intercepts everything).

    pytest test-aitosoft/test_static_mode.py -q
"""

import asyncio
import os
import sys

import httpx

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "docker"
    ),
)

import aitosoft_static_mode as asm  # noqa: E402

PUBLIC_A = "http://8.8.8.8"  # global -> allowed by egress_broker
PUBLIC_B = "http://1.1.1.1"  # global -> allowed by egress_broker
PRIVATE = "http://10.0.0.1/"  # RFC1918 -> blocked
IMDS = "http://169.254.169.254/metadata/instance"  # link-local -> blocked

HTML_OK = "<html><body><h1>Hello</h1><p>Contact: a@b.fi</p></body></html>"


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _install_mock_client(handler) -> httpx.AsyncClient:
    """Inject a MockTransport client as the module singleton. Built with the
    same redirect posture as production (follow_redirects=False) so the
    manual-loop code path under test is the real one."""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    asm._static_http_client = client
    return client


async def _reset_client():
    await asm.close_static_http_client()  # clears the singleton + closes


# ---------------------------------------------------------------- redirects


def test_redirect_public_to_private_is_refused():
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": PRIVATE})

    async def main():
        _install_mock_client(handler)
        try:
            result = await asm._fetch_static_one(f"{PUBLIC_A}/start")
        finally:
            await _reset_client()
        assert result["success"] is False
        assert result["error_message"] == (
            "static-fetch: redirect blocked (SSRF protection)"
        )
        # Opaque: the blocked target must not leak into the API response.
        assert "10.0.0.1" not in result["error_message"]
        # The private target was never fetched.
        assert requested == [f"{PUBLIC_A}/start"]

    run(main())


def test_redirect_to_imds_is_refused():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"location": IMDS})

    async def main():
        _install_mock_client(handler)
        try:
            result = await asm._fetch_static_one(f"{PUBLIC_A}/")
        finally:
            await _reset_client()
        assert result["success"] is False
        assert "redirect blocked (SSRF protection)" in result["error_message"]

    run(main())


def test_redirect_public_to_public_is_followed():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "8.8.8.8":
            return httpx.Response(302, headers={"location": f"{PUBLIC_B}/final"})
        return httpx.Response(200, text=HTML_OK, headers={"content-type": "text/html"})

    async def main():
        _install_mock_client(handler)
        try:
            result = await asm._fetch_static_one(f"{PUBLIC_A}/start")
        finally:
            await _reset_client()
        assert result["success"] is True
        assert result["status_code"] == 200
        assert result["url"] == f"{PUBLIC_B}/final"
        assert "Hello" in result["markdown"]["raw_markdown"]

    run(main())


def test_relative_location_resolves_against_current_url():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, text=HTML_OK, headers={"content-type": "text/html"})

    async def main():
        _install_mock_client(handler)
        try:
            result = await asm._fetch_static_one(f"{PUBLIC_A}/start")
        finally:
            await _reset_client()
        assert result["success"] is True
        assert result["url"] == f"{PUBLIC_A}/final"

    run(main())


def test_more_than_max_hops_is_refused():
    count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        count["n"] += 1
        return httpx.Response(302, headers={"location": f"{PUBLIC_A}/{count['n']}"})

    async def main():
        _install_mock_client(handler)
        try:
            result = await asm._fetch_static_one(f"{PUBLIC_A}/start")
        finally:
            await _reset_client()
        assert result["success"] is False
        assert "too many redirects" in result["error_message"]
        # Initial request + STATIC_MAX_REDIRECT_HOPS follows, then refuse.
        assert count["n"] == 1 + asm.STATIC_MAX_REDIRECT_HOPS

    run(main())


# ------------------------------------------------------------- concurrency


def test_batch_fanout_is_bounded_by_semaphore():
    state = {"in_flight": 0, "peak": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        state["in_flight"] += 1
        state["peak"] = max(state["peak"], state["in_flight"])
        await asyncio.sleep(0.02)
        state["in_flight"] -= 1
        return httpx.Response(200, text=HTML_OK, headers={"content-type": "text/html"})

    async def main():
        _install_mock_client(handler)
        try:
            urls = [f"{PUBLIC_A}/page{i}" for i in range(30)]
            envelope = await asm.handle_static_crawl_request(urls=urls)
        finally:
            await _reset_client()
        assert len(envelope["results"]) == 30
        assert all(r["success"] for r in envelope["results"])
        assert state["peak"] <= asm.STATIC_FETCH_MAX_CONCURRENCY
        assert state["peak"] >= 2  # it did actually run concurrently

    run(main())


# ------------------------------------------------- monitor aggregate outcome


class _FakeMonitor:
    def __init__(self):
        self.ended = []

    async def track_request_start(self, *args, **kwargs):
        pass

    async def track_request_end(
        self, request_id, success, error=None, pool_hit=True, status_code=200
    ):
        self.ended.append(
            {"success": success, "error": error, "status_code": status_code}
        )


def _patched_monitor():
    import monitor

    fake = _FakeMonitor()
    original = monitor.get_monitor
    monitor.get_monitor = lambda: fake
    return fake, (monitor, original)


def _restore_monitor(token):
    module, original = token
    module.get_monitor = original


def test_all_urls_fail_records_non_200_monitor_outcome():
    """api.handle_crawl_request's static branch must record the real
    aggregate outcome — an all-failed batch is not a 200 success, even
    though the HTTP envelope stays 200 by contract."""
    import api

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async def main():
        fake, token = _patched_monitor()
        _install_mock_client(handler)
        try:
            envelope = await api.handle_crawl_request(
                urls=[f"{PUBLIC_A}/a", f"{PUBLIC_B}/b"],
                browser_config={},
                crawler_config={},
                config={},
                render_mode="static",
            )
        finally:
            await _reset_client()
            _restore_monitor(token)
        # Envelope contract unchanged: HTTP-level success, inner failures.
        assert envelope["success"] is True
        assert all(r["success"] is False for r in envelope["results"])
        # Monitor got the truth.
        assert len(fake.ended) == 1
        assert fake.ended[0]["success"] is False
        assert fake.ended[0]["status_code"] != 200

    run(main())


def test_partial_success_still_records_200():
    import api

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "8.8.8.8":
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, text=HTML_OK, headers={"content-type": "text/html"})

    async def main():
        fake, token = _patched_monitor()
        _install_mock_client(handler)
        try:
            await api.handle_crawl_request(
                urls=[f"{PUBLIC_A}/a", f"{PUBLIC_B}/b"],
                browser_config={},
                crawler_config={},
                config={},
                render_mode="static",
            )
        finally:
            await _reset_client()
            _restore_monitor(token)
        assert fake.ended == [{"success": True, "error": None, "status_code": 200}]

    run(main())


# ------------------------------------------------------- client construction


def test_prod_client_never_autofollows_redirects():
    """The singleton client must be built with follow_redirects=False —
    auto-following would bypass the per-hop SSRF validation entirely."""

    async def main():
        await _reset_client()  # ensure we build a fresh real client
        client = await asm._get_static_http_client()
        try:
            assert client.follow_redirects is False
        finally:
            await _reset_client()

    run(main())


def test_fetch_timeout_reads_config_yml():
    import utils

    # Wiring: the knob is read from crawler.static_fetch_timeout_s.
    original = utils.load_config
    utils.load_config = lambda: {"crawler": {"static_fetch_timeout_s": 7}}
    asm._static_fetch_timeout_cached = None
    try:
        assert asm._get_static_fetch_timeout_s() == 7.0
    finally:
        utils.load_config = original
        asm._static_fetch_timeout_cached = None

    # Real config.yml carries the deployed value.
    assert asm._get_static_fetch_timeout_s() == 15.0
    asm._static_fetch_timeout_cached = None
