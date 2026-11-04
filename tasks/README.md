# Open tasks, in the order to do them

**Updated 2026-11-04 (evening).** Each task file carries the concern, the evidence and the design
space, and deliberately no checklist. You're expected to challenge it and record what you found
wrong in the file itself; that has happened on nine consecutive task files, and it is the quality
gate that works. Where a task file and this index disagree, the task file wins.

## State of the world

- **Production is `0.9.5-http-as-asked` on `crawl4ai-service-se` (Sweden Central)**, by digest,
  Google Chrome 157. It's v0.9.5 plus one Chrome `--disable-features` switch carrying two features
  (`HttpsUpgrades`, `HttpsFirstBalancedModeAutoEnable`), from 2026-11-04 (AITOSOFT_CHANGES, the two
  top entries; it must stay the *last* such switch, FINDINGS). Query the live state with `az` (AZURE_OPERATIONS §0). **`main` ==
  production + docs.** Verify it.
- **The West Europe app (`crawl4ai-service`) is kept**, idle at zero, as a second egress: some hosts
  drop our Sweden Central addresses and accept West Europe's (decision below). MAS holds its
  deletion, which was planned for 11-11.
- **From ≈2026-11-08, MAS's production traffic arrives unannounced** (`131-from-us-…`): campaign runs
  from their edge at 1–5 in flight, at any hour. Deploys and fleet changes now have live-traffic
  gates. The procedure lives in AZURE_OPERATIONS §2.1. Scale-in kills in-flight renders again
  outside windows (`optimization-experiments.md` lever 3).
- **Optimisation series 1 with MAS closed on 2026-11-04** after five windows on real prospects
  (`optimization-experiments.md`, ledger and "What series 1 established").
  - A fleet fixed at 2 replicas is the standing setup for MAS's windows, and it makes our cost
    predictable: 0.40–0.47 ¢ per company (0.55 measured in window 5, with a warm-up we
    lengthened by mistake), against 0.43–0.64 ¢ when the scaler chose.
  - Identical windows differ by ~±10 %.
  - The windows found two Chrome regressions no offline suite could see; both are fixed.
- **What the August sweep says about priorities.** 186,178 requests over 175 h. Of MAS's 60,874
  capture attempts, 86.1 % were stored and **95 % of failures were the origin's**. Our share, in
  captures lost: 500s 156 (152 of the 163 URLs failed on every attempt, so deterministic: item 1),
  429s 29, `render_defect` 27, `unrenderable_content` 4. Size any new defect against those numbers.

## Open items

