# Session 2026-06-22: Cron Ingest @ 03:22Z

## Summary
- **12 journals discovered**, 12 evaluated, 11 no-signal, 0 malformed
- **1 new event**: custodian escalation (`manifest.build` provider 401)
- **0 new lessons** (single event, <2 threshold)
- **0 new shifts** (at cap 12/12)
- **Active shifts**: 12/12

## New Event
- `ocas-custodian/esc-run-20260621T200000` → `escalation` (severity: high)
  - manifest.build custom provider returning HTTP 401 via `fallback_model` routing
  - API key (`mnfst_8977...`) may be expired/rotated
  - 5 affected jobs: `bower:weekly-deep`, `taste:scan`, `bones:update`, `rainbow-grocery-receipts`, `dream-journal:morning`
  - Recurrence count: 2 (first seen 2026-06-20)

## Operational Notes
- Data-directory `praxis_common.py` was stale (missing dual-journal fix from 2026-06-21)
- Copied updated `praxis_common.py` from skills directory before running
- Added new gotcha to `gotchas-praxis.md` about data-directory drift pattern
- Custom ingest script written (then cleaned up) — production script still has date-filter bug
- `ingest_state.json` note field was overwritten (lost "Second wave" note) — minor

## Production Script Status
- `praxis_ingest_run.py` still has date-filter bug (only scans today/yesterday)
- `praxis_ingest_run.py` still has lesson scoping bug (re-processes full history)
- `praxis_ingest_run.py` does NOT update `ingest_state.json` after run
- Dual-journal fix now in data-directory `praxis_common.py` (manually synced)
