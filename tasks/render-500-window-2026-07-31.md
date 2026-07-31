# 9 renders failed inside one 4½-minute window, and the sweep is a burst

**Status:** Open — investigation first, from logs and correlation IDs. **Zero
live traffic.** MAS handed us the correlation IDs; the evidence is already in our
Log Analytics.
**Priority:** High. The failure population is small (3.6 % of one probe) but the
*shape* — a time window rather than a per-host property — points at exactly the
condition MAS's ~15,000-company sweep creates, and that sweep is the largest
single event either side has planned.
**Effort:** S-M. **Risk:** none to investigate.
**Evidence:** `tmp/mas-repo-messages/09-from-us-taxonomy-answer-and-zero-traffic.md`
§2 and its corrections section.

## What MAS measured

Their 243-host probe against `0.9.2-failure-class`, 04:44:56 → 05:03:39 UTC on
2026-07-31 — **the only traffic that has gone through the current image**, since
they have had zero production WAA invocations since the deploy (their §2; checked
in `agent_invocations`, not inferred).

| | |
|---|---:|
| total HTTP requests from them | **252** (corrected from 251) |
| HTTP 500 | **9** (3.6 %) across 5 hosts |
| HTTP 504 | **0** |
| max wall time, any single fetch | 34,797 ms |

Every one of the 9 was `{"error":"Internal server error", "failure_class":
"render_error"}`. **All five hosts eventually succeeded and four returned real
content**, so the origins were fine. These are our renders failing.

| host | attempts | correlation_id per 500 | first seen (UTC) |
|---|---:|---|---|
| `eurobull.fi` | 2 | `e7deaf4ececb` | 04:46:07 |
| `meitmeal.fi` | 4 | `631b86527fc3`, `4492bd99f3f7`, `c75787261894` | 04:46:18 |
| `valonkone.com` | 4 | `d0b1d722e133`, `73220db2dd23`, `7b710be5a333` | 04:46:47 |
| `savaterra.fi` | 2 | `3bac649a8171` | 04:47:06 |
| `powerofsun.fi` | 2 | `e9d8eb4e344b` | 04:50:33 |

## The observation that makes this a task

MAS flagged it and deliberately declined to interpret it, which is the right call
from where they sit:

> **5 of the 70 hosts probed between 04:46 and 04:50 hit a 500; 0 of the other
> 173 did.**

A per-host property does not cluster like that. A property of *our replicas at
that moment* does. And 04:46 is roughly 90 seconds into a burst arriving at a
service that **scales to zero** — so the window coincides with the one condition
we know is expensive and have never measured under load:

| Fact | Value | Source |
|---|---|---|
| scale-to-zero idle | ~5–6 min after last request | forensics §0 |
| cold image pull | **37.6 s** (1.79 GB) | forensics §0 |
| app boot | ~3.5 s | forensics §0 |
| render capacity | 2 per replica, KEDA rule at 2 concurrent | `config.yml` + ACA |

**Hypothesis to test, not to assume:** requests landing on a replica that is
still starting — image pulled, app up, but the PERMANENT pool browser not yet
initialised, or the pool re-initialising — fail in a way that classifies as
`render_error`. If so, every scale-out step during the sweep produces a burst of
500s, MAS retries each three times, and the cost is worst exactly when volume is
highest.

Competing explanations that must be excluded before believing that one:

- **Concurrency, not coldness.** RenderGate rejects with 429, not 500, and the
  7-day census showed 0 REJECTs — but that was before this probe's arrival rate.
  Check `RenderGate ADMIT` / `REJECT` and `in_use=` around the window.
- **A property of those five hosts after all.** Four of the five are in MAS's
  retry list from message 07, so they were hit repeatedly — check whether the
  500s correlate with the *repeat* attempts rather than the clock.
- **Coincidence.** n = 5 hosts in one 19-minute run. Say so if that is where the
  evidence lands; a negative result here is worth having written down.

## Also answers two questions MAS asked us

Both come out of the same log query and neither needs a new instrument:

1. **Did the 9 × 500 reach the origin?** MAS cannot tell from outside, and it
   changes their site-safety ledger: if `render_error` fires *after* the fetch the
   day cost 255 origin hits, if before, 246. The correlation IDs are the join key.
   Under the shared-egress finding this is our number to produce, not theirs.
2. **Does the clustering mean anything?** Whatever the answer, send it — they
   explicitly said they would rather know before reading a 3.6 % rate into
   anything.

## What this replaces

`tasks/post-deploy-measurement-0.9.2-failure-class.md` is **closed** by MAS's §2.
Its remaining half was a production log census, and there is no production
traffic to census — 86 WAA runs on 2026-07-30, all before the 18:24 deploy, none
since. This probe is the entire dataset the current image has seen, so the census
is this task.

One thing the probe did settle in passing: **0 × 504, and nothing came within
145 seconds of the 180 s fence.** That is consistent with the render-hang fix
having removed the failure `static-fallback-within-fence.md` was sized against.
243 fetches on one afternoon is not a workload, but it points the way we
suspected — record it there.

## If the hypothesis holds

Do not design the fix in this file; the shape depends on which of the three
explanations survives. But note what already exists to build on: the pool has a
PERMANENT tier and a BUSY_SINCE janitor (`crawler_pool.py`), and ACA has a
startup probe (`DEPLOYMENT_INFO.md`). A replica that is not ready to render
should not be receiving renders, and that is a readiness-probe question before it
is a code question.

## Verification

- Zero live requests. Log Analytics (`ContainerAppConsoleLogs_CL`,
  `ContainerAppSystemLogs_CL`) and the correlation IDs above.
- Whatever the verdict, write it into
  `tasks/waa-eval-2026-07-30-forensics.md` §11 and answer MAS in the next message.
- If a scale-out defect is confirmed and the fix is small, it joins the
  `cleaned-html-collapse-guard` + `detector-round3` image rather than getting its
  own deploy.
