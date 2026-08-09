# The autoscaler over-provisions the fleet by ~44× on MAS's traffic shape

> **CLOSED 2026-08-09 — the confirmation ran, twice, and passed. Do not re-run
> the acceptance experiment; it is already in production data.**
>
> This header said the confirmation was still owed, and because CLAUDE.md
> principle 9 makes the task file win over the index, a clean-context reader was
> being pointed at the one document claiming a measurement was outstanding. Both
> runs happened *before* this file was updated:
>
> - **Segment 5** (2026-08-08, 318 companies at `--concurrency 4`, 1,987
>   requests, 3 h 14 m — 6× the load the trigger change was validated on):
>   **max 9 replicas of 45** for a true concurrency of mean 1.31 / p95 2.96 /
>   max 5.25. 3 × 429, 0 × 504.
> - **Batch 1** (2026-08-09, 200 companies at `--concurrency 5`, 1,364
>   requests): **max 10 replicas of 45**, concurrency mean 1.49 / p95 2.69.
>   3 × 429, 0 × 504.
>
> **No revert criterion was met in either.** Against segment 3's 30 replicas for
> a ~1.2-concurrency workload, that is the change working. Nothing here is
> pending.

**Status:** **SHIPPED 2026-08-08, ACCEPTANCE PASSED 2026-08-08/09, CLOSED** — ACA
scale trigger `concurrentRequests` 2 → 6, validated by a controlled synthetic A/B
against production (below): **replica plateau 38 → 5, zero 429s in both arms, max
queue wait 5.3 s of the 15 s budget** — then confirmed on two real workloads (see
the closing note above). Revert is one `az` command, no image rebuild.
**Size:** M as estimated. The edit really was one number; the measurement really
was the work — and it went somewhere the plan did not anticipate.

**Rewritten by the implementing session after six research threads and one
controlled experiment.** The original diagnosis was directionally right and its
headline was wrong. Read "What the original file got wrong" before anything else.

---

## The finding, restated correctly

On 2026-08-08 MAS ran segment 3 (50 companies, `--concurrency 3`, 04:54–05:24
UTC, 299 `/crawl` requests). Our fleet climbed to **30 replicas — the
`maxReplicas` ceiling at the time — and stayed there**, then took ~9 minutes to
drain. Mean true concurrency over the window was **1.24**; the instantaneous
peak was **8**. Measured in replica-minutes the run consumed **781 against ~17.6
justified — 44×, or ~2.3 % efficiency** (153.5 replica-seconds billed per fetch
against 3.5 of actual work).

The cause is not that ACA's autoscaler is broken. It is that **its trigger was
pinned to a number in a different unit**, which made it fire on essentially any
activity.

---

## The root cause: a category error, not a ratchet

`render_capacity: 2` (RenderGate, `aitosoft_admission.py`) and the ACA scale rule
`concurrentRequests: 2` were held equal by a `config.yml` comment asserting they
MUST match. They are not the same kind of thing:

| | what it is | units | is it a safety mechanism? |
|---|---|---|---|
| `render_capacity` | hard cap on simultaneous renders per replica, enforced in-process | concurrent renders | **yes.** Cannot be exceeded. `gunicorn --workers 1`, so process == replica |
| ACA `concurrentRequests` | when Azure adds a replica | Microsoft's own doc: *"requests in the past 15 seconds divided by 15"* — a **rate**, while named "concurrency" | **no.** It protects nothing |

Two quantities in different units cannot meaningfully be equal. Setting the
trigger to the gate's capacity means "add a replica the instant a replica is
doing anything", which is maximally twitchy. **ACA's own default for this rule is
10; we were running 2.**

Raising the trigger **cannot** oversubscribe a replica. The gate still admits
`render_capacity` renders and queues `admission_queue` more, regardless of what
the scaler does. That is the whole reason this change is low-risk.

---

## What the original file got wrong

Recorded in the file, per CLAUDE.md principle 6. Ten consecutive sessions have
found the previous file wrong about something load-bearing; this is eleven, and
one of the corrections came from the implementing session's own hypothesis being
refuted by its own experiment.

