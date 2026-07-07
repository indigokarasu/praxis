# Cron Ingest 2026-07-07T02:05Z — Steady-State Confirmation

**Run ID:** `cron-ingest-0205z`
**Date:** 2026-07-07
**Trigger:** Scheduled cron (30-min cadence)

## Summary

Routine steady-state cron ingest. All known production script bugs active but mitigated by post-ingest checklist.

| Metric | Value |
|--------|-------|
| Journals on disk | 13,984 |
| New journals processed | 1 (mentor-light) |
| Events recorded | 1 (`no_signal`) |
| Gap journals backfilled | 1 |
| Lessons extracted (Bug 2) | 14 |
| Noise lessons cleaned | 14 (all removed — missing `signal_type` key) |
| Active shifts | 3/12 (healthy) |
| Stale scripts cleaned | 0/10 threshold |

## Bug Confirmation (All Still Active)

| Bug | Status | Mitigation |
|-----|--------|------------|
| Bug 1: Date filter too narrow | Confirmed — gap backfill caught 1 journal | `gap_backfill.py` post-run |
| Bug 2: Full-history lesson reprocessing | Confirmed — 14 noise lessons from 3,821 events | Fast pre-filter + `cleanup_noise_lessons.py` |
| Bug 3: Eval file ID format mismatch | Not triggered this run | Gap backfill catches |
| Bug 4: Double-Z timestamp | Not triggered this run (shell heredoc used) | Shell heredoc with `TS_SHORT="${TS%Z}"` |

## Key Validations

### Fast Pre-Filter Works
- **Condition:** All events in current run = `no_signal` (1 event, mentor-light routine journal)
- **Action:** Skip per-lesson inspection, clear all lessons from run
- **Result:** 14 Bug-2 lessons removed in single operation
- **Reference:** `references/session-20260629-cron-ingest-1404.md` (first validation), `references/session-20260630-cron-ingest-0140.md` (second), this run (third)

### Noise Lesson Cleanup Fix Works
- **Script:** `cleanup_noise_lessons.py` (patched 2026-07-01)
- **Fix:** Checks `les.get("signal_type") is None` (missing key) not just `"?"`/`""`
- **Result:** All 14 lessons caught — breakdown: `missing_signal_type=14, confidence_low=0, noise_signal_type=0`
- **Reference:** `references/noise_lesson_cleanup.md`, `references/session-20260701-cron-ingest-1231.md`

### Decay Check Uses `last_reinforced_at` (Not `activated_at`)
- **Active shifts:** 3 (custodian, mentor, spot)
- **All reinforced:** 2026-06-28T10:09:10Z (~9 days ago)
- **Reinforcement counts:** 4, 2, 1 respectively
- **Age from `last_reinforced_at`:** 9 days → healthy (TTL 14 days)
- **Age from `activated_at`:** 19 days → FALSE decay risk
- **Confirmation:** Gotcha in skill (`Decay age computation: use last_reinforced_at, NOT activated_at`) is correct

### Post-Ingest Checklist Executed Fully
1. ✅ Ingest state updated (`eval_gaps_backfilled: 19`, `gap_journals_backfilled: 2`)
2. ✅ Gap backfill executed (`+1 journal`, eval file 49,171 lines)
3. ✅ Noise lesson cleanup (14 removed)
4. ✅ Stale script cleanup (0 `.py` files outside `scripts/`)
5. ✅ Decay scan (0 risk, 0 stale proposed)
6. ✅ State finalized with all metrics

## Steady-State Indicators

- **Gap backfill rate:** ~1 journal per cron run (date filter miss persists)
- **Bug-2 noise lessons per run:** 10-15 (full-history reprocessing)
- **Active shifts:** Stable at 3 (cap 12, 25% utilization)
- **No genuine behavioral signals** in 7+ days (all `no_signal` events)
- **No stale proposed shifts** (15 expired 2026-06-30 decay check)

## Files Touched

- `skills/ocas-praxis/scripts/praxis_ingest_run.py` (production, bugs unfixed)
- `skills/ocas-praxis/scripts/gap_backfill.py` (working)
- `skills/ocas-praxis/scripts/cleanup_noise_lessons.py` (patched 2026-07-01, working)
- `commons/data/ocas-praxis/ingest_state.json` (updated)
- `commons/data/ocas-praxis/lessons.jsonl` (cleared)
- `commons/data/ocas-praxis/shifts.jsonl` (unchanged, 3 active)
- `commons/journals/ocas-praxis/2026-07-07/praxis-cron-20260707T020510Z.json` (written)