# Session: 2026-06-20 Praxis Cron Ingest (06:13Z)
# Run ID: r_20260620_061308_9f1eb673

## Summary
- 10 unevaluated journals across both paths (legacy + indigo profile)
- 1 legitimate event: `correction` from ocas-custodian (2 Tier-1 fixes applied)
- 1 false-positive removed post-hoc: `failure_keyword` from custodian summary "error jobs remain transient"
- 0 new lessons (only 1 event, no ≥2 group)
- Active shifts: 12/12 (cap full)

## New Gotcha: Summary signal suppression gap
- `should_suppress_summary_signals` only suppresses when ALL signals are summary-derived
- When a journal has BOTH `correction` (from fixes_applied) AND `failure_keyword` (from summary "error jobs remain transient"),
  the suppression is skipped because `correction` is a non-summary signal
- Fix: secondary filter — if `failure_keyword` coexists with non-summary signals, check summary for transient/stable
  phrases ("transient", "stable", "remain", "all errors transient", "no new") and remove the failure_keyword

## Custodian Tier-1 Fixes Recorded
1. `tier1-pause-resume-31889beac268` — custodian:light interpreter shutdown → pause/resume reset
2. `tier1-script-flag-b298d37664ca` — thread-renamer:active missing --active flag (config drift after 3105 runs)

## Key Files
- Ingest script: `scripts/ingest_cron_20260620.py`
- Gotcha updated: `references/gotchas-praxis.md` (new entry: "Summary signal suppression gap when mixed with non-summary signals")