1. **"A load that justifies one replica" — the headline — is not what the data
   says, and the number quoted was an averaging artifact.** "Peak 2.9 in any
   minute" is a per-minute *average*. `ContainerAppHTTPLogs` carries a
   `StartTime` column (and `TimeGenerated == StartTime` for all 299 rows, so it
   is arrival), which lets you sweep true overlap: **the instantaneous peak was
   8**, and the workload justifies **4** replicas at its busiest moment, 1 on
   average. The honest overshoot is 44× in replica-minutes — a stronger number
   that does not depend on the peak-vs-mean argument at all.
2. **"The autoscaler ratchets" is refuted.** Segment 2 ran **1.7× longer with
   more busy-seconds and peaked at 16, not 30**, and both segment 2 and the
   08-05 run **scaled down mid-run** — which a monotone ratchet cannot do. The
   drain is also invariant to the peak (9.06–9.44 min whether the peak was 16 or
   30), where a self-referential metric would take proportionally longer from a
   higher peak.
3. **The €0.30/run figure is ~10× low, in the opposite direction the file
   guessed.** At list price the segment-3 waste is **€2.98–3.16**; the estimate
   anchored on the 30-replica peak instead of integrating ramp + plateau +
   drain, where most of the area is. The file reasoned "if it turns out to be
   trivially small, option C gets much stronger" — that branch does not fire.
   Separately: **cash cost is €0**, because the subscription is Sponsored
   (`quotaId: Sponsored_2016-01-01`) and has emitted no Azure usage record since
   2026-06-03. And the free grant gives no comfort: **one run is 51 % of the
   monthly grant**, the projected sweep is **205×**, and `minReplicas: 0` makes
   the cheaper idle rate permanently unreachable.
4. **Design option B does not exist.** The file said to "check what is actually
   settable". It is settable and it is a no-op: `pollingInterval` is a real ARM
   field that Microsoft documents as *"doesn't apply to HTTP and TCP scale
   rules"*; `cooldownPeriod` is real and governs **only** the final replica → 0
   transition. What actually damps scale-in is the **300 s scale-down
   stabilization window**, which has **no configuration surface anywhere in ACA**
   (`microsoft/azure-container-apps#1418`, open since 2025-02). The design space
   is A, C, D — never B.
5. **The central cost/429 trade is largely illusory.** The file's most emphatic
   warning was that over-provisioning "has been absorbing MAS's bursts". The ACA
   ingress is **round-robin, decided per request, session affinity off**
   (`stickySessions: null`), and Envoy picks the endpoint *then* the connection
   pool — so a big fleet **dilutes** bursts rather than absorbing them, and
   dilution requires the replicas to already exist. The 429 window is **cold
   start, where there is exactly one replica no matter what `maxReplicas` says**.
   MAS's own control already said this: three crossings of 5 concurrent in
   minute one produced their single 429; seven crossings after KEDA had scaled
   produced none.
6. **The acceptance experiment as specified could not have measured the thing.**
   It proposed a one-shot cold burst of N=12/16. A burst measures cold-start
   429s — the *safety* side. It cannot reproduce the over-provisioning, which
   builds over minutes of sustained traffic. Those are two experiments, and the
   file conflated them.
7. **`example.com` was the wrong target and an unnecessary one.** `raw://` URLs
   render through the **full** browser path with **zero network egress** — see
   the new tooling section below. It is strictly better on every axis, including
   the file's own requirement that both A/B arms carry identical load, which a
   third party cannot promise.
8. **`deploy-image.sh` would have broken, and the file did not notice.** Its
   invariant check hard-fails `exit 1` when `render_capacity != concurrentRequests`
   — **after** `az containerapp update --image` has already landed. Shipping the
   scale-rule change without touching that script would have left every
   subsequent deploy failing at the verification step with the new image live.
9. **Segment 3 also shipped 12 HTTP 500s (4.0 % of requests) that the file does
   not mention**, all `failure_class=render_error`, 28.9–36.3 s, in two clusters
   (4 at cold start, 8 in a 2m41s burst at 05:10–05:13 across 8 different
   replicas). A 500 is retried **3×** by MAS where a 429 is retried once. The
   file says "any candidate setting has to hold the zero" about 429s while
   treating a run with 12 of the more expensive class as clean. **Not this
   task's problem, but it is unclosed** — the 05:10–05:13 shape is not random.

