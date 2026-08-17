# Open tasks, in the order to do them

**Updated:** 2026-08-17, after the final WAA sweep ended and a six-agent forensic review of it.

**Read this first: the service is in good shape and the open list is deliberately short.** Seven
task files were closed on 2026-08-17 — not because they were wrong, but because the sweep sized the
harm and the harm was smaller than the risk of fixing it. The reasoning for each closure is in
`tasks/done/post-sweep-closure-2026-08-17.md`, and it is worth reading before you re-derive any of
them.

## How to read this file

Every item below gives you **the concern, the evidence, and why it matters** — and deliberately no
ordered checklist. You are a peer with a clean context and the same tools; a step list would narrow
your judgement, and this repo's record is that a fresh session re-deriving the diagnosis catches
what the author missed. **You are expected to challenge what is written here and to record what you
found wrong, in the task file itself.** That has happened on nine consecutive task files and it is
the quality gate that actually works.

Where a task file and this index disagree, the task file wins and the index is stale.

---

## State of the world

**Production:** image `0.9.2-desc-cap`, unchanged since 2026-08-09. **Check the revision, trigger
and replica bounds with `az`, not with any document here** — `AZURE_OPERATIONS.md` opens with the
exact commands, and every transcribed copy of those values in this repo has drifted at least once.

**`main` == production** as of the 2026-08-09 deploy. This sentence has been false in both
directions before; verify it rather than believing it.

**Nothing is gating. Nothing is waiting on a deploy. There is no active campaign** — MAS's sweep
finished 2026-08-16T21:50 UTC and their request rate against us is near zero until the next one.

### What the final sweep measured

2026-08-09T14:19 → 2026-08-16T21:50, **175.5 h, 186,178 `/crawl` requests** — 5× anything either
repo had run. 93.6 % × 200, 5.66 % × 429, 0.69 % × 5xx. Mean true concurrency **1.68**.

**The number that should govern your sense of proportion** is MAS's terminal accounting, because it
counts pages we cost them rather than wire events: of **60,874 capture attempts, 86.1 % stored**;
our 429s cost them **29 captures**, our 500s **156**, our `render_defect` **27**. **95 % of all
their failures were the origin** — dead domains, 404s, and sites blocking us. Across 175 hours,
**2 requests failed hard at the wire** (both in the one moment both replicas restarted together).

**The scale trigger 6 → 12 change (2026-08-14) is the most valuable thing this repo has done in six
months, and it was one number.** Mean fleet 11.05 → 1.97, slot utilisation 8.9 % → 40 %, cost per
1,000 requests **$3.28 → $0.51**. It cost queue wait (0.041 s → 0.919 s mean) and 27× more
RenderGate rejections per admit, all absorbed by MAS's retry ladder.

**Costs are in USD.** The Azure usage export carries no currency column and every euro figure this
repo published before 2026-08-17 is ~12 % high. `€398.89 for one sweep` is `$398.89 ≈ €350`.

---

## The open items

| # | Task | Size | Why it is on this list |
|---|---|---|---|
| **1** | `capacity-gate-in-the-429-envelope.md` | S | MAS's one explicit ask, we committed to it, and the sweep proved why it matters. |
| **2** | `fixture-origin-bypasses-the-pinning-proxy.md` | S | ~12 lines; makes 67 existing tests measure the path production uses. The fast feedback loop. |
| **3** | `file-upstream-prs.md` | M judgement | The simplicity play, and it is time-sensitive. |
| **4** | `render_mode` mislabel — no file, it is one word | XS | We report a lie in a field MAS parses. |

### 1. Put the capacity gate in the 429 envelope

**The concern.** Both our 429 mechanisms emit a byte-identical envelope — `failure_class:
"capacity"`, `Retry-After: 5` — differing only in free text after `Replica at render capacity:`. So
MAS cannot hold a threshold on either gate independently, and the stop-trigger we handed them for an
unattended run was **unevaluable**; taking it literally would have aborted a healthy run at minute
two.

**The evidence that it matters, and it is better than when this was first written.** MAS's `49-…`
§1 discovered that our memory gauge has been sitting in their logs **for a fortnight** — every
refusal carries `memory at 90.2% (limit 85.0%)` — and they read it two weeks late because it was
embedded in prose. Those 4,455 readings turned out to be a **better instrument than our own**
(our janitor's sampling interval is chosen from the reading it just took, so it oversamples high
states; theirs is triggered by request arrivals and is unbiased). A structured field would have made
their whole §1 a dashboard.

