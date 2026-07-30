# Static mode: replace httpx with a browser-TLS-impersonating client

**Status:** Open — ready to implement, no external input needed
**Priority:** Medium. Not a fix for any observed incident; it hardens the path
that everything else is about to start falling back to.
**Effort:** M. **Risk:** medium — swaps the HTTP client under a path MAS
depends on. Fully offline-testable (`test-aitosoft/test_static_mode.py` exists).
**Evidence:** `tasks/waa-eval-2026-07-30-forensics.md` §2a, plus 2026-07 industry
sources cited below.

## Why now

Static mode started life as an escape hatch for hosts where Playwright hangs.
After the 2026-07-30 eval it becomes strategically important: it is the only
path that reliably returns content on the sites where full mode fails
(`maitokolmio.fi`: full mode 504 @ 180 s, static 200 @ 1.9 s), and
`tasks/static-fallback-within-fence.md` proposes making it the automatic
fallback. A path that important should not announce itself as a bot.

`aitosoft_static_mode.py` uses `httpx`. httpx's TLS ClientHello — cipher order,
extension order, ALPN, HTTP/2 SETTINGS — is a stable, well-known non-browser
JA3/JA4 fingerprint. In 2026 that check runs *before* any HTML is served:
Akamai deployed JA4 during 2026, and the standard failure signature is exactly
"works in a browser, 403 in Python". We currently send a Chrome `User-Agent`
over an unmistakably-not-Chrome handshake, which is worse than sending neither
— it is an explicit mismatch signal.

**Calibration, so this does not get oversold:** for `konecranes.com` this
changes nothing. Real Chrome, patchright and httpx all get the same 403 from
Fastly, which proves that host blocks on IP/ASN reputation, not fingerprint.
This task is insurance for the general population of Finnish SME sites behind
Cloudflare/Imperva/F5, not a konecranes fix.

## Direction

Swap `httpx.AsyncClient` for `curl_cffi`'s `AsyncSession` with
`impersonate="chrome"` (the moving alias, not a pinned version — it tracks the
current supported fingerprint automatically). curl_cffi is the Python binding
for curl-impersonate; it replicates a real browser's TLS *and* HTTP/2
fingerprint, and its async API is close enough to httpx that
`_fetch_static_one` should change very little.

Things the implementer must preserve — each exists for a reason, all of them
verified live:

| Current behaviour | Why | Check in curl_cffi |
|---|---|---|
| `verify=False` | broken-cert SME sites must crawl in static mode exactly as they do in full mode (`tasks/done/tls-broken-cert-regression-2026-07-17.md`) | `verify=False` |
| `follow_redirects=False` + manual hops | every `Location` is re-validated by `egress_broker.check_redirect` (SSRF). **Non-negotiable.** | `allow_redirects=False` |
| `STATIC_MAX_REDIRECT_HOPS = 5` | bounded chain | unchanged |
| UA mirrored from `config.yml` | static and full must not look like different clients | must now *match* the impersonated Chrome version, not config.yml's UA — a Chrome-138 UA over a Chrome-131 handshake is a fresh mismatch signal. **Resolve this deliberately.** |
| per-URL timeout from `crawler.static_fetch_timeout_s` | fast-or-fail | `timeout=` |
| module-scope client + `close_static_http_client()` in lifespan | one client per process | mirror it |
| never raises — failures become `success=false` in a 200 | 504 is reserved for "we tried to render and failed" | must survive the swap; `test_static_mode.py` pins this |

Note the UA row: it is the one real design decision here. Either drive both the
impersonation target and the UA from one constant, or drop the explicit UA and
let curl_cffi set the matching one.

Also worth checking while in there: `Accept-Language: fi,en;q=0.7` is a good
Finnish-market signal; keep it. Header *order* matters to some WAFs and
curl_cffi handles it as part of impersonation — do not re-impose a custom
header dict that destroys the ordering.

## Dependency / build considerations

- Adds a compiled dependency (`curl-cffi[asyncio]`) to the image. Check the
  wheel exists for the deploy target (linux/amd64) and note the arm64
  devcontainer caveat in TESTING.md.
- Keep httpx importable — it is used elsewhere in upstream.
- Fallback: if curl_cffi fails to import, degrade to the current httpx client
  rather than failing the module (`aitosoft_static_mode` is imported lazily by
  `api.py`; a module-level import failure surfaces as a 500 on the static path).

## Verification

- `pytest test-aitosoft/test_static_mode.py` must stay green (it pins the
  never-raises contract and the SSRF hop validation).
- Add a fingerprint check: fetch `https://tls.browserleaks.com/json` (or
  equivalent) through static mode and record the JA3/JA4 before and after in
  `test-aitosoft/reports/`. This is the only way to prove the change did what
  it claims.
- Tier 1 regression 4/4, plus one static-mode run per Tier 1 site.
- Re-measure `maitokolmio.fi` static **once** to confirm no regression on a
  known-good static host.

## Sources (2026-07)

- <https://scrapfly.io/blog/posts/ja3-ja4-tls-fingerprinting-guide-to-detection-and-evasion>
- <https://github.com/lexiforest/curl_cffi>
- <https://curl-cffi.readthedocs.io/en/latest/quick_start.html>
- <https://proxyhat.com/blog/tls-impersonation-curl-cffi-guide>
