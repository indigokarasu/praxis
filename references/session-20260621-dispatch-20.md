# Session 2026-06-21 Dispatch #20 — Second-Wave Pattern Confirmed

**Date**: 2026-06-21T23:03:37Z  
**Trigger**: Dispatcher detected 6 new journal files  
**Pipelines run**: Forge + Mentor + Praxis

## What happened

1. **First dispatch wave**: 6 journals detected (custodian light-scan, praxis-dispatch, 4 mentor-light)
2. **Forge scan**: Clean — no unprocessed proposals. Wrote `forge-scan-20260621T230559Z.json`
3. **Mentor heartbeat**: 4577 files scanned, 6 new ingested, `active_skills_30d` corrected 14→22
4. **Praxis ingest**: 8 journals evaluated (4 new, 4 already evaluated), 0 events, all no-signal
5. **Second dispatch wave**: Dispatcher re-ran and detected 2 journals written by this dispatch's own run
6. **Resolution**: Evaluated all dispatch-output journals as no-signal. Queue cleared on third dispatcher run.

## New learning: Dispatcher second-wave pattern

After a multi-skill dispatch runs, the dispatcher re-scans and detects journals written by the dispatch's own pipelines. This is **expected behavior**, not an error. Include all dispatch-output journals in the Praxis ingest's eval list.

## Key metrics

- Mentor `active_skills_30d`: 14 (script) → 22 (corrected)
- Praxis active shifts: 12/12 (at cap)
- Total journals evaluated this dispatch: 12
- Events extracted: 0 (all routine no-signal)