**Scope, and the reasoning behind the shape.** Ship an **additive `capacity_gate` field, not a new
`failure_class` value** — both need identical plumbing, but a new enum value additionally breaks the
two places pinning `capacity` (`test_failure_classification.py:317`, `AITOSOFT_CHANGES.md:1559`) and
splits MAS's own 429 baseline mid-programme. Keeping `capacity` as the stable total is the point.
Add `memory_pct` and `limit_pct` alongside it — that is the half `49-…` actually argued for.
Always present, so absence means "old build".

The plumbing runs `RenderCapacityExceeded` (`aitosoft_admission.py:71-74`) → `:140`, `:160`,
`crawler_pool.py:431,466` → `_capacity_429` (`api.py:825-829`) + the stream twin (`:1278-1282`) →
emitted in `server.py:540-547`.

**Fold in:** `AZURE_OPERATIONS.md`'s claim that "a 429 means the render slots are full" is actively
wrong — **~94 % of the sweep's 10,532 429s were the pool memory guard, not RenderGate.**

**What I am least sure of:** whether MAS would rather have a header (`X-Capacity-Gate`) than an
envelope field. They asked for the envelope; a header is the true minimum and needs no `server.py`
change. If you find the envelope path ugly, the header is a defensible substitute — tell them.

### 2. `fixture-origin-bypasses-the-pinning-proxy.md`

**The concern.** `set_egress_proxy()` has exactly one caller, `server.py:183`, so `ProductionPath`
never starts the proxy and **all 67 fixture tests run on a network path production does not use.**

**Why it matters more than its size suggests.** A dead host is **134 s direct vs 30 s through the
proxy** — a test without the proxy measures the wrong number by 4×. Every failure-class test we
have, and every future one, inherits that error. This is the loop where investment still compounds:
data-quality defects are testable offline in seconds, while infrastructure defects need a real sweep
and are now essentially closed out.

**Expect some tests to change behaviour, and treat that as the payoff, not a problem.**

### 3. `file-upstream-prs.md` — reframed, and now time-sensitive

**The concern is maintenance surface, not altruism.** Our fork is **+4,696 / −193 lines across 25
files**, and **~2,375 of those lines sit on 17 files upstream also owns**. `crawler_pool.py` alone
is +605. Upstream currently has 7 commits we lack, and three of them edit `api.py`, `server.py` and
`supervisord.conf` — our three heaviest diffs — solving the same problem class our
`aitosoft_failure_class.py` solves. **The divergence is actively growing.** A merged PR deletes our
diff permanently; an unfiled one is a merge conflict every release, forever.

**The reframe, and it is the most useful thing the 2026-08-17 research found.** We planned to argue
the consent PR on the root collision. That is right but it is not the strongest argument, and it
proposes the wrong fix:

- **DuckDuckGo's `autoconsent`** — ~300 CMP rule files, commits daily — has **no `remove()` action
  in its rule syntax at all.** Its actions are hide / click / wait / set-style.
- **uBlock and EasyList hit our exact bug in 2021** (`uBlockOrigin/uBlock-issues#1692`: sites
  blanked because `body` carried a consent class matched by a generic filter) and still carry
  **~845 hand-written `:not(html)` / `:not(body)` guards** across Fanboy's and AdGuard's lists,
  verified live on EasyList master.
- **Every maintained system in this space hides rather than removes.** crawl4ai's snippet is more
  dangerous than any adblocker not because its selectors are worse but because **its action is.**

So the strongest submission is **"the generic tier should hide, not remove"**, with the structural
guard as defence in depth — which is what we already do internally, and what the whole field
converged on. It makes the root-collision question moot rather than merely survivable.

**Time pressure:** upstream **PR #2139** (filed 2026-08-13, unreviewed) modifies **both**
`remove_consent_popups.js` and `remove_overlay_elements.js`, for an unrelated CSP-sandbox hang. File
soon and reference it.

**And read our own stop condition before starting: it has fired.** The file says "if #2114 sits as
long as #2085 did, stop filing and carry the patches." Upstream has **116 open PRs**, **5 commits in
all of August** (against 42 in July), and **zero maintainer engagement on any of our four** in
18–31 days. **That is a real argument for filing fewer, better PRs rather than more** — the `desc`
cap and the consent snippet are the two that carry their own evidence and need no context from us.