---

## The experiment that changed the conclusion

**This is the most important section, because it refuted the implementing
session's own model as well as the file's.**

Two independent research threads fitted models to the observational data and
disagreed: one concluded the metric was **replica-proportional** (a genuine
self-sustaining ratchet), the other that it was a **trailing ~240 s arrival
count**. Both were fitted to runs in which arrival rate and burstiness
co-varied, so neither could separate them.

A controlled run was built to break that confound: uniform synthetic `raw://`
traffic at **segment 3's exact arrival rate** (10.7 req/min for 12 minutes,
render ~4.95 s ≈ MAS's p50), with burstiness removed.

| | segment 3 (MAS) | controlled run |
|---|---|---|
| arrival rate | 10.7/min | **10.7/min** |
| mean concurrency | 1.24 | 0.88 |
| **peak in-flight** | **8** | **~2** |
| p99 / max duration | 36 s / 52 s | ~5 s / 6 s |
| **replica high-water** | **30** | **1** |
| scale-up events | 14 | **0** |

`ceil(0.9 / 2) = 1`. **On smooth load the scaler behaved correctly, at the same
arrival rate that drove MAS's run to the cap.** So:

- **Arrival rate is not the driver.** Both fitted models are wrong, including the
  one that predicted ~21 replicas for this exact run.
- **The "ratchets on a load that justifies one replica" framing is wrong** in a
  way that matters: the defect is specific to MAS's traffic *shape*, not to light
  load in general.
- **The driver is burst shape.** Established by the next experiment, below.

### Burstiness is the driver — reproduced, then used as the A/B instrument

The bursty follow-up settled it. Same arrival rate (10.7/min), same render time,
same 9-minute duration, **only the burst shape changed** (`--fanout 4`: four
requests every 22.4 s instead of one every 5.6 s, so peak in-flight 4 instead of
~2):

| | uniform | bursty (`--fanout 4`) |
|---|---|---|
| arrival rate | 10.7/min | 10.7/min |
| mean concurrency | 0.88 | 1.15 |
| **replica plateau** | **1** | **38** |

38× the fleet from the same number of requests per minute. **The scaler responds
to burst shape, not to rate and not to mean concurrency** — and note `ceil(4/2) = 2`,
so it is not computing concurrency ÷ target either. What fits is ACA's documented
scale-up step (1, 4, 8, 16, …) firing on *every* burst with 0 s stabilization,
against a scale-down damped by the 300 s window: each burst ratchets, and the
fleet converges only where the ratchet meets the damping.

**It plateaus.** 38 was a fixed point, held flat for the last four samples — not
a runaway. That matters, because a runaway would not have been fixable by any
trigger value.

### The A/B, run against production

Both arms identical (`--fanout 4`, 10.7/min, 9 min, `raw://`, from cold):

| | **before, trigger 2** | **after, trigger 6** |
|---|---|---|
| requests / status | 104 / all 200 | 96 / all 200 |
| **429s (client-side)** | **0** | **0** |
| **RenderGate rejects** | **0** | **0** |
| max queue depth | 1 of 4 | **1 of 4** |
| max queue wait | 4.8 s | **5.3 s** of the 15 s that 429s |
| mean concurrency | 1.15 | 1.27 |
| p50 / p90 / max | 5.35 / 6.05 / 22.8 s | 5.64 / **10.44** / 19.6 s |
| **replica plateau** | **38** | **5** |
| replica curve | 2,8,12,18,20,23,27,27,34,38,38,38 | 0,1,2,2,2,3,3,4,4,5,5,5 |

**7.6× fewer replicas, no rejections, queue depth unchanged.** The real cost is
**p90 latency +73 % (6.05 → 10.44 s)** from queueing on a smaller fleet — inside
MAS's own production p90 of 9.35 s, and far from the 15 s queue limit and the
180 s fence. p50 barely moved and max improved.

For scale: the after-arm's queue pressure is *lower* than MAS's real segment 3
had at trigger 2 (`queued=3`, `waited=9.9s`) — because that pressure was
cold-start concentration on one replica, which the trigger does not govern.

