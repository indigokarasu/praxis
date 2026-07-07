# Noise Lesson Cleanup

This document describes the procedure for cleaning up noise lessons in the Praxis behavioral refinement loop.

## When to Run

Run after every Praxis ingest (both cron and dispatch) as part of the post-ingest checklist. See `references/cron-execution-checklist.md`.

## Criteria for Noise Lessons

A lesson is considered noise if ANY of the following are true:

1. `confidence: "low"`
2. `signal_type` is one of: `""`, `"unknown"`, `"?"`, `"no_op"`, `"forge_activity"`, `"routine"`, `"no_signal"`, `"cron_error"`, `"cron_errors"`, `"observation"`, `"success"`, `"mentor_light"`, `"correction"`, `"low_coverage"`, `"gap_detected"`
3. (Optional) All events from the current run are `no_signal` — this requires access to the current run's events and is omitted in the automated script for simplicity.

## Automated Script

Use `scripts/cleanup_noise_lessons.py` to perform the cleanup automatically. The script:

- Reads `lessons.jsonl`
- Filters out lessons matching the noise criteria above
- Writes the cleaned list back to `lessons.jsonl`
- Prints counts before and after

## Manual Verification

After running the script, verify that the lesson count has decreased and that no legitimate lessons were removed by spot-checking the remaining lessons.

## Integration with Praxis Checklist

Add the script execution step after `gap_backfill.py` and before writing the Praxis journal:

```bash
# After gap_backfill.py
python3 skills/ocas-praxis/scripts/cleanup_noise_lessons.py
# Then write Praxis journal
```

## Notes

- The script does not implement the third condition (all events from current run are no_signal) because it requires access to the current run's events. If that condition is needed, consider enhancing the script.
- Regular cleanup prevents the lessons file from growing with stale or irrelevant patterns.