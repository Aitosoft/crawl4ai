# The wall-clock fence test is load-flaky, and nobody has established why

**Status:** Open, not started. Carved out of `cleaned-html-collapse-guard.md`'s
verification notes on 2026-08-02, where it was a loose thread rather than a task.
**Priority:** Medium, and higher than its size suggests — see "Why this is not
cosmetic".
**Effort:** S to fix, **but the diagnosis comes first and may not be S.**
**Risk:** low for the test change; the diagnosis could surface a product finding.
**Evidence:** observed by the 2026-08-01 session — failed once in three full
suite runs, passed in two of the coordinator's checks. Pre-existing; untouched by
the collapse-guard work.

## The test

`test-aitosoft/test_fixture_origin.py:640`:

```python
outcome = production_path.crawl(
    fixture_origin.url("/ok", stall=3),
    wall_clock_s=1,
    delay_before_return_html=SHORT_WAIT,
)
assert outcome.http_status == 504
assert outcome.envelope is None
assert outcome.elapsed_s < 3, "the fence must fire before the origin answers"
```

The origin stalls 3 s, the fence is set to 1 s. The `elapsed_s < 3` assertion is
what makes the 504 mean *"we gave up"* rather than *"the origin failed"* — it is
load-bearing and should not simply be deleted.

But it leaves only **2 s for everything that is not the fence**: pool
acquisition, browser launch or reuse, page setup, the cancel, and teardown. A
fully-loaded suite run sometimes does not fit in it.

## Why this is not cosmetic

Our entire pre-deploy quality gate is *"the offline suite is green"* — 232 tests,
no live traffic, and a deploy proceeds on that signal. A test that fails ~1 run
in 3 for reasons unrelated to the code trains sessions to re-run and wave it
through, and the next session inherits "that one is always flaky" as folklore.
CLAUDE.md already records this exact failure mode in the security section, about
a secret-check pattern that always cried wolf: *"a check that always cries wolf
is worse than no check."* Same defect, different gate.

## Establish which of two things it is BEFORE changing the assertion

They look identical from a red test and they have opposite consequences. Do not
widen the margin until you know which one you have.

1. **Harness overhead.** Pool + page + teardown genuinely takes >2 s under a
   loaded suite. Then the test is measuring the harness, the assertion's *margin*
   is wrong, and widening it is the whole fix.
2. **The fence itself is slow to unwind under load.** The fence cancels an
   in-flight render; if cancellation sometimes takes seconds, **that is a product
   finding, not a test problem.** Our production fence is `wall_clock_s: 180` and
   the Azure ingress limit is 240 s — a fence that overruns by an unbounded
   amount eats that 60 s of headroom, and MAS sees a hung connection instead of
   the 504 their client is documented to treat as terminal (2 consecutive on a
   host pivots them to static). This is the reading that would make the task
   worth more than its size.

The instrument already exists: time the phases separately rather than asserting
on the total. `production_path` and `FixtureOrigin.hits_for()` can distinguish
"the origin was never allowed to answer" from "we took a long time getting to the
fence".

## Direction, once the diagnosis is in

If it is (1), the honest fix is to widen the *gap between the fence and the
origin's answer* rather than to loosen the assertion — raise `stall` so the
assertion keeps meaning "before the origin answers" with real slack, instead of
raising the threshold until it stops failing. **Check what a longer stall costs
the fixture server first**: a server-side sleep may hold a worker for its full
duration even after the client has gone, and a suite that pays that on every run
has traded a flaky test for a slow one.

If it is (2), the test is telling the truth and the fence is the thing to fix.
Write the finding up before touching the assertion.

Either way, record the measured phase split in this file. "We widened it and it
went green" is the outcome that leaves the next session exactly where this one
started.

## Verification

- Offline, no live traffic, no Azure. `test_fixture_origin.py` and
  `fixture_origin.py` are 100 % ours.
- Run the full suite ≥5 times, not once — the failure is load-dependent and a
  single green run proves nothing. State the observed pass rate in this file.
- Do not deploy for this. It rides along in whatever image ships next.