**Still not established:** whether burst *shape* alone explains it, or whether
TCP connection count contributes (our generator pools connections; MAS's
per-company parallel fetches likely do not, and an ACA maintainer states the
scaler counts "active connections as well as requests"). It does not block the
change — the trigger divides `desired` whatever the numerator is, which the A/B
now demonstrates rather than assumes — but do not inherit a mechanism from this
file. Ask MAS for their client's connection behaviour (message `29-…` §4).

---

## The incident this measurement caused, and what it teaches

**Applying the scale-rule change while the fleet was at 38 replicas took the
environment to its core quota and stranded the new revision.** Recorded in full
because it is a live operational risk that applies to *every* deploy, not just
this one, and because we found it by walking into it.

`az containerapp update --scale-rule-*` — like **any** template change,
including `deploy-image.sh`'s `--image` — mints a **new revision**, and the new
revision needs its **own** replicas while the old one is still draining. Both
count against the environment's 100-core quota at 2 vCPU each. At 38 replicas
(76 cores) the new revision could not create pods:

```
FailedCreate ×25: pods "crawl4ai-service--0000039-…" is forbidden:
  exceeded quota: consumption, requested: cpu=2k, used: 98250, limited: 100k
```

`--0000039` then sat in **`ActivationFailed` / `Unhealthy` with 0 replicas while
holding 100 % of the traffic weight**, and `--0000038` kept serving at 0 %
weight. `/health` returned 200 throughout and every request succeeded — **ACA
being forgiving, not a margin to rely on.** Had the old revision finished
draining first, neither revision would have had a replica.

Three things follow:

1. **Check the replica count before any deploy.** Above ~20 replicas (40 cores)
   a deploy can strand the new revision. That is precisely the condition during
   a MAS sweep — i.e. exactly when someone would want to ship a fix. Now in
   `DEPLOYMENT_INFO.md`.
2. **It is an independent argument for this change.** At the old trigger, a
   routine sweep put us within one deploy of this failure. A ~3× smaller fleet
   moves the risk out of reach.
3. **It invalidated the first after-arm.** Traffic kept being served by
   `--0000038`, whose template snapshot still carries `concurrentRequests: 2` —
   so the "after" run was measuring the *old* setting and its replica curve
   climbed exactly as before. **A revision's scale rule is a snapshot, not a
   live lookup**; during a transition you may be measuring either one. Re-run
   after confirming which revision is actually serving.

## What shipped

1. **ACA scale rule `concurrentRequests` 2 → 6.** One command, no image rebuild.
   Still more eager than ACA's own default of 10.
2. **`azure-deployment/deploy-image.sh`** — the `render_capacity == concurrentRequests`
   check is replaced by a **drift** check of the live rule against a declared
   `ACA_SCALE_TRIGGER=6`, plus a branch for the rule being **missing entirely**
   (in which case ACA silently falls back to 10, which is the original
   2026-07-16 incident).
3. **`azure-deployment/batch-scale.sh`** — it hardcoded `MAX_REPLICAS=30` and
   passed `--max-replicas 30` on **both** `up` and `down`. Running the emergency
   valve would have silently reverted the 30 → 45 raise made the same day, at
   exactly the moment someone reached for it because the fleet was under stress.
   It no longer mentions max-replicas; the live value is the source of truth.
4. **Documentation** — the "MUST match" claim existed in six places
   (`config.yml`, `aitosoft_admission.py`, `CLAUDE.md`, `DEPLOYMENT_INFO.md`,
   `AITOSOFT_FILES.md`, `OVERNIGHT_PLAYBOOK.md`) and is corrected in all of them,
   with the units table and the reasoning rather than just a new number.

### Why 6

- ACA's default is 10 and the 2026-07-16 incident happened at 10, so 6 stays
  meaningfully more eager than the setting that failed.
- At segment 3's shape it predicts ~10 replicas against a peak in-flight of 8
  (which needs 4) — roughly 2× headroom, versus 30 before.
- At the planned 50–100 companies / 4 concurrent it predicts ~13 replicas
  against a need of ~6, keeping us clear of both `maxReplicas: 45` and the
  environment's 100-core quota (45 replicas × 2 vCPU = 90 of 100, shared with
  MAS's `aitosoft-edge`). **The quota is the real operational risk, more than
  the cost.**
