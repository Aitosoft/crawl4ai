# `config.yml` `base_config` silently drops every boolean setting

> **CLOSED 2026-08-09 — diagnosis confirmed, fix §1 obsolete, `config.yml` line
> commented out. Do not re-open to change the merge rule.**
>
> The diagnosis below is correct and was re-verified by execution on 2026-08-09
> (`api.py:876-880`; `False == None` is False and `False == ""` is False, so a
> boolean can never be applied). What changed is that **its entire "Fix §1"
> premise — that the merge rule is the lever — is wrong.**
>
> `CrawlerRunConfig` is decorated `@_with_defaults` (`async_configs.py:1329`),
> the same mechanism `aitosoft_entry.py:40` already uses for `BrowserConfig`. So
> **`CrawlerRunConfig.set_defaults(simulate_user=True)` sets the boolean today**,
> with no change to `api.py` at all — and it is *better* than the proposed fix,
> because `_with_defaults` keys on presence in `kwargs` rather than truthiness,
> so a client's explicit `false` still wins. The §1 redesign's own stated cost
> ("a client explicitly sending `simulate_user: false` becomes
> indistinguishable from not sending it") is simply avoided. Verified end to end
> through `CrawlerRunConfig.load(body, provenance=UNTRUSTED)`, including
> `clone()` preservation and per-instance deep-copy of default objects.
>
> **Decision 2 is unchanged and still unanswered: nobody has measured whether
> `simulate_user` should be on, and nobody has missed it in the ~10 months it
> has been off.** So the line is not being restored by another route. It is
> **commented out** in `deploy/docker/config.yml` with the reason inline —
> deliberately not deleted, so the next reader finds the history rather than a
> blank. Commenting it out also removes a landmine: as written, anyone who
> "fixed" the merge rule would silently turn user simulation on for every
> request on a 2 vCPU replica.
>
> **What would re-open this:** someone wanting user simulation on, which is
> decision 2 and needs a measurement, not a merge-rule change. Do it with
> `set_defaults`.
>
> Nothing about `total_timeout` changed — it is `None`-defaulted, it applied all
> along, and it is still the only key in `base_config`.

**Status:** Open — diagnosed and proven, fix deliberately NOT bundled with the
2026-07-30 deploy (see "Why not now").
**Priority:** Medium. Nothing is broken today; one setting we believe is on has
been off since it was added, and the next boolean anyone adds will be too.
**Effort:** S (fix) + M (verifying what turning `simulate_user` on actually
costs). **Risk:** medium — the fix changes render behaviour on every request.
**Evidence:** triaged 2026-07-30 from the WAA side-findings list; reproduced
offline.

## Problem

`api.handle_crawl_request` merges `config.yml`'s `crawler.base_config` into the
request's `CrawlerRunConfig` with this rule:

```python
# deploy/docker/api.py
for key, value in base_config.items():
    if hasattr(crawler_config, key):
        current_value = getattr(crawler_config, key)
        if current_value is None or current_value == "":   # <-- here
            setattr(crawler_config, key, value)
```

"Unset" is defined as `None` or `""`. Every boolean knob on `CrawlerRunConfig`
defaults to `False`, and `False` is neither — so a boolean in `base_config` can
never be applied. Reproduced:

```
simulate_user: current=False  applies=False    <- config.yml says true; stays False
total_timeout: current=None   applies=True     <- applied correctly
```

**`simulate_user: true` (deploy/docker/config.yml:81) has therefore never taken
effect for a single request.** It is also in `aitosoft_trust.py`'s relaxation
list, so a client *can* set it — MAS does not. `total_timeout` and the other
`None`-defaulted settings are unaffected and work as documented.

## Why not now

Fixing the merge rule turns `simulate_user` on for every request at once. That
is a real behavioural change — mouse-move and click emulation before capture,
on a 2 vCPU replica with `render_capacity: 2` — shipped into the same image as
the failure-classification contract change, with no measurement of what it costs
in latency or what it buys in block rate. The deploy it would have ridden along
with exists to make block detection safe; this would have added an unmeasured
variable to exactly the population we need to watch.

## Fix

Two independent decisions — do not conflate them:

1. **The merge rule.** Treat "unset" as "equal to the field's default" rather
   than "None or empty string". `CrawlerRunConfig` is a plain class, so compare
   against a pristine `CrawlerRunConfig()` instance:
   ```python
   _defaults = CrawlerRunConfig()
   if current_value == getattr(_defaults, key, None):
       setattr(crawler_config, key, value)
   ```
   Note the semantic shift this carries: a client explicitly sending
   `simulate_user: false` becomes indistinguishable from not sending it. That is
   acceptable for our single trusted client but should be stated in
   `AITOSOFT_CHANGES.md`, not discovered later.

2. **Whether `simulate_user` should be on at all.** Decide with numbers, not by
   restoring an intent nobody measured. Run the Tier 1 four with it on and off
   and compare wall-clock; then decide. If the answer is "no", delete the line
   from `config.yml` rather than leaving a setting that lies about itself.

## Verification

- Offline: assert a boolean in `base_config` reaches the effective config.
- Assert `total_timeout` still applies (it is the one that matters for the
  render-hang fix and must not regress).
- Tier 1 regression 4/4, with wall-clock recorded on both sides of the change.
