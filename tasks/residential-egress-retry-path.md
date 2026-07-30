# Residential/ISP egress on the retry path (reputation-blocked hosts)

**Status:** Open — approved in principle by Tero 2026-07-30 (build the task;
provider choice and spend authorisation still to come). **Do not sign a
contract or commit credentials without Tero's explicit go-ahead.**
**Priority:** Medium. It is the only thing that makes konecranes-class hosts
crawlable at all, but it affects a minority of hosts and every other task in
this batch is a correctness defect that costs us more.
**Effort:** M-L. **Risk:** medium-high — money, credentials, and a change to
the egress path that carries our SSRF guarantee.
**Evidence:** `tasks/waa-eval-2026-07-30-forensics.md` §0, §2a

## Why this and nothing else works

`www.konecranes.com` returns a Fastly/Varnish 403 to **all three** of our
engines — plain httpx, real Chrome + playwright-stealth, and patchright's
undetected-chromium — with byte-identical results. Two different browser
engines cannot agree unless the decision is made before fingerprinting matters.
It is IP/ASN reputation. Our egress is `172.199.49.233`, an Azure West Europe
address in a shared SNAT pool (the environment has no VNet integration).

Therefore: no stealth work, no TLS impersonation, no header shaping and no
Azure-region move changes anything for this class of host. Only a non-datacentre
egress does.

## Design: retry-path only, static-first

This is the whole cost argument, so do not widen it casually.

- **Trigger only after a confirmed block.** First-tier stealth render runs on
  our normal egress as today. Residential is a *third* tier, after
  `blocked-host-retry-economy`'s classifier says "reputation block".
- **Static mode first.** HTML only, no assets. ~150 KB/page against ~2 MB for a
  full render — a 13× cost difference on a metered-by-gigabyte product.
- **Full render over residential only if static-over-residential proves
  insufficient**, and only as a follow-up decision with fresh numbers.

Cost shape at these constraints, for a 15,000-company sweep (~120,000 fetches,
2–5 % reputation-blocked ⇒ ~6,000 retried pages):

| Shape | Volume | 2026 market rate | Cost/sweep |
|---|---|---|---|
| retry-only, static | ~0.9 GB | $1.40–6/GB | **$5–10** |
| retry-only, full render | ~12 GB | same | $65–100 |
| everything residential | ~240 GB | same | $1,300+ — never do this |

Market tiers observed 2026-07: budget ~$1.40–1.75/GB (IPRoyal, Webshare at
volume), mid ~$3–6/GB (Decodo ~$5.50/GB at 10 GB), enterprise $8–12/GB
(Bright Data $8/GB PAYG, Oxylabs from ~$2.50/GB at volume). Re-price before
buying; this moves.

## The hard part: egress broker interaction

`deploy/docker/egress_broker.py` is the single rule for all outbound traffic and
it deliberately fights exactly what this task adds:

- `enforce_egress()` strips any `proxy` / `proxy_config` off the browser config
  and *forces* the localhost pinning proxy, so Chromium never resolves target
  hosts itself (DNS-rebinding control).
- `resolve_and_pin()` resolves once and hands back the exact IP to dial;
  re-resolving at connect time is the hole it closes.
- `--proxy-server` and friends are scrubbed from Chromium launch args.

Routing through an external proxy means **the proxy does the DNS resolution**,
so our pinning is structurally bypassed on that path. Think this through
properly rather than disabling the guard:

- The SSRF threat model here **improves in one dimension and changes in
  another.** A third-party residential proxy sits outside our network entirely,
  so a malicious redirect cannot reach our IMDS (`169.254.169.254`), our
  localhost services, or anything else in our address space via that path. It
  could in principle reach the *provider's* internals; reputable providers block
  that, and it is their perimeter, not ours.
- Keep validating every hop **on our side anyway**: run `resolve_and_pin` /
  `check_redirect` on each `Location` before handing the URL to the proxy. It no
  longer guarantees what is dialled, but it still refuses obviously-internal
  targets and keeps the audit trail honest. Document clearly in the code that
  the guarantee is weaker on this path and why that is acceptable.
- Add the residential path as an explicit, named exception inside
  `egress_broker`, not as a bypass sprinkled at the call site. One rule, one
  place — that is the whole point of that module.

## Credentials

**PUBLIC REPOSITORY.** Proxy username/password/endpoint go in env vars sourced
from Azure Key Vault, exactly like `CRAWL4AI_API_TOKEN`. Never in `config.yml`
(it is committed), never in a task file, never in a log line. Add the credential
shape to the pre-commit secret pattern in CLAUDE.md if it is distinguishable.

Deploy note: setting a new env var means `az containerapp update --set-env-vars`,
which is the operation that has broken MAS's token before. Read
`DEPLOYMENT_INFO.md` and do it as its own change, never during an image deploy.

## Spend safety (do not skip — this is metered)

A retry loop against a per-gigabyte product is a live financial risk. Before it
goes anywhere near production traffic:

- Hard per-process byte and request budget for the residential path, with the
  cap in `config.yml`. On exhaustion, fail the retry rather than falling back to
  unmetered behaviour silently.
- Log every residential fetch with host + bytes so spend is attributable.
- Interlock with `tasks/blocked-host-retry-economy.md`'s per-host memo so one
  blocked host cannot be retried through the paid path repeatedly.
- Start with a provider offering pay-as-you-go, not a monthly commit, so the
  first sweep prices itself.

## Verification

- **Do not live-test against konecranes** to prove it works. Use a
  reputation-blocked host chosen fresh, hit it at most twice, and record the
  before/after in `test-aitosoft/reports/`.
- Offline: assert the residential path is only reachable after a
  `origin_blocked` classification, that the byte cap terminates it, and that
  per-hop validation still runs.
- Assert credentials never appear in a response body, an error message, or a
  log line.
- Tier 1 regression 4/4 — none of them are blocked, so residential must never
  engage there. Assert that explicitly; a Tier 1 site touching the paid path is
  a bug.

## Sequencing

Depends on `tasks/blocked-host-retry-economy.md` (the classifier that decides
"reputation block" is the trigger for this path) and benefits from
`tasks/static-mode-tls-impersonation.md` (the static client that will carry it).
Do those first.