- It cannot reduce the fleet below what the gate needs, because the gate is
  independent of it.

**Not chosen: option C (do nothing).** Cash cost is €0, which is the strongest
argument for it. It loses to the quota exposure at sweep scale and to the fact
that the fix is one reversible number. **Not chosen: lowering `--keep-alive`**
(see below). **Not available: option B.**

---

## The lever that was investigated and deliberately not pulled

`gunicorn --keep-alive 300` (`supervisord.conf:23`) was a strong candidate while
the connection-floor hypothesis was live: it is 150× gunicorn's own default of 2 s,
and `UvicornWorker` **does** honour it (`workers.py`: `"timeout_keep_alive": self.cfg.keepalive`),
so it genuinely holds idle connections for 300 s. It was **not pulled — and it is
NOT refuted.** Being precise about this, because the first draft of this section
said "refuted" and that was an overclaim of exactly the kind this repo keeps
recording ("a measurement can be cited for something it does not measure"):

- **The controlled uniform run refuted a *rate* model. It cannot refute a
  *connection* model**, because a client with one request in flight opens one
  connection and therefore never exercises a connection term. The keep-alive
  hypothesis is **untested**, not dead.
- It needs an image rebuild, where the scale-rule change needs none — so it is
  correctly not the *first* lever, regardless of merit.
- A coincidence worth writing down rather than closing over: gunicorn's
  keep-alive is 300 s, and segment 3's first scale-down came **332 s** after its
  last scale-up. That is confounded with the HPA's 300 s scale-down
  stabilization window and the two cannot be separated read-only. It matters
  more now that the bursty run has demonstrated something *accumulates*.
- **What would test it:** a bursty arm with connection reuse disabled (one fresh
  connection per request) against the same rate, versus the pooled arm. If the
  replica curve moves, connections are in the metric.

Other reasons it stays where it is:
- **It is upstream's value, not ours** — `git diff upstream/develop -- deploy/docker/supervisord.conf`
  differs only in `server:app` → `aitosoft_entry:app`. Changing it creates a new
  divergence on a file we currently barely touch.
- The failure mode it risks is a raced idle close, whose signature is
  **503 with `ResponseFlags=UC`, not 502** — so the AWS-style "backend idle
  timeout must exceed the LB's" guidance applies, and ACA's upstream idle
  timeout is undocumented and unsettable (`azure-container-apps#1172`, open).

Two facts worth keeping from that thread: `--threads 4` on the same command line
is **inert** (UvicornWorker ignores it), and `config.yml:12 timeout_keep_alive`
is a **dead knob** — its only consumer is inside `server.py`'s
`if __name__ == "__main__":`, which supervisord never runs.

---

## New tooling, and why it should be reached for first

**`raw://` is a full-fidelity load generator with zero egress.** Verified from
source and by execution:

- `deploy/docker/utils.py:354` returns early for `raw:`/`raw://` **before** any
  DNS or SSRF check; `api.py:692` excludes it from bare-host prefixing.
- `async_crawler_strategy.py:488` still routes it **through the browser**
  (`_crawl_web` → `page.set_content()`) whenever `needs_browser` is true — and
  `remove_consent_popups`, the flag MAS sends on every production request, sets
  it. So a `raw://` request exercises RenderGate (the 429 boundary), the pool, a
  real Chromium launch on a cold replica, the consent pass, scraping, markdown
  and the collapse guard. Only the network navigation is skipped.
- Render duration is a **dial**: `delay_before_return_html` is on the untrusted
  allowlist, and wall time is linear at ~1.3 s overhead + the delay.

This satisfies TESTING.md golden rule 0 outright — there is no live request to
budget, register or burn — and unlike a third party it is byte-identical across
A/B arms. **Reach for it before any live host, and before adding a
`fixture_origin` route, when the thing under test is load shape rather than
markup shape.**

The probes are **committed**, in `test-aitosoft/`:

| file | what it measures |
|---|---|
| `sustained_rate_probe.py` | sustained arrival rate at a chosen burst shape — the **provisioning** side. `--fanout` is the variable that matters |
| `cold_burst_probe.py` | N concurrent from cold — the **safety** side (429s, TTFB, queue pressure) |
| `cold_burst_probe.kql` | server-side readback: rescale ramp, replica high-water, status histogram, RenderGate ADMIT/REJECT |

