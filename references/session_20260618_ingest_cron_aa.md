# 2026-06-18 Cron Ingest (r_20260618_073841_45d1f91a)

## Summary
Routine cron ingest. 15 new journals scanned (all no-op). 10 new lessons extracted from event backlog. 17 shifts proposed, all rejected at 12/12 cap. Post-hoc cleanup removed 3 noise lessons and 8 orphaned shifts. Final: 11 active shifts, 33 lessons, 2519 events.

## Key Finding: Noise Filter Gap in Lesson Extraction Pass 1

**Problem:** The ingest script applied `NOISE_SIGNAL_TYPES` filtering during event recording but NOT during lesson extraction Pass 1 grouping. This allowed noise signal types that already existed in `events.jsonl` (from prior runs) to be grouped and extracted as lessons.

**Specific noise lessons produced:**
- `mentor_light/Execution` — 288 events (routine heartbeat, not behavioral pattern)
- `coverage_gap/Planning` — 11 events (scan-yield measurement artifact)
- `coverage_gap/planning` — duplicate with different case

**Root cause:** The "Lesson Noise Gate" section of `ingest-script-pattern.md` documents the filter as MANDATORY, but the Pass 1 code template in "Lesson Extraction — Two-Pass Pattern" does NOT include the noise check in the grouping loop. The inline script I wrote followed the code template, not the prose requirement.

**Fix:** Add explicit noise filter check in Pass 1 BEFORE creating lesson stubs:
```python
for (st, phase), events in event_groups.items():
    if len(events) < 2:
        continue
    if (st, phase) in existing_groups:
        continue
    if st in NOISE_SIGNAL_TYPES:  # THIS CHECK WAS MISSING
        continue
    # ... create lesson stub ...
```

**Verified:** Post-hoc cleanup removed the 3 noise lessons and 8 orphaned shifts. Final state clean.

## Shift Cap Status
- 11 active shifts (1 slot freed by cleanup)
- All 11 active shifts have 0 reinforcements, 12+ days old
- 17 proposed shifts queued (including high-value: security_alert, parse_error, calendar_conflict)
- Decay check overdue — all shifts approaching 14-day TTL

## Micro-Lessons
1. `mentor_light` is routine heartbeat noise — 288 events in backlog, should never become a lesson
2. `coverage_gap` is scan-yield measurement artifact — not a behavioral pattern
3. Cap saturation at 12/12 with 0 reinforcements = system not learning, just accumulating
4. Lesson extraction reads from FULL event pool (2519 events) — noise filter must apply at grouping time, not just event recording time
