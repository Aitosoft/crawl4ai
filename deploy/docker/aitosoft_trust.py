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
    _ac._MAX_TIMEOUT_MS = 180_000

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
