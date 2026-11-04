# Test Sites Registry

Which live sites we may test against, what each should return, and which hosts
we must not touch. The rules for live traffic are TESTING.md golden rules 0–1,
in short: live traffic is the last instrument, a justified live request is one
request, and no host gets more than 1–2 hits per session. **This file is where every live request is recorded.** How the
Tier 1 gate is run and what it checks: TESTING.md, "Live CLI scripts".

**Last updated:** 2026-11-03. "Stored captures" below means
`test-aitosoft/artifacts/<label>/`, which is local to this devcontainer and
gitignored.

---

## Tier 1: the deploy gate

Source of truth: `TIER_1_SITES` in `test-aitosoft/test_regression.py`. The gate
checks only the expected names; it does not check phones or emails.

| Site | Page | Expected name | What it exercises (from stored captures, 2026-08-17 unless dated) |
|---|---|---|---|
| **caverna.fi** | homepage | none | Since 2026-07 the homepage is a location picker with two addresses and no phone numbers: 1,001–1,239 markdown chars while it carried a news item, 539 since 2026-08-05. In April it was ~23,000 chars with phone numbers. It is the weakest gate member: it passed at 133 tokens against a 100-token bar |
| **accountor.com/fi/finland** | `suuryritykselle` | Katja Vanhanen (Jani Järvensivu until 2026-08-17) | A large real page (~8.8k tokens) with CMP scripts. It **redirects cross-domain to `www.aspia.fi/finland/suuryritykselle`**, as it has in every capture since 2026-04-11, so it also exercises final-hop handling |
| **solwers.com** | `sijoittajat/hallinnointi/#johtoryhma` | Johan Ehrnrooth | Names in ALL CAPS (`JOHAN EHRNROOTH, CEO`); the largest Tier 1 page (~13k tokens) |
| **jpond.fi** | `yhteystiedot/` | Janne Lampi | Plain emails (21 `@jpond.fi` occurrences in the markdown, 19 `mailto:` links in the HTML). **It is no longer `(at)`-obfuscated:** the site's own HTML had 18 `(at)` in captures up to 2026-04-15 and 0 in every capture from 2026-07-17 on. Nothing in Tier 1 exercises `(at)` obfuscation any more |

**Accountor was never a cookie wall.** The January 2026 failure (31 tokens) was
our own `remove_overlay_elements` flag deleting the page. `remove_consent_popups`
did not exist yet when the site was unblocked on 2026-01-24. Today no
`CybotCookiebotDialog` element appears in any successful capture, and `evästeet`
and `cookiebot` appear 0 times in its markdown. Whether `remove_consent_popups`
does any work here is unsettled; one request with it set to `false` would answer
that. Evidence: `FINDINGS.md` §Consent and overlay scripts, first entry.

**Expected contacts**, for checking stored captures by hand:

| Site / page | Person | Title | Phone | Email | Last verified |
|---|---|---|---|---|---|
| aspia.fi `/finland/suuryritykselle` | Katja Vanhanen | Growth Director | +358 40 688 7777 | katja.vanhanen@aspia.fi | 2026-11-04 capture (`0.9.5-merge-se`). Jani Järvensivu (Myyntijohtaja) was there until at least 2026-08-17 and is absent from the 2026-11-04 raw HTML: site drift, found when Tier 1 went 3/4 |
| accountor.com `/fi/finland/pk-ja-kasvuyritykselle` | Kari Putkonen | Myyntijohtaja, pk-yritykset | +358447386009 | kari.putkonen@aspia.fi | 2026-01 (page not in Tier 1) |
| solwers.com | Johan Ehrnrooth | CEO | | | 2026-08-17 capture |
| jpond.fi `/yhteystiedot/` | Janne Lampi | | | janne.lampi@jpond.fi | 2026-08-17 capture |

## Tier 2: not a gate

`test_regression.py --tier 2`. Three of its five entries repeat Tier 1 hosts
(jpond.fi, solwers.com, caverna.fi), so **do not run it in the same session as
Tier 1, and never run `--all`**. No Tier 2 report exists under
`test-aitosoft/reports/`, so the rows below are January 2026 notes that nobody
has re-verified.

| Site | Page | Expected name | Notes |
|---|---|---|---|
| **neuroliitto.fi** | `yhteystiedot/hallinto-ja-tukipalvelut/` | Helena Ylikylä-Leiva | contacts 3+ levels deep; Cookiebot tracking |
| **showell.com** | homepage | none | `.fi` redirects to `.com`; heavy tracking (39 Cookiebot URLs); no contacts on the homepage |

---

## Do not live-test

### Retired test sites

| Site | Retired | Why |
|---|---|---|
| **talgraf.fi** | 2026-04-11 | Permanently Cloudflare-blocked by our own over-scraping. This is the cautionary tale behind rule 1 |
| **tilitoimistovahtivuori.fi** | 2026-04-11 | Contact page 404s (site restructured) |
| **monidor.fi** | 2026-03-26 | Site restructured; old paths 404 |

### Burned hosts: the live-request record

These are customer sites a diagnosis forced us to hit, several of them past the
1–2 rule. Each one has a fixture or offline reproduction, so re-hitting it buys
nothing. **Add a row in the same session as any new live request:** host, count,
date, why, and what replaces it.

