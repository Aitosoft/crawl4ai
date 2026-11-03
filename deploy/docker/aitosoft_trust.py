"""
Aitosoft: trusted-client relaxations of the v0.9.x untrusted-config boundary.

Upstream v0.9.0 treats every network request body as untrusted and rejects
or clamps "power fields". This service is single-tenant: the only client is
MAS, authenticated with a bearer token. We relax exactly what MAS's request
contract needs and nothing else — js_code, proxies, extra_args, cookies,
cdp_url etc. all stay forbidden (defense-in-depth against a leaked token).

Lives in its own module (not aitosoft_entry.py) so tests can apply the
relaxations without importing the full server app. Applied once at import
time by aitosoft_entry; calling apply_trust_relaxations() twice is harmless.

The MAS request contract these relaxations serve is pinned by
test-aitosoft/test_mas_contract.py — run it after every upstream sync.
"""

import os

import crawl4ai.async_configs as _ac

_applied = False


def apply_trust_relaxations() -> None:
    global _applied
    if _applied:
        return
    _applied = True

    # 1. browser_config.headers — MAS sends per-company persona headers
    #    (Accept-Language, sec-ch-ua). Header values only shape outbound
    #    requests to crawl targets; they cannot execute code or reroute
    #    traffic, and egress is still pinned by the SSRF broker.
    _ac.UNTRUSTED_FORBIDDEN_FIELDS["BrowserConfig"].discard("headers")
    _ac.UNTRUSTED_FIELD_ALLOWLIST["BrowserConfig"].add("headers")

    # 2. page_timeout clamp — upstream caps it at 60s; MAS legitimately sends
    #    90s for slow SPA sites. Raise the cap to our wall-clock deadline
    #    (config.yml limits.wall_clock_s = 180s) so the per-page timeout can
    #    never exceed the request deadline anyway.
    #
    #    Through the env var since v0.9.5: upstream (a59f50e, 61eb573) replaced
    #    the `_MAX_TIMEOUT_MS` constant we used to assign with
    #    `_max_timeout_ms()`, which reads CRAWL4AI_MAX_TIMEOUT_MS on EVERY call.
    #    Our old assignment silently became an attribute nothing reads, and
    #    MAS's 90000 was clamped to 60000 (only test_mas_contract.py noticed).
    #    Per-call reading is also why setdefault here is import-order-proof.
    #    The same ceiling caps wait_for_timeout and body_visibility_timeout.
    #    Note `page_timeout: 0` now becomes 60000, not this cap: upstream
    #    treats malformed input as the default on purpose. MAS never sends 0.
    os.environ.setdefault("CRAWL4AI_MAX_TIMEOUT_MS", "180000")

    # 3. Behavioral emulation knobs — magic / simulate_user /
    #    override_navigator are anti-bot-evasion toggles, not code-execution
    #    or traffic-routing vectors. Upstream forbids them for multi-tenant
    #    safety; for our single trusted client they're legitimate tuning.
    for _f in ("magic", "simulate_user", "override_navigator"):
        _ac.UNTRUSTED_FORBIDDEN_FIELDS["CrawlerRunConfig"].discard(_f)
        _ac.UNTRUSTED_FIELD_ALLOWLIST["CrawlerRunConfig"].add(_f)

    # 4. Falsy forbidden fields are dropped, not rejected. Upstream raises 400
    #    on the PRESENCE of a forbidden field even when its value is
    #    null/false/empty (e.g. {"magic": false} — which pre-0.9 MAS/test
    #    configs sent). A falsy power-field is semantically identical to its
    #    absence, so absorbing it costs nothing security-wise. Truthy
    #    forbidden fields (js_code, proxy_config, cookies, ...) still 400.
    _upstream_filter = _ac._filter_untrusted_fields

    def _filter_untrusted_fields_tolerant(type_name, params):
        forbidden = _ac.UNTRUSTED_FORBIDDEN_FIELDS.get(type_name, set())
        pruned = {k: v for k, v in params.items() if not (k in forbidden and not v)}
        return _upstream_filter(type_name, pruned)

    _ac._filter_untrusted_fields = _filter_untrusted_fields_tolerant

    # 5. TLS: tolerate broken certificates, as this service always has.
    #    Until v0.9.2 upstream hardcoded --ignore-certificate-errors into every
    #    Chromium launch; f0ada4c (v0.9.5) removed it, and enforce_egress forces
    #    ignore_https_errors=False unless egress_broker.ALLOW_INSECURE_TLS. An
    #    expired, self-signed or wrong-host certificate would then fail as
    #    net::ERR_CERT_* -> origin_unreachable -> HTTP 200 success:false, which
    #    MAS cannot tell from a company with no website. Nobody has counted how
    #    many MAS targets that is, so verification stays off until someone does
    #    and MAS agrees (tasks/upgrade-upstream-v0.9.5.md §3.1). Static mode
    #    already uses verify=False, so the two render modes agree.
    #
    #    The module attribute, not the CRAWL4AI_ALLOW_INSECURE_TLS env var:
    #    egress_broker reads the env var once at import, and under pytest it is
    #    imported before this module (test_egress_dns_offload imports api), so
    #    an env-var default here would hold in one test run and not in another.
    #    enforce_egress and webhook.py read the attribute at call time.
    #    Pinned by test_fixture_origin.py's broken-certificate tests.
    import egress_broker

    egress_broker.ALLOW_INSECURE_TLS = True
