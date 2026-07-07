# Session 2026-06-22 — Dispatch #21 (Second-Wave Handling)

## Summary
Dispatch at 2026-06-22T09:26Z. 2 new mentor-light journals. All 3 pipelines ran clean. Second wave detected 5 dispatch-output journals. Queue cleared after second-wave handling.

## Wave 1 (Initial Dispatch)
- **Trigger:** 2 new mentor-light journals (`09:24:17Z`, `09:25:25Z`)
- **Forge:** 0 unprocessed proposals → no-op journal written (`forge-scan-20260622T093126Z`)
- **Mentor:** 4 new files ingested, active_skills_30d corrected 14→22 (19th+ confirmation)
  - Partial success: script stdout said 4 but evidence showed 0 → backup evidence written
- **Praxis:** 3 new journals found (all dispatch-output), 0 events, all no-signal

## Wave 2 (Self-Referential Detection)
Dispatcher detected 5 journals written by Wave 1:
1. `forge-scan-20260622T093126Z.json`
2. `mentor-light-20260622T093136Z.json`
3. `mentor-light-20260622T093145Z.json`
4. `praxis-dispatch-20260622T093443Z.json`
5. `cron-ingest-20260622T093340Z.json`

All 5 were already in the eval file from the Mentor heartbeat's ingestion. Praxis ingest correctly found 0 new journals.

**Key issue:** The `praxis-dispatch-20260622T092737Z.json` from the PREVIOUS dispatch run was NOT in the eval file. Added manually.

## Praxis State Reset Bug
The ad-hoc ingest script (`praxis_dispatch_ingest_20260622.py`) overwrote `total_ingests` (was 10, became 1), `journals_processed` (was 48, became 0), and `last_evaluated_count` (was 38, became 0) instead of incrementing. Fixed manually after the run.

**Lesson:** Ad-hoc Praxis ingest scripts must increment existing state values, not replace them. The production script (`praxis_ingest_run.py`) has the same bug — it doesn't update `ingest_state.json` at all.

## Third-Wave Mitigation
After Wave 2, all dispatch-output journals were in the eval file and `last_ingest_run` was advanced to `2026-06-22T09:38:34Z`. Queue cleared on next dispatcher scan.

## Key Learning
When the Mentor heartbeat script ingests journals, it adds them to Praxis's `journals_evaluated.jsonl` via its own ingestion mechanism. This means by the time the Praxis dispatch ingest runs, the journals are already evaluated. The Praxis ingest will find 0 new journals but still writes a journal — which the dispatcher then detects as a second wave. This is expected and harmless IF all dispatch-output journals are in the eval file.