| # | Task | Size | Why now |
|---|---|---|---|
| **1** | `deterministic-failures-are-terminal.md` | S | Acked by MAS (`131-…`). Three shapes that 500 on every attempt (inline-PDF shell, both-tiers-empty JS shell, `ERR_HTTP2_PROTOCOL_ERROR`), loopback DNS mislabelled 400 `bad_request`, and the one-word `render_mode` mislabel. One announced deploy. |
| **2** | `https-connect-failure-http-retry.md` | S–M | MAS asked for it. Up to 137 archive companies failed https at the tunnel and stored nothing; not yet split into ~1 s refusals (this task) and ~30 s timeouts (lever 12). A marked `http://` attempt. MAS acks the field name first. |
| **3** | `optimization-experiments.md` | M per lever, ongoing | The loop continues when either side has a lever (MAS's next is likely `task-609`). The protocol, the ledger and levers 1–13 live there. |
| **4** | `file-upstream-prs.md` | M | File the two PRs a maintainer can verify alone. Close #2114 only once upstream fixes #2416. |

## Waiting on a decision (Tero and MAS's owner)

- **Some hosts drop our Sweden Central egress** (`optimization-experiments.md` lever 12;
  AZURE_OPERATIONS §7). The A/B was one static request to jekura.fi: it timed out through `-se` and
  returned 200 through the West Europe app. MAS's archive: companies with a tunnel failure, 2.4 %
  since the move (n = 11) against 1.4 % before, a lead. Options:
  - (a) a marked fallback through the West Europe app for ~30 s connect timeouts (both sessions'
    preference);
  - (b) a static egress address for `-se`;
  - (c) move the crawler back to West Europe;
  - (d) residential egress.

**Decided 2026-11-04 (Tero deferred both to us):** the API token in old images is not rotated and the
old tags stay as rollback targets (nothing reached the open internet; `upgrade-upstream-v0.9.5.md` §8
item 5). The 630 raw pages from run (ii) are kept as the offline corpus.

---

## Parked on purpose: don't pick these up unasked

- **CI could run the browser suite on real Chrome.** GitHub's `ubuntu-latest` has Google Chrome
  preinstalled, and `fixture_origin._resolve_channel()` picks it automatically. Day one,
  `pdf-inline` goes red for the true reason, until item 1 fixes it. Item 1 makes this cheaper.
- **Dead-browser replacement (upstream `3f9f790`, on develop after v0.9.5).** It replaces pooled
  browsers whose Chromium process died. How often that happens in production is unmeasured. It
  lands in our most-modified file and carries a silent trap (an auto-merged janitor block calls
  helpers that don't exist on our side; `upgrade-upstream-v0.9.5.md`). **Make it a task only with a
  measured frequency**, or when the next sync brings it in anyway.
- **`residential-egress-retry-path.md`.** It aims at IP-based blocks, which dominate, and now at
  lever 12 too. But it needs an instrument neither repo has: a real browser from a residential IP.
- **`guard-corpus-is-not-in-the-repo.md`.** XS. Four tests fail on a fresh clone because
  `test-aitosoft/artifacts/*` is gitignored. It fails loudly, in the safe direction. Commit 4–6 files
  to `artifacts/keep/`, or delete the task. Don't open its sizing table.
- **`test_fingerprint.py` has been broken since v0.9.2** (it sends `js_code`, which gets a 400).
  `test_soak.py` breaks the live-site rules (327 live requests in its stored run). Fix or delete each
  one when someone next needs it; until then, don't run them.
- **The egress proxy may answer with its own 400 on an idle socket.** `_handle` writes `_BAD` when
  an idle client socket times out after 30 s (`egress_proxy.py`). A stalled plain-http navigation
  once got that 400 (the upgrade's trial merge, not reproduced). Plain-http traffic grew on
  2026-11-04 when `HttpsUpgrades` went off. So count `origin_http_error` with status 400 on
  `http://` URLs in any readout; none seen in window 5 (its two 400s were loopback DNS, not this).
- **The response-size backstop and the `colspan` amplifier.** Pathological markup only, and never
  seen in production (FINDINGS §Output). Raise its priority if a real instance appears.
- **Scale-trigger or `render_capacity` changes.** The scaler is burst-driven (AZURE_OPERATIONS
  §3.2); a fixed fleet does what a trigger can't (`optimization-experiments.md` lever 2).
- **Memory work.** Closed by two repos independently (`tasks/done/post-sweep-closure-2026-08-17.md`).
  Reopen only if a memory stall costs work (AZURE_OPERATIONS §6.4). Peak `anon` in the 2026-11-04
  windows was 2.7–3.5 GB of 4 GiB, with no kill.

## Open threads that need someone else's data

- **53 captures came back with no `<body>` element**, on 28 hosts (`etlistat.fi` ×15). On 26 of the 28
  hosts our consent JS logged nothing, so it is not the cause. Worth a task only if it grows, or if
  MAS can hand over the bytes.
- **Text after an inline `<style>`, `<link>` or `<meta>` is dropped (upstream #2416, open).**
  Measured 2026-11-04 on 630 real WAA raw pages: **0 change** (FINDINGS §Parse collapse). Take
  upstream's fix when it ships; don't build ours. We keep `strip_noscript` until then.
- **PDF text extraction.** MAS holds April captures with extracted PDF text; today an inline PDF
  returns Chrome's viewer shell (item 1 makes that terminal, not readable). Upstream ships `pypdf`
  and an opt-in PDF path. MAS's extension filter keeps PDF links out of the agent's menu, but not
  out of URLs it reads in page text (`96-from-us-…`).

## Reference, not a task

`upgrade-upstream-v0.9.5.md` (done) and `waa-eval-2026-07-30-forensics.md` stay in `tasks/` because
code comments cite them by path. **Many other code comments cite `tasks/<name>.md` for files that
have since moved:** look in `tasks/done/<name>*.md` (a few names were changed on the move; grep
`tasks/done/` for the topic). The second is the evidence base for the five root causes behind the
2026-07-30 image.

## Cross-repo state

The MAS thread is direct, session to session over Remote Control (CLAUDE.md §Cross-repo). Messages
are filed in gitignored `tmp/mas-repo-messages/`; cite filenames, never integers. A session's listed
name changes with its title, so find it with `ListAgents`, or reply to the latest message's `from`.
MAS's `task-608` closed after window 5 (`129-…` to `132-…`), with our open items in its follow-ups.
Owed to MAS: items 1 and 2 deployed, announced; the http retry's field name proposed before it's
built. The thread is at `132-…` (2026-11-04).
