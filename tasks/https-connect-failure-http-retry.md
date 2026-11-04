# One marked `http://` attempt when an `https://` URL fails at connect

**Status:** open, not started. Opened 2026-11-04 by the optimisation-loop session (lever 10 in
`optimization-experiments.md`). **MAS asked for it** (`tmp/mas-repo-messages/115-from-us-…` §3), on
two conditions: the result is marked, and the field name gets their ack. It ships in its own window.
**Size:** S–M. A small change in our layer, plus a fixture route. The care goes into the contract
and the budget.

## The problem, with its evidence

Some company sites serve only plain http, and their port 443 refuses connections or has nothing
behind it. MAS's agent normally asks for `https://`. Our egress proxy's CONNECT then fails, Chrome
reports `net::ERR_TUNNEL_CONNECTION_FAILED`, and we return `origin_unreachable` at HTTP 200. That
class is terminal and correct as far as it goes. But the company's site is alive on http, and
nobody tries it.

- **MAS's archive** (`115-from-us-…` §2, prod `capture_attempts` against `scraped_pages`, read-only,
  2026-11-04): 432 companies ended with every capture attempt `origin_unreachable` and nothing
  stored. 408 of them were tried on https only, and **137 of those failed at the tunnel**. The rest
  were DNS failures, which no http retry can help. Only 24 of the 432 were ever tried on `http://`.
  So ≈137 companies (~0.5 % of the 28,636 that stored anything) are the candidates. Some will be
  dead hosts, not http-only ones.
- **A live example** (window 1, 2026-11-04): `steel-air.fi`, `orivedenliikenne.fi` and `oribus.fi`
  all resolve to 77.240.23.85, and all three failed `https://` at the tunnel. The agent tried
  `http://steel-air.fi` only once its https failed, and that loads since `0.9.5-https-first`. The
  other two were never tried on http. Counting on our side: `ContainerAppConsoleLogs_CL`,
  `RESULT FAILURE` lines with `ERR_TUNNEL_CONNECTION_FAILED`, 13:09–13:36Z.
- **Not every tunnel failure is a closed 443.** `selosella.fi` failed the same way because our
  pinning proxy dials only the first DNS answer, and that host has a stray A record
  (`egress_broker.resolve_and_pin`; `optimization-experiments.md` lever 11). An http retry would hit
  the same stray address and fail too, so it's harmless there, but it isn't the fix for that case.

## What MAS needs (their words, `115-from-us-…` §3)

"If you retry, report it in the response (final_url on http:// is enough), so our side never
mistakes an http answer for an https one. We rejected a silent client-side fallback in August for
exactly that reason." So: never silent. The result says it was fetched over http, in a field MAS
names and acks.

## Design space

1. **Where.** In our layer, after the result is classified: `origin_unreachable` whose error
   carries a connect-level code, on an `https://` URL, in full render mode. Candidates:
   `api.handle_crawl_request`, after `classify_result`, or a small `aitosoft_*` module it calls,
   like the patchright tier. Not in `crawl4ai/` (Principle 1), and not in the egress proxy. The
   proxy sees the CONNECT fail but has no say over the navigation.
2. **Which errors.** Start narrow: `ERR_TUNNEL_CONNECTION_FAILED` and `ERR_CONNECTION_REFUSED`.
   Measure before widening to `ERR_SSL_*` (enjo.fi's `ERR_SSL_UNRECOGNIZED_NAME_ALERT` in window 3 is
   the likeliest next member) or `ERR_CONNECTION_TIMED_OUT`, which is expensive to wait on twice.
   Never on DNS failures; the seed check returns those before render.
3. **Budget.** One attempt, inside the same admission slot and the same wall-clock fence (180 s). A
   tunnel failure costs ~0.5 s, so the retry is nearly free when http is dead too.
4. **The marker.** A result-level field, for example `fetched_over_http_after_https_failed: true`
   (name to be agreed with MAS), plus the honest `url`/`redirected_url`. **Contract rule:** this changes
   what MAS receives, so it waits for their ack.
5. **What comes back on double failure:** the original https failure. That's the URL they asked
   for, and changing the class there helps nobody.
6. **Interaction with `HttpsUpgrades` off** (`0.9.5-http-as-asked`, deployed between windows 4 and
   5): the retry's `http://` stays http. Without that change, Chrome would upgrade the retry straight
   back to the https that just failed.

## How to verify

- **Fixture origin:** the `--host-resolver-rules` trick from
  `test_an_http_only_public_site_renders`, with :443 pointing at a closed port, a seed of
  `https://name/ok`, and an expected success with the marker and `http://` in the final URL. A
  control: with the retry disabled, the same seed is `origin_unreachable`.
- **Production, one window:** MAS's readout already joins by URL. Count the marker's successes and
  the `origin_unreachable` count before and after. The candidate pool predicts ~0.5 % of companies,
  so at 75 companies a window expect 0–2. A repeat window, or MAS's archive replay, decides the
  size.

## What I talked myself out of

- **MAS's agent retrying http itself.** They rejected it: their agent sees only a failed page and
  would be guessing. We see the transport fact.
- **Retrying on every `origin_unreachable`.** Most are DNS failures (271 of 408), where http can't
  help.
- **Folding it into the patchright tier.** That tier is for blocks, and it relaunches a different
  browser. This retry is a different URL in the same browser.

## What I'm least sure of

1. That a tunnel failure means "443 closed" often enough to be worth a second navigation. The 137
   includes dead hosts. The fixture proves the mechanism, and only a production window proves the
   yield.
2. The parked egress-proxy idle-socket 400 on plain-http (`tasks/README.md` §Parked). More
   plain-http traffic makes it likelier to show. Count `origin_http_error` 400s on `http://` URLs
   in the window after shipping.
3. Whether `ERR_SSL_*` belongs in the first version. Sites with a broken TLS stack and a working
   http exist (enjo.fi may be one), but a TLS failure is less clearly "nothing on 443".
