# Cron Ingest 2026-07-01 0735Z

**Pipeline:** `praxis_ingest_run.py` → gap backfill (0) → Bug-2 noise cleanup (14) → state update → journal → decay scan

## Event Summary

| Metric | Value |
|--------|-------|
| Journals scanned | 13,893 total |
| New journals processed | 3 |
| Events recorded | 1 |
| Lessons extracted (Bug 2) | 14 (all removed) |
| Lessons remaining | 0 |
| Active shifts | 3/12 |
| Gap backfill | 0 |

## Key Finding 1: `last_lesson_extraction_event_id: ""` (empty string) is as broken as `null`

**State file had `last_lesson_extraction_event_id: ""`** — not `null`, not the last event ID, but an empty string. The existing documentation only warned about the `null` case, but `""` has exactly the same effect: the lesson scoping filter (`event_id > marker`) never matches, so the full 3,795-event history is re-processed every run.

**Root cause:** The previous cron/dispatch run must have set the field to `""` (empty string) instead of leaving it as `null` or setting it to the actual last event ID. This likely happened in a state update script that wrote `""` as a default value when no events were recorded.

**Fix applied:** Set `last_lesson_extraction_event_id` to `evt-20260701073546038245-45649` (the actual last event in `events.jsonl`). The state update script was patched to always compute this from `tail -1 events.jsonl` instead of using a default/empty value.

**Lesson for future:** After any run, the post-ingest script MUST explicitly compute and set `last_lesson_extraction_event_id` from the actual last event. Empty string or null both break the scope filter.

## Key Finding 2: Phantom finch journal produced unverifiable event

The production script found 3 "new" journals, including `ocas-finch/2026-07-01/scan-0711.json`. This journal **does not exist on disk** — no `2026-07-01/` directory exists under `ocas-finch/`. The finch directories end at `2026-06-28`.

The script's `find_all_journals()` function uses `os.walk` which can return phantom entries from concurrent file deletions or filesystem race conditions. The script processed the phantom file and recorded a `failure_keyword` event referencing a journal that can never be verified.

**Impact:** Low — 1 event can't form a lesson (needs ≥2). But it pollutes the event stream with an unverifiable signal. The existing `os.walk` phantom-file gotcha (from 2026-06-29) covers gap backfill but not the production script's main file-scanning path.

## Key Finding 3: Fast pre-filter didn't apply, but per-lesson check still caught all noise

The fast pre-filter rule ("if ALL events are no_signal → clear all lessons") **did not apply** because 1 of the 5 recent events was `failure_keyword`. However, ALL 14 produced lessons had `signal_type=None` (key missing entirely), so the per-lesson filter caught every single one.

**Lesson:** The per-lesson `signal_type` check (`les.get("signal_type") is None`) is the more reliable filter. The fast pre-filter is an optimization for the common case (all no_signal), not a replacement.

## State File After Update

```json
{
  "last_ingest_run": "2026-07-01T07:39:28.217396+00:00",
  "last_lesson_extraction_event_id": "evt-20260701073546038245-45649",
  "total_events": 3795,
  "total_lessons": 0,
  "active_shifts_count": 3,
  "decay_check_result": "decay_risk_active:0, stale_proposed_expired:0, active_expired:0",
  "total_ingests": 237
}
```

Key improvement: `last_lesson_extraction_event_id` is now set to an actual event ID, preventing future Bug-2 reprocessing.