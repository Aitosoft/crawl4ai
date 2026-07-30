# Post-deploy measurement: did the five fixes do what we claimed?

**Status:** Open — the only task that is *waiting on someone else*, and the one
that gates three others.
**Priority:** Highest. Not because it is hard, but because until it lands we are
guessing about the size of every remaining decision.
**Effort:** S (our side). **Risk:** none — pure observation.
**Evidence:** `tasks/waa-eval-2026-07-30-forensics.md` §9, §8d

## Why this is a task and not just "wait"

`0.9.2-failure-class` (rev `--0000031`, 2026-07-30 18:24 UTC) shipped five
fixes. **Three of them are not verifiable by us at all** — the reference hosts
are on the do-not-live-test ledger, and the challenge family is intermittent, so
a clean fetch from our egress proves nothing either way. MAS's re-scrape is the
only instrument that reads them.

That makes the measurement a deliverable, not a formality. Three open decisions
are downstream of the numbers it produces.

## What MAS reports back (asked for in the deploy note)

| Population | Size | Predicted outcome | What a miss means |
|---|---|---|---|
| `empty_*` hosts | 70 | **Full content.** 1 byte → whole body, deterministic, no network variable. | Any host still empty is a *second* root cause. Chase it hard — the `<noscript>` diagnosis predicts 70/70. |
| `challenge_*` hosts | 171 | **Split.** Still-challenged ⇒ `success:false` + `origin_blocked`. Withdrawn ⇒ real content. §8d's 5/5 probe says expect a lot of the second. | The split *is* the deliverable — see below. |
| `blockpage_*` hosts | 2 | Unchanged, still blocked. | — |

## What our side watches, in the same window

- `ORIGIN FAILURE` log lines appear and are dominated by `origin_blocked` /
  `origin_http_error`. Expected, and expected to be numerous
  (`OVERNIGHT_PLAYBOOK.md` has the signal row).
- **`failure_class=render_error` must NOT climb.** That is the bucket
  unrecognised failures fall into by design bias, so a rise means the taxonomy
  is mis-sorting something real as ours.
- 500s and 504s should become rare. If they don't, the classification isn't
  reaching a channel — there were two, and finding the second one late is
  exactly how this bug survived the first pass.
- MAS's aggregate success rate **drops**. That is the fix working; it is
  written down in the playbook so nobody rolls back over it.

## What the numbers decide

1. **`residential-egress-retry-path.md`** — the challenge split *is* the
   business case. 171 still blocked ⇒ build it. ~3 still blocked ⇒ close it.
   Nothing else produces this number, and it costs nothing.
2. **`blocked-host-retry-economy.md`** — sizes the wasted-render bill and tells
   us whether the classifier needs to be cheap or merely correct.
3. **`static-mode-tls-impersonation.md`** — if hosts that challenge our Chrome
   serve static fine, TLS impersonation matters; if IP dominates in every
   measured case (as it has so far), it stays a hardening task.

## Done when

MAS's re-scrape numbers are recorded in `waa-eval-2026-07-30-forensics.md` §9,
the three tasks above have had their priority re-set from real figures, and any
still-empty host from the 70 has its own task file.
