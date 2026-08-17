# Residential/ISP egress on the retry path (reputation-blocked hosts)

> **PARKED 2026-08-02 by the coordinator scope cut — do not pick this up unasked.**
> The population is floor 6 / ceiling 29, the 23 undetermined resolve for free in MAS's next sweep, and this is the only item on the list that costs money. **What un-parks it: a real count, then Tero.**
> The reasoning is in `tasks/README.md` "The scope cut" and CLAUDE.md principle 7;
> the analysis below is preserved and still believed correct — it is the
> *priority* that changed, not the diagnosis. If you think it should be un-parked,
> say why in this file rather than just starting.

**Status:** Open, but **on hold pending a re-count** (2026-07-30 evening). The
mechanism below is sound; the population it was sized for may have largely
evaporated. Approved in principle by Tero 2026-07-30 for *framing* only —
provider choice and spend authorisation still to come. **Do not sign a
contract or commit credentials without Tero's explicit go-ahead.**

> **UPDATE 2026-08-01 — the population, derived rather than asserted.**
> `challenge-interstitial-resolve.md` phase 1 is done, and it does **not** hand
> this task a smaller number yet. What it settles is the *mechanism*; what it
> leaves open is whether the vendor these hosts sit behind resolves for us at all.
> Both previous statements of the population were wrong in the same way — a
> conditional outcome quoted as a count.
>
> The 33 `origin_blocked` verdicts in MAS's re-scrape decompose as (§10b, §10d):
>
> | | n | belongs to |
> |---|---:|---|
> | our own false positives | 4 | `detector-round3-evidence-vs-inference.md` (#4) — never ours to route |
> | `robot-suspicion` challenge, cloudfront `d1rozh26tys225` | 23 | undetermined until phase 2 ships and MAS re-scrapes |
> | 80,671-byte `403 - Forbidden` template | 4 | **this task, unconditionally** — a Block action, no wait resolves it |
> | unclassified | ~2 | this task |
>
> **So: the floor is 6 and the ceiling is 29.** Not "31", not "4", and not
> "three" — which is what Tero was last told and is below even the floor. Quote
> the floor with its condition attached, never a bare number.
>
> **The 23 are now measurable for free.** Phase 2 gives our existing patchright
> retry a longer capture wait (S, ships with #3+#4's image); MAS re-scrapes these
> hosts naturally, so their next sweep converts the 23 to a real count at zero
> marginal traffic and zero spend. **That measurement comes before any residential
> probe, which comes before any spend.** Do not reorder those.
>
> One thing phase 1 does settle for this task: `/challenge/never` — a wall that
> never lifts — cost 25.22 s at a 10 s wait and still returned the interstitial.
> Waiting is not a substitute for egress, and the 4 hard-403 hosts are exactly
> that case.

> **UPDATE 2026-07-31 — the re-count landed and the number is 31, not 3.**
> MAS re-scraped all 171 challenge hosts (forensics §10b): 133 return real
> content, **31 are `origin_blocked`**. §8d's *direction* was right and its
> *number* was not — five clean draws is compatible with an 18 % block rate
> (0.82⁵ ≈ 0.37), so "roughly three" was the most optimistic reading of a sample
> that could not exclude 31. Everything below sized for 171 is still too big;
> everything Tero was told on 2026-07-30 about "three hosts" is too small.
>
> **Two things must happen before this is re-priced again, in this order:**
> 1. `tasks/challenge-interstitial-resolve.md`. 23 of the 31 serve a JS
>    challenge at HTTP 202 — the code AWS WAF's Challenge action uses — and the
>    same 202 also returned the real site on 10 hosts. If a wait resolves it,
>    those 23 are not an egress problem at all and this task's population is 4
>    hosts serving a hard 403 template. **Do not spend before that number.**
> 2. A residential probe. **This is the one step here that genuinely cannot be
>    done offline**, so it goes last and stays small — see
>    `tasks/done/fixture-origin.md` for why that ordering is now the rule rather
>    than an exception.
>    It is free of *spend*, not of traffic: the dev container egresses through a
>    **Finnish consumer ISP, not a datacentre** (the address and provider are in
>    the gitignored `PRIVATE.md`, because it is the owner's own home connection).
>    We can run our exact code from a residential IP without buying
>    anything. That is the discriminator the cost table below has been waiting
>    for, and it also answers `static-mode-tls-impersonation.md`: run static
>    (httpx TLS) and full (Chrome TLS) from the same residential IP and see
>    whether the fingerprint or the IP is doing the work.
>    Site-safety, and it is **stricter here than anywhere else**: these are
>    MAS-classified blocked hosts, the standing rule in `TEST_SITES_REGISTRY.md`
>    applies, and the egress is a home connection rather than a cloud resource we
>    can re-provision. One hit per host per cell, logged. Burning the owner's own
>    connection is a worse outcome than not knowing.
>
> **Read also: `waa-eval-2026-07-30-forensics.md` §8d.**
> This task was sized on "171 of MAS's 243 affected hosts are egress
> reputation". Then we probed five of those hosts — four of them nominated by
> MAS — and **all five returned clean content to our Azure egress**. The
> challenge looks like a time-bounded 2026-04 deployment that has been
> withdrawn, not a standing block on our IP. If that holds, the genuine
> reputation class is roughly `konecranes.com` + `louisvuitton.com` + `alpit.io`
> — three hosts, not 171, and the cost table below is answering a question
> nobody is asking.
>
> **The gate is MAS's post-deploy re-scrape of the 171 challenge hosts.** It
> produces the real number for free. Re-decide then. Do not spend, and do not
> let MAS spend either — they were about to take option C to their owner as a
> budget decision (their reply-4 §3), on our now-superseded classification.

**Priority:** Low until the re-count lands, then whatever the real number says.
It is the only thing that makes konecranes-class hosts crawlable at all, but on
current evidence that class is small, and every other open task is a
correctness defect that costs us more.
**Effort:** M-L. **Risk:** medium-high — money, credentials, and a change to
the egress path that carries our SSRF guarantee.
**Evidence:** `tasks/waa-eval-2026-07-30-forensics.md` §0, §2a

## Why this and nothing else works

`www.konecranes.com` returns a Fastly/Varnish 403 to **all three** of our
engines — plain httpx, real Chrome + playwright-stealth, and patchright's
undetected-chromium — with byte-identical results. Two different browser
engines cannot agree unless the decision is made before fingerprinting matters.
It is IP/ASN reputation. Our egress is a single Azure West Europe address in a
shared SNAT pool (the environment has no VNet integration; the address is in
`PRIVATE.md`).

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
`AZURE_OPERATIONS.md` and do it as its own change, never during an image deploy.

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
