# Session 2026-06-20 Dispatch

## First Dispatch Run (09:31 UTC)
- 3 pipelines executed:
  1. **Forge journal scan**: All 12 proposals already processed, 0 unprocessed
  2. **Mentor light heartbeat**: 1 new mentor-light journal — filtered as routine cron cadence no-op
  3. **Praxis journal ingest**: 1 unevaluated journal (forge-dispatch no-op), 0 new events
- 1 stale script cleaned up

## Second Dispatch Run (09:56 UTC)
- Triggered by new journal: `ocas-praxis/2026-06-20/dispatch-20260620T094858Z.json`
- 3 pipelines executed:
  1. **Forge journal scan**: All 13 proposals already processed, 0 unprocessed
  2. **Mentor light heartbeat**: 5 new entries from 3 skills. `active_skills_30d` corrected 12→19 (dual-path 30d count). Dual-path scan: 1,086 shared + 673 profile = 1,759 total files in 3-day window.
  3. **Praxis journal ingest**: 2 new journals, 0 new events (both no-ops from this dispatch run)
- 2 stale scripts cleaned up

## Key Operational Issue: Eval File Path Mismatch

The `journals_evaluated.jsonl` stores journal IDs in a different format than what filesystem scans produce:
- Eval file stores: `ocas-mentor/mentor-light-20260620T091801Z.json` (no date directory)
- Filesystem scan produces: `ocas-mentor/2026-06-20/mentor-light-20260620T091801Z.json` (with date directory)

This causes every journal to appear "unevaluated" on each scan. The dedup mechanism cannot match, wasting time re-scanning already-evaluated journals.

**Workaround used this session:** Determine new journals by comparing file mtime against `ingest_state.json:last_ingest_run` timestamp, bypassing the broken dedup for new-journal detection.

**Fix needed:** Normalize eval IDs at the start of each ingest run, or rebuild the eval file from the current filesystem scan using the canonical `path_to_journal_id` function.

## Dual-Path Journal Distribution (3-day window, 09:56Z)
- Shared (`/root/.hermes/commons/journals/`): 1,086 files
- Profile (`/root/.hermes/profiles/indigo/commons/journals/`): 673 files
- Total unique: 1,759 files
- Profile contains 62% as many recent journals as shared — both paths must be scanned for complete coverage

## Signal Filtering Results
- Mentor light heartbeat (outcome: success, routine) → no_signal ✓
- Forge dispatch scan (result: clean, 0 unprocessed proposals) → no_signal ✓
- Praxis dispatch ingest (0 new events) → no_signal ✓