**What I am least sure of:** whether a "hide" change is acceptable to upstream at all, since
`cleaned_html` is parsed by lxml and `display:none` still leaves the text in the DOM. Hiding is
sufficient for `innerText` and insufficient for a DOM extractor. That tension is real and the PR
must address it — possibly by removing only *inside* a structural guard and hiding otherwise.

### 4. The `render_mode` mislabel — one word

`api.py:1198`'s `failed_result(...)` omits `render_mode`, which then defaults to `"full"`
(`aitosoft_failure_class.py:507`). Because the seed check (`:760`) precedes the static short-circuit
(`:764`), **a static-mode request to a dead domain is reported to MAS as `"full"`.** One word, in a
field they parse.

**The sibling half of this item is dead and should not be rebuilt:** `render_mode: "static"` failed
fetches log no `failure_class` at all (`aitosoft_static_mode.py:301,307`). Real in code, and
**exactly zero requests wide** — static mode was used **0 times in 186,178 requests**, confirmed
from MAS's side (`renderMode: "full"` on all 61,937 of their rows).

---

## Parked on purpose — do not pick these up unasked

**`residential-egress-retry-path.md`.** It addresses the layer our data says actually dominates:
blocks are IP-based, not fingerprint-based, and Azure's shared SNAT means we inherit co-tenants'
reputation. But it needs an instrument **neither repo has** — a real browser from a residential IP.
`curl` cannot substitute: a 403 there separates nothing, and even a 200 could be TLS or header
shape rather than address reputation. Also relevant: the one independent 2026 benchmark puts
Patchright at **25 of 31** Cloudflare targets against vanilla Playwright's **24** — our tier-2 has a
small, measured ceiling, and every "residential vs datacentre" percentage in circulation comes from
companies selling residential proxies.

**`guard-corpus-is-not-in-the-repo.md`.** XS. Three tests fail on a fresh clone because
`test-aitosoft/artifacts/*` is gitignored. It fails **loud, in the safe direction**. Either commit
4–6 files into `artifacts/keep/` (the mechanism `.gitignore:14-17` already provides) or delete the
file. **Do not open its four-option sizing table** — that is exactly the elaboration this repo's
principle 7 warns about.

**The response-size backstop, and the `media.tables` `colspan` amplifier.** `table_extraction.py`
does `row_data.extend([text] * colspan)` with an **unvalidated integer straight from the page**: a
4,624-byte page reaches 4.5 MB of `media`, and `colspan="2000000"` costs **+91 MB RSS from 905 bytes
of HTML** while leaving the wire unchanged. Never seen in production. The sweep's largest response
was **32.6 MB** and **zero exceeded 100 MB** against the 232 MB that lost a customer before the
`desc` cap — so the cap is holding and this stays parked. Two things raise its priority if they
change: an actual production instance, or a decision to fix OOMs by bounding allocations (this is
the one candidate that bounds an *allocation* rather than re-scaling a *meter*).

**Raising `render_capacity`, and any further scale-trigger change.** The fleet is at its floor. Loop
gain (see `AZURE_OPERATIONS.md`) is ~0.45 at trigger 12 against ~0.87 at trigger 6 — comfortable.
A replica at 2/2 is already oversubscribed ~2.4× on CPU.

**More memory work.** Closed by two repos independently: `anon` moved **+26 MB of 4,096 across 53
hours**. See the closure record.

---

## Open threads that are real but need someone else's data

**53 captures came back with no `<body>` element at all**, on 28 hosts (`etlistat.fi` alone ×15).
**26 of those 28 hosts emitted no `CONSENT DECLINED` line**, so our own consent JS is not the cause
for the great majority, and MAS sends `remove_overlay_elements: false`. Two engines agree on
`delotec.fi` at 2,015 bytes. **It is a real unexplained mechanism and it is 53 captures** — worth a
task file only if it grows or if MAS can hand over the bytes.

**PDF text extraction.** MAS holds April captures with 11,101–45,118 characters of extracted PDF
text; today the same class returns a 174-byte viewer shell. **Who caused that is NOT established** —
their attribution to our browser change is inference, not a provenance check, and this repo cannot
reproduce it either way (`pypdf` is not in the image). Nobody needs it: MAS removes PDFs at
dispatch. **Upstream is moving here** — issue #2135 with two competing PRs (#2137, #2138), plus
#2130 adding `pypdf` to the Docker requirements. **Take theirs; build nothing.**

