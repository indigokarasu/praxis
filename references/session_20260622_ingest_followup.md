# Session 2026-06-22 — Praxis Journal Ingest (Follow-up)

## Summary
Cron ingest run at 2026-06-19T02:29 UTC (follow-up to 01:56 partial run). 6 new journals scanned, 0 events, 0 lessons (1 duplicate removed), 0 shifts.

## Journals Processed
- **ocas-mentor** `mentor-light-20260619T022316Z.json`: `no_signal` (mentor-light routine)
- **ocas-mentor** `mentor-light-20260619T015748Z.json`: `no_signal` (mentor-light routine)
- **ocas-custodian** `light-scan-2026-06-18T190000-0700.json`: `no_signal` (custodian routine)
- **ocas-forge** `r_20260618_journal-scan-1781835543.json`: 0 signals
- **ocas-elephas** `run_cron_20260619_020605.json`: `no_signal` (elephas routine)
- **ocas-spot** `sweep_20260618_191127.json`: `no_signal` (spot routine)

## Key Finding: Lesson Dedup Failure Due to Phase Case Mismatch

A new `coverage_gap` lesson (`les-202606190229-0005`) was created with `failure_phase: "planning"` (lowercase). An existing lesson (`les-20260618T100919-coverage_gap-Planning`) had `failure_phase: "Planning"` (capitalized). The dedup check uses exact string comparison on `(signal_type, failure_phase)`, so `("coverage_gap", "planning")` ≠ `("coverage_gap", "Planning")`. The duplicate referenced 9 legacy events from June 13-15 — a stale re-extraction from the full event history.

**Fix applied:** Duplicate lesson removed post-hoc.

**Required ingest script fix:** Before lesson dedup comparison, normalize `failure_phase` to lowercase:
```python
phase_key = les.get("failure_phase", "execution").strip().lower()
dedup_key = (les.get("signal_type", ""), phase_key)
```
This ensures `Planning`/`planning`/`PLANNING` all map to the same key. The same normalization must be applied to BOTH the new lesson's key AND the existing lesson's key when building the dedup set.

Also affects Pass 1 grouping — events with `failure_phase: "Execution"` and `"execution"` should group together. Normalize before grouping.

## State After
- Events: 2,535 (unchanged)
- Lessons: 46 (unchanged — 1 added, 1 removed)
- Shifts: 230 (unchanged)
- Evaluated journals: 16,801 (+6)
- Active shifts: 12/12 (at cap)

## Cleanup
- ingest_cron_20260622.py removed from data dir
- 1 duplicate lesson removed
