# Dispatch 2026-06-29T12:40Z — Massive Legacy Eval Backfill

**Time:** 2026-06-29T12:40:05Z
**Pipeline:** Praxis journal ingest (dispatch-driven)

## Summary
A genuine dispatch triggered a one-time legacy backfill of 12,087 journals that were created before eval tracking began (May 13 – June 26). The eval file grew from 48,501 to 60,590 lines in a single dispatch.

## What Happened
- Dispatcher detected 4 "new" journal files (2 already in eval, 2 missing)
- The 2 missing files were: (1) a cron mentor-light journal from a prior cycle, (2) the prior wave's own dispatch output
- During the broader `os.walk` scan, 12,086 additional legacy journals were found unevaluated
- All 12,087 were registered in a single batch append to `journals_evaluated.jsonl`

## Post-Dispatch Cleanup
- 1 concurrent cron journal caught (`mentor-light-20260629T124026Z`)
- Final eval file: 60,590 lines

## Key Learning
This was a **one-time catchup event**. The eval file was created mid-June but journals had been accumulating since mid-May. After this backfill, the eval file should be comprehensive and gap rates return to normal steady-state (50-80 per wave from concurrent cron).

The `last_ingest_run` timestamp is NOT a coverage boundary for legacy journals — only the eval file's actual content is authoritative. Always grep individual filenames against the eval file, never assume `last_ingest_run` coverage for pre-tracking journals.
