# 2026-06-15 Cron Ingest — Full Scan Validates Date-Window Fix

## What happened

The cron ingest ran with the corrected "scan ALL date directories" fix (removed `if date_dir in (today, yesterday)` filter). This was the first production run after the fix was applied to `ingest-script-pattern.md`.

## Results

- **592 new journals** discovered (previous runs found 0-4 due to narrow date window)
- **35 events** extracted after dedup by `(source_journal, signal_type)`
- **9 behavioral signals:** 8x coverage_gap (ocas-mentor), 1x execution_error (ocas-mentor)
- **26x no_signal** filtered (forge empty scans, spot inactive sweeps)

## Key findings

### coverage_gap pattern confirmed
Lesson `coverage_gap/planning` updated 1→9 events. Mentor evaluation_coverage consistently 0.03-0.24 (below 0.5 threshold). Root cause: mentor script dedup logic undercounts new files.

### Shift activation blocked by cap
12/12 active shifts, all reinforced today. No merge candidates for coverage_gap/ocas-mentor.

### Date window fix validated at scale
592 journals found vs. 0-4 on prior runs confirms the date-window filter was the primary miss cause. Cron jobs writing to future-dated directories were invisible to the old filter. journals_evaluated.jsonl dedup is the correct gatekeeper.

## Decisions

1. Lesson update (not new): coverage_gap/planning 1→9 events, dedup prevented duplicate
2. Shift activation skipped: at cap, all fresh, no merge candidates
3. No-signal filtering: 583 events correctly suppressed

## Scripts

- `scripts/ingest_20260615_cron.py` — main ingest
- `scripts/lesson_extract_20260615.py` — lesson extraction with content dedup
- `scripts/decisions_20260615.py` — decision logging