---

## Standing rules that have earned their place

**Size the harm before opening the investigation.** If you cannot state an upper bound on what a
defect is costing, that bound is the first measurement. This repo has consistently investigated
first and sized second, and the 2026-08-17 review is what made the cost of that visible: the memory
family consumed weeks and cost 29 captures.

**Do not build what upstream will ship in a month or two.** They see every user's experience; we see
one client. Spend our effort on what we must hand-roll — the Azure deployment, the admission and
pool layer, the failure taxonomy — and take theirs everywhere else. Check `git log
HEAD..upstream/develop` and the open PR list before starting anything in `crawl4ai/`.

**Research what is true *this month*, not six months ago.** This field moves fast and we have been
burned by stale advice in both directions. The 2026-08-17 research pass found that the consent
problem was solved by the wider ecosystem in a way we had not noticed, and that our own operational
knowledge exceeds anything published. Both were worth knowing; neither was derivable from inside
the repo. Do this periodically, and always record each source's date.

**Our characteristic failure is a wrong instrument, not sloppy reasoning.** Every headline number
that turned out wrong was wrong because the measurement was wrong. Before reporting a number, say
which table and column produced it and what would make it wrong. Count anything that matters twice,
from two instruments; when they disagree, that disagreement is the finding. The trap list lives in
`AZURE_OPERATIONS.md`, and it grew by six entries on 2026-08-17 — including one (`contains` is
term-based on `_CL` columns) that produced a **false refutation of a correct claim**.

**Reach for the cheapest lever before the cleverest one**, and verify the cheap lever exists before
building an argument on it. Buying headroom, deleting a feature, raising a limit and doing nothing
are all legitimate answers, and they beat a correct implementation of the wrong question.

**Roles stay separated across sessions.** Whoever writes a plan does not implement it; whoever
implements does not sign off. The implementing session is *required* to challenge the task file and
record what it found wrong. A task file that survives implementation unamended is the unusual case.

---

## Cross-repo state

Messages live in gitignored `tmp/mas-repo-messages/`. **Cite filenames, never integers** — the two
repos' numbering has diverged and a message once sat unread for two days because of it.

**Last exchange:** MAS sent `49-…` plus `49-data/` (61,937 timing rows, 5,511 retry rows, hourly
aggregates, per-host 500 tables, terminal outcomes) on 2026-08-17. We replied with `50-…`, which
answers their three questions, corrects four things we had told them, and asks for nothing.

**Corrections we sent them in `50-…`, in case they come back on any of it:** the 2026-08-15 OOM was
not the first (2026-08-13 was) and not "two containers" (ACA emits two rows per kill); there were
34 container restarts in the 53-hour window, not 4; `az containerapp replica list` *can* see silent
restarts via `properties.containers[].restartCount`; and `unrenderable_content` has now fired 12
times after we told them it never had.

**What each side can see, because it decides who should measure what.** We see inside the browser,
the pool, the admission gate, response bytes on the wire, which detector branch fired, and anything
at the point of removal *before* capture. They see ~117,000 stored pages, corpus history (has this
URL ever succeeded, and with how many characters), what was inside an element we declined to remove,
the complete 404 instrument, their own client's socket behaviour, cohort composition, and — the one
that matters most — **whether a company actually lost work.** Their terminal-outcome table is a
better prioritisation instrument than anything we hold, and adopting it is what reordered this list.

---

## Documentation

| Doc | When |
|---|---|
| `AZURE_OPERATIONS.md` | Anything about the deployment, scaling, cost, logs or alerts. Live state is `az`, not prose. |
| `OVERNIGHT_PLAYBOOK.md` | Tero says "monitor overnight". |
| `AITOSOFT_CHANGES.md` | What we changed and why — the authoritative change log. |
| `TESTING.md`, `TEST_SITES_REGISTRY.md` | Test framework, quality gates, site safety. |
| `tasks/done/post-sweep-closure-2026-08-17.md` | Why seven items are closed. Read before re-deriving any of them. |
| `tasks/waa-eval-2026-07-30-forensics.md` | The five root causes behind the 2026-07-30 image; cited by older work. |
