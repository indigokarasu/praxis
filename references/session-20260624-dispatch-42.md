# Dispatch #42 — 2026-06-24T06:24Z (Praxis)

**Trigger:** Multi-skill dispatch — `new_journals` (2 files)

**Dispatcher provided:**
- `ocas-praxis/2026-06-24/cron-ingest-20260624T061606Z.json` (from prior Praxis cron)
- `ocas-mentor/2026-06-24/mentor-light-20260624T061631Z.json` (from prior Mentor cron)

## Ingest Run (First Wave)
- **last_ingest_run at start:** `2026-06-24T06:28:36.826318+00:00`
- **Both journals older than state** — mtime-based discovery would miss them
- **CAPTURED_TS used:** `2026-06-24T06:15:00.000000+00:00` (before both journals)
- **Template:** `dispatch_ingest_template.py`
- **Result:** 7 new journals found, 0 events recorded, all no-signal
- **Gap backfill:** 10 journals added to eval file
- **Third-wave mitigation:** 4 dispatch-output journals (forge-scan, mentor-light, praxis-dispatch, this run's journal) added to eval file, `last_ingest_run` advanced to 06:37:36Z
- **Journal:** `cron-ingest-20260624T063830Z.json`

## Second-Wave Cleanup
- Dispatcher re-detected 4 journals from this dispatch run
- All 4 already in `journals_evaluated.jsonl` — silent no-op
- `last_ingest_run` advanced to 06:39:47Z
- **Journal:** `cron-ingest-20260624T063946Z.json`

## Key Observations
- CAPTURED_TS pattern works reliably for catching journals written before `last_ingest_run` was advanced by sibling pipelines
- Third-wave mitigation correctly handles all dispatch-output journals
- Queue cleared after second-wave cleanup
