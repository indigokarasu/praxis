# Dispatch 2026-06-30T01:03Z — Praxis Pipeline

**Multi-skill dispatch, Praxis portion.** Email second-wave no-op + genuine journal dispatch.

## Ingest Summary

- **Journals ingested:** 9 (date filter picked up more than the 1 dispatcher-listed file)
- **Events recorded:** 5 (all `no_signal` from routine mentor-light journals)
- **Lessons extracted:** 13 (all Bug-2 noise)
- **Lessons cleaned:** 13 (all had `signal_type` key missing entirely)
- **Gap backfill:** 0
- **Shift changes:** 0
- **Active shifts:** 3/12

## Key Patterns

1. **Fast pre-filter confirmed:** All 5 events were `no_signal` → all 13 lessons removed without per-lesson inspection. This is the correct steady-state shortcut.

2. **signal_type key missing pattern:** All 13 noise lessons had `signal_type` key entirely absent from the dict (not set to `None`, not `"?"` — the key simply didn't exist). The `is_bug2_noise_lesson()` filter with `st = les.get("signal_type"); if st is None: return True` catches this correctly.

3. **Dispatch context:** The `praxis_ingest_run.py` script's date filter (`today` + `yesterday`) picked up 9 journals, not just the 1 file listed in the dispatcher's `new_files`. This is expected — the dispatcher only lists files changed since its last scan, while the script scans the full date directory.

## State After

- `total_ingests`: 192
- `journals_processed`: 60,996
- `eval file lines`: 48,729 (praxis), 926 (dispatch)
- `lessons.jsonl`: 0 entries (all noise removed)
