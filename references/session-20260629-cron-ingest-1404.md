# 2026-06-29 Cron Ingest 14:04Z — Bug-2 Filter Confirmation

**Run:** #166 | **Outcome:** success (routine, no genuine signals)

## Summary

- 7 journals scanned, 4 events recorded (3 no_signal, 1 failure_keyword from dispatch)
- 13 lessons produced — ALL were Bug-2 noise with `signal_type=None` (key missing entirely)
- Fast pre-filter applied: all events were no_signal → all lessons archived without per-lesson inspection
- 0 gap journals backfilled
- Active shifts: 3/12, all healthy (age=1d, reinforced)

## Key Observation

The 2026-06-29 Bug-2 cleanup filter fix (`les.get("signal_type") is None` check) was confirmed working. All 13 lessons had the `signal_type` key **absent** from the dict (not set to `"?"` or `""`). The fast pre-filter ("all events no_signal → all lessons noise") correctly identified this without needing per-lesson checks.

## Lesson

When all events in a run are `no_signal`, skip per-lesson signal_type inspection entirely. Archive all produced lessons and clear `lessons.jsonl`. This is both faster and more reliable than filtering individual lessons.
