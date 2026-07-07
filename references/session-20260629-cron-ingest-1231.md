# Session: Cron Ingest 2026-06-29 12:31 UTC — Missing signal_type Key Discovery

## Trigger
Scheduled cron job: `praxis:journal_ingest`

## What happened

### Production script ran normally
- `praxis_ingest_run.py` processed 2 journals, recorded 1 event (mentor-light no_signal)
- Script produced "13 new lessons" — all Bug 2 noise from full-history reprocessing

### Noise cleanup revealed filter bug
- Expected: cleanup filter `les.get('signal_type', '') == '?'` would catch all 13 noise lessons
- Actual: 0 lessons matched `== '?'` because `signal_type` key was **entirely absent** from the lesson dicts
- `les.get('signal_type', '')` returned `None` (not `''`) because the key didn't exist
- Root cause: production script's Pass 2 grounding didn't add `signal_type` when source events lacked the field

### Fix applied
- Rewrote `lessons.jsonl` to empty (all 13 were from this run, all noise)
- Updated Bug 2 cleanup criteria in SKILL.md to include `les.get("signal_type") is None` check
- Added `is_bug2_noise_lesson()` function with all four noise conditions

## Key lesson: signal_type can be missing
The earlier heuristic "signal_type == '?' is the most reliable single indicator" was wrong.
The most reliable check is: **is the key present at all?** Missing key > "?" > "" > null.

## Metrics
- Journals scanned: 2
- Events recorded: 1 (no_signal)
- Lessons cleaned: 13
- Gap backfill: 0
- Active shifts: 3 (all healthy, recently reinforced)
- Decay risks: 0

## State
- `total_ingests`: 159
- `last_ingest_run`: 2026-06-29T12:33:02Z
- `lessons.jsonl`: 0 entries (all were Bug 2 noise)
