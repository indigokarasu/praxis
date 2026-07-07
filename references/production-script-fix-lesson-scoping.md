# Production Script Fix: Lesson Extraction Scoping

**Issue:** `praxis_ingest_run.py` re-processes the entire `events.jsonl` history every run, producing noise lessons from stale patterns.

**Confirmed:** 2026-06-21 (produced `no_signal` lesson, confidence=low, n=10 from historical mentor-light events)

## Root Cause

The production script's lesson extraction loads ALL events from `events.jsonl` and groups them by `(signal_type, failure_phase)`. The `last_lesson_extraction_event_id` field exists in `ingest_state.json` but is NOT used by the production script's lesson extraction logic.

## Fix Required

In `praxis_ingest_run.py`, before Pass 1 grouping:

```python
# Load state to get last lesson extraction event ID
state = {}
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        state = json.load(f)
last_lesson_evt_id = state.get("last_lesson_extraction_event_id")

# Filter events to only new ones since last lesson extraction
if last_lesson_evt_id:
    filtered_events = [e for e in all_events if e.get("event_id", "") > last_lesson_evt_id]
else:
    filtered_events = all_events

# Use filtered_events for Pass 1 grouping, NOT all_events
```

## Also Fix: Date Filter

Remove the `date_dir in (today, yesterday)` filter from the filesystem scan. Walk ALL date directories and rely on mtime comparison + eval dedup.

## Verification

After fix:
- Lesson extraction should produce 0 lessons when no new events were recorded
- `no_signal` lessons should never be created from historical accumulation
- The lesson pool should stop growing with noise entries
