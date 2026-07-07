# Recurring Noise Lesson Cleanup (Post-Ingest)

**Pattern:** Every cron ingest run produces 13-15 noise lessons from the production script's lesson-scoping bug. These must be cleaned up post-run to prevent `lessons.jsonl` from growing unbounded with stale patterns.

**Confirmed:** 2026-06-26 (15 noise lessons removed: 13 from this run + 2 pre-existing)
**Updated:** 2026-06-29 (13 noise lessons with MISSING signal_type key — filter bug discovered)

## Why It Happens

The production script `praxis_ingest_run.py` ignores `last_lesson_extraction_event_id` and re-processes the full `events.jsonl` history (3,300+ events) every run. This re-creates lessons for stale patterns that no longer represent active behavior. All produced lessons are `confidence: low` because the grouping threshold (≥2 events) is met by historical accumulation, not by genuine emerging patterns.

## Cleanup Procedure

After every cron ingest run, before writing the Praxis journal, run **two passes**:

### Pass 1: Remove low-confidence and signal_type-missing lessons (UPDATED 2026-06-29)

```python
import json

lessons_path = 'lessons.jsonl'
kept = []
removed = 0
with open(lessons_path) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        les = json.loads(line)
        st = les.get('signal_type')  # None if key missing
        if les.get('confidence') == 'low':
            removed += 1
        elif st is None:
            # signal_type key entirely absent — Bug 2 noise (2026-06-29 discovery)
            removed += 1
        else:
            kept.append(line)

with open(lessons_path, 'w') as f:
    for line in kept:
        f.write(line + '\n')

print(f'Pass 1: removed {removed} low-confidence/missing-signal_type lessons, kept {len(kept)}')
```

**Critical fix (2026-06-29):** `les.get('signal_type')` returns `None` when the key is absent. The old filter `les.get('signal_type', '').strip().lower()` would return `None` (not `''`) for missing keys, and `None` is not in any string set — so the lesson would pass the filter. Always check `st is None` before string operations.

### Pass 2: Remove malformed and noise-signal lessons (MANDATORY — 2026-06-27, updated 2026-06-29)

Pass 1 alone is insufficient. The production script also produces lessons with **empty `signal_type`**, **missing `signal_type` key**, or **noise signal types** from historical accumulation. These must also be removed:

```python
import json

NOISE_SIGNAL_TYPES = {
    '', 'unknown', '?', 'no_op', 'routine', 'no_signal', 'cron_error',
    'cron_errors', 'observation', 'success', 'mentor_light', 'low_coverage',
    'gap_detected', 'correction', 'anomaly', 'stale_counters', 'fixes_applied',
    'new_tasks_found', 'task_resolved', 'directive', 'parse_error',
    'security_alert', 'calendar_conflict', 'auth_failure', 'coverage_gap',
}

lessons_path = 'lessons.jsonl'
kept = []
removed = 0
with open(lessons_path) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        les = json.loads(line)
        st = les.get('signal_type')  # None if key missing
        if st is None:
            # signal_type key entirely absent — Bug 2 noise
            removed += 1
        elif isinstance(st, str):
            st_lower = st.strip().lower()
            if not st_lower or st_lower in NOISE_SIGNAL_TYPES:
                removed += 1
            else:
                kept.append(line)
        else:
            # signal_type is not a string (e.g., int, list) — malformed
            removed += 1

with open(lessons_path, 'w') as f:
    for line in kept:
        f.write(line + '\n')

print(f'Pass 2: removed {removed} malformed/noise lessons, kept {len(kept)}')
```

**Confirmed 2026-06-27:** Single-pass cleanup left 43 high-confidence lessons with empty signal types (e.g., `|ocas-custodian/execution`) and noise types (`low_coverage`, `gap_detected`, `correction`, `anomaly`). Two-pass cleanup reduced from 74 → 16 meaningful lessons.

**Confirmed 2026-06-29:** Pass 2 also catches lessons where `signal_type` key is entirely absent (returns `None` from `.get()`). The old filter `les.get('signal_type', '').strip().lower()` would fail on this because `.get('signal_type', '')` returns `None` when key is missing (the default `''` only applies to the dict's get, not to the key being absent — actually it DOES return `''` for missing keys, but `''.strip().lower()` returns `''` which IS in NOISE_SIGNAL_TYPES... however the actual behavior showed 0 removals, suggesting the key was present-but-empty in some lessons and absent in others). Always check `st is None` explicitly first.

## Expected Outcome

- `lessons.jsonl` should only contain `confidence: high` lessons with a valid, non-noise `signal_type` string
- If any `confidence: medium` lessons exist, review manually before removing
- The count of high-confidence lessons should remain stable across runs
- **If all events in a run are `no_signal`**, expect ALL produced lessons to be noise — `lessons.jsonl` may go to 0 entries after cleanup (confirmed 2026-06-29: 13 lessons → 0)

## Related

- `references/production-script-fix-lesson-scoping.md` — root cause fix for the scoping bug
- `references/session-20260618_ingest_cron_d.md` — original discovery of the scoping issue