| Host | Hits | Why | Verify instead with |
|---|---|---|---|
| **maitokolmio.fi** | 8 (2026-07-30) | config matrix isolating the untimed-render hang | `test_render_bounds.py` |
| **kiertopakkaus.fi** | 4 (2026-07-30) | reference case for nested-`<noscript>` body loss | `test_noscript_body_collapse.py`; DOM captured |
| **konecranes.com** / `www.` | 3 (2026-07-30) | reputation-blocked at a Varnish edge; already smoke-verified in prod once | `test_redirect_block_detection.py` |
| **magicad.com** | 3 (2026-07-30) | challenge-family probe | `test_antibot_challenge_detection.py` (fixtures from MAS's stored samples) |
| **savagroup.fi**, **palsatech.fi**, **pajala.fi**, **recset.fi** | 1 each (2026-07-30) | challenge-family probes nominated by MAS | as above |
| **anitamakela.com** | 1 (2026-07-30) | the origin's own zero-byte Apache 500 | `test_failure_classification.py` |
| **www.kubler.fi** | 1 (2026-08-06) | the Enfold host whose `<html>` class made our consent JS delete the document. A post-deploy request proved the fix: 55,545 markdown chars, 5 emails, HTTP 200. MAS also hit it 8 times in segment 1 | `fixture_origin.py` `/consent/{shape}` |
| **www.grumblo.com** → `shop.grumblo.com` | 1 (2026-08-09) | a 22.1 MB response; was it the `media desc` mechanism or a second cause? It was one plain `httpx` GET from the devcontainer (home ISP, not Azure egress). Answer: same mechanism. 272 images carry 88 % of a 1.73 MB `media` payload as `desc`, and the cap takes it to 108 KB with `cleaned_html` byte-identical | `test_media_desc_cap.py` |
| **www.fortax.fi**, **suujahammas.fi** `/ajanvaraus` | ours: 2 each (2026-11-04) | joint run (ii) brought both back "newly empty" against August, and Fortax lost work. One request each through `-se` (v0.9.5, Chrome 157) and the idle West Europe app (v0.9.2, Chrome 151): is it the merge or the site? MAS's agent also fetched each once in run (ii) | the A/B answer recorded in `tasks/upgrade-upstream-v0.9.5.md` §10 |
| **neverssl.com**, **example.com** | ~10 and 2 (2026-11-04) | not customer sites: neverssl.com exists to be http-only, and example.com is IANA's. Does Chrome 157 refuse http-only sites, and does one switch fix it? 8 navigations from `az acr run` probes on the shipped image, 1 `curl`, 1 production canary through `-se` after the deploy. example.com was the control: it serves https too | `test_an_http_only_public_site_renders` and its control (`--host-resolver-rules` onto the fixture); FINDINGS §Upstream merge watchlist |
| **www.diabetes.fi**, **ahlmanedu.fi** | 39 and 19 (2026-04-14) | the "hard", Azure-blocking sites in `test_soak.py` | fixture `/challenge/never`, `/block/*`, `?stall=` for the fence |
| **roadscanners.com**, **columbia-road.com** | not recorded (2026-04-15) | static-mode development: a DevTools-protocol hang, and a timeout path | `test_render_bounds.py`, `test_static_mode.py` |

**Standing rule:** never live-test a host MAS has classified `blocked` or
`challenge` in `tmp/crawl4ai-affected-hosts.txt` (gitignored, produced
2026-07-30, local to this devcontainer). Probing a host that is deciding whether
to trust our egress is how that decision goes against us, and we cannot tell a
fresh block from one we caused.

---

## Content patterns seen on Finnish SME sites (2026-01, MAS V1–V10)

Kept as one-line lessons; none of them is a crawl4ai test.

- **Email obfuscation** (`name(at)domain.fi`, the same split across lines, or a
  stated pattern such as talgraf's `etunimi.sukunimi@talgraf.fi`) is handled by
  MAS's LLM. crawl4ai needs no regex decoding.
- **Phone formats** (`050 361 6485`, `0503616485`, `+358 50 361 6485`, landlines
  such as `010 574 3806`) are all extracted by the LLM in context.
- **Contact-page paths** worth trying when you choose a test page:
  `/yhteystiedot`, `/ota-yhteytta`, `/johtoryhma`, `/hallinto`, `/tiimi`,
  `/yritys`, `/en/contact`, and WordPress `?page_id=<n>`.
- **Page sizes vary by two orders of magnitude**, and tokens cost MAS. Tier 1 on
  2026-08-17, in markdown tokens: caverna.fi 133, jpond.fi 1,686, accountor 8,835,
  solwers.com 13,173.

## Adding a test site

Pick it under rule 0: a host that answers a question no fixture can. Record:
domain, company, Y-tunnus, the page to crawl, 1–2 decision-makers with
title/phone/email, what makes the site hard, and which tier it joins. Add
gate members to `TIER_1_SITES` / `TIER_2_SITES` in `test_regression.py`, which
is what the gate reads; this file only describes them. When a site drops out,
move it to "Retired test sites" with the date and reason.