Neither is collected by pytest (no `test_` prefix; verified — the suite collected
306 at the time, 312 since 2026-08-09; the point is that adding these two did not
change it). They read the token from `CRAWL4AI_API_TOKEN` and never print or
store it, refuse a warm app without `--allow-warm`, and cap `--n`/`--rounds`/
`--rate-per-min`/`--duration-min`.

**The first draft of this file said not to commit them** — "throwaway
instruments, rebuilding is ~30 minutes". That was wrong for two reasons worth
keeping: the new CLAUDE.md row tells every future session *"reach for `raw://`
before any live host"* and would have handed them nothing to reach for; and a
**rebuilt** generator is not a valid B-arm against a **recorded** A-arm, which
is exactly the comparability the third-party target was rejected for failing.
Same family as `guard-corpus-is-not-in-the-repo.md`.

---

## How to read the acceptance run

MAS runs 50–100 companies at `--concurrency 4`. Watch, in this order:

1. **Replica high-water vs what the load justified.** `ContainerAppHTTPLogs` is
   the only table with `RequestDuration`, and its `StartTime` column is arrival,
   so true in-flight concurrency comes from sweeping overlaps — not from
   per-minute bins, which understate the peak by ~3× (that is the mistake in the
   original file). Prediction: **~13 replicas**. Cross-check the count against
   the Azure Monitor `Replicas` metric, which needs no KQL and has no ingestion
   lag.
2. **429 count, and — more importantly — RenderGate queue wait.** `429` is a
   step function that reads 0 right up until it doesn't. Segment 3's zero-429
   record was **one queue slot and 5 seconds from breaking**: `queued=3` of 4 and
   `waited=9.9s` of 15, all in the first 32 seconds on the single cold replica,
   on a run MAS had pre-warmed. **Queue wait is the safety metric.**
3. **`ResponseFlags != "-"` and `UpstreamRequestAttemptCount > 1`.** 30-day
   baseline is 0 and 1. Ingress-side failures leave no `failure_class` and no
   application log line at all — structurally the same blind spot as the 404
   finding, one layer further out.
4. `failure_class=` counts (never the log token — see CLAUDE.md), and the
   `COLLAPSE RECOVERED` / `RENDER DEFECT` split per segment.

**Revert criteria, pre-registered:** any 429 outside the first minute of the
run, or more than one 429 total, or queue wait above 12 s. Revert is
`--scale-rule-http-concurrency 2` plus resetting `ACA_SCALE_TRIGGER` in
`deploy-image.sh` (otherwise the next deploy fails its drift check).

---

## What I am least sure of

1. **Which mechanism actually drives it.** Rate is refuted; concurrency bursts,
   duration tail and connection count are all still live. The change is
   insensitive to which — `desired` is divided by the trigger regardless — but a
   future session sizing anything else here should not inherit a mechanism from
   this file, because this file does not have one.
2. **Whether 6 is enough, or too much.** It is a 3× reduction chosen from a model
   I could not validate synthetically. The acceptance run settles it, and the
   revert is one command.
3. **Whether concentrating the same load onto fewer replicas re-opens the memory
   family.** It was closed at zero across four workloads, but every one of those
   ran on an over-provisioned fleet. `max_browsers: 6` and the 85 % guard are the
   things to watch. This is the risk I would look at first if the acceptance run
   surprises us.
4. **The 12 × HTTP 500 cluster in segment 3** (item 9 above) is unexplained and
   is a bigger cost to MAS than the 429s this task worried about.

## Where everything lives

| thing | where |
|---|---|
| RenderGate, capacity/queue/429 | `deploy/docker/aitosoft_admission.py` |
| `render_capacity` + the corrected comment | `deploy/docker/config.yml:180-215` |
| `ACA_SCALE_TRIGGER`, drift check | `azure-deployment/deploy-image.sh` |
| Scale rule, revert command, dead knobs | `DEPLOYMENT_INFO.md` "Scaling" |
| ACA scale rule (live) | `az containerapp show ... properties.template.scale` |
| Workspace ID for the queries | `PRIVATE.md` |
