# The collapse guard's evidence is not in the repository

**Status:** Open, not started. Opened 2026-08-02 while deploying
`0.9.2-collapse-recovery`, by checking a claim rather than by a failure.
**Priority:** Medium. Nothing is broken in production; what is broken is our
only pre-deploy gate, on any machine that is not this one.
**Effort:** S, but the sizing decision is the whole task.
**Risk:** Low.
**Evidence:** `git clone` of this repo into a temp dir — `test-aitosoft/artifacts/`
does not exist. `git ls-files test-aitosoft/artifacts/` returns exactly one
entry, `.gitkeep`.

## What is wrong

`test-aitosoft/.gitignore` ignores `artifacts/*`. The 140 stored captures under
`test-aitosoft/artifacts/` (35 MB) are **local, untracked files**. Three tests in
the offline suite read them:

| test | what it asserts | on a fresh clone |
|---|---|---|
| `test_thresholds_clear_every_real_capture` | every real capture comes back clean | `assert checked >= 30` — **fails at 0** |
| `test_the_real_corpus_still_shows_the_gap` | healthy pages stay far from the threshold | `assert ratios` — **fails, empty** |
| `test_no_real_capture_is_mutated_by_the_guard` | recovery never rewrites a real capture | passes vacuously, then **fails at 0** |

So `aitosoft_collapse_guard.py`'s central claim — *"`test_thresholds_clear_every_real_capture`
re-derives it on every run, so the constants cannot rot silently while the
constants drift"* — is true **only on a machine that happens to hold the
corpus**. Every threshold in that module, and the `1.311` / `0.10` gap the guard
is shippable because of, rests on files a fresh session cannot see.

This is the same shape as the finding that named it, one level up: *a claim can
be right about the component and wrong about the thing that ships.* The test
does re-derive the evidence. The repository does not contain the evidence.

## Why it went unnoticed

Because the failure mode is "the guard is *more* likely to be wrong", not "a
test goes red in a way anyone sees". Sessions run in this dev container, which
accumulated the corpus over four months of Tier 1 runs, so the suite has always
been green here. `tasks/README.md` records that our only pre-deploy gate is "the
offline suite is green" — that gate is machine-dependent and nobody knew.

It also gets quietly *worse* with use: every Tier 1 run writes a new
`artifacts/<label>/` directory, so the corpus grows and drifts per machine. The
2026-08-02 run added four captures and the guard suite went from 32 to 34 tests
passing without anyone choosing that.

## The decision this needs

**How much corpus, and which.** Not "commit `artifacts/`" — 35 MB, 140 files, 38
of them over 400 KB, and `check-added-large-files` will refuse those anyway.

The populations the thresholds actually rest on are four, and the module
docstring names them: healthy content pages (739–34,172 visible chars),
cookie-wall / JS shells (0 visible), a challenge interstitial (58), and the
fixture collapses. A defensible minimum is **one or two captures per population**
— roughly 6–10 files — with the two count assertions lowered to match and
re-derived from what is committed rather than from what happens to be on disk.

That trades statistical weight for reproducibility. State the trade in the test,
because the current `>= 30` is doing real work: it is what catches "somebody
pointed the glob at an empty directory".

Options, and none is obviously right:

| | for | against |
|---|---|---|
| commit a 6–10 capture subset under `artifacts/keep/` (the mechanism `.gitignore` already provides for exactly this) | reproducible, small, uses what exists | weaker evidence than 140 files; someone must choose the subset honestly |
| commit all captures under 400 KB | closest to today's evidence | still megabytes of customer HTML in a **public** repo |
| generate the corpus instead — a fixture-origin route per population | no customer bytes at all, fully reproducible | synthetic, and the whole point of this corpus is that it is *real* pages |
| leave it, and delete the `>= 30` assertions | honest about what is checked | throws away the guard's only false-positive test |

**Read `.gitignore`'s own comment before deciding** — it already anticipated
this: *"Allow deliberately-kept results (copy them into keep/ by hand)."* The
mechanism exists and was never used.

## The part that is not a decision

Whatever is chosen, **this repository is public** (CLAUDE.md, Security). Stored
captures are full HTML of real customer sites. Nothing in them is a secret by our
own rule — "facts and reasoning stay public", and crawled hostnames are already
tracked — but committing megabytes of a third party's markup is a different act
from recording that we crawled them. Worth one deliberate thought rather than
none.

## Verification

- `git clone` into a temp dir, `pytest test-aitosoft/test_collapse_guard.py`,
  and it must pass. That is the whole test for this task, and it is the check
  nobody had run.
