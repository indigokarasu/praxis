# Session: 2026-06-18 Praxis Journal Ingest (Cron U)

**Run time:** 2026-06-17T23:43 UTC  
**Trigger:** Scheduled cron `praxis:journal_ingest`

## Summary

Routine ingest cycle. 7 unevaluated journals found, all routine no-ops.

## Details

| Metric | Value |
|--------|-------|
| Total journals on disk | 7,741 |
| Unevaluated | 7 (4 mentor, 2 forge, 1 custodian) |
| New events | 0 |
| New lessons | 0 |
| New shifts | 0 |
| Malformed | 0 |

All 7 journals were routine operational scans:
- 4x ocas-mentor mentor-light heartbeat journals
- 2x ocas-forge journal-scan no-ops
- 1x ocas-custodian light-scan no-op

## System State After Run

- Events: 2,455 | Lessons: 67 | Shifts: 90 total, 12 active (at cap)
- Active shift cap: 12/12 (full)
- No new signals to extract

## Observations

- The eval ID format in journals_evaluated.jsonl stores IDs WITHOUT .json extension (e.g., ocas-mentor/2026-06-17/mentor-light-20260617T232020Z). The existing gotcha about preserving .json was from a different profile/run. Added a new gotcha about dual-format matching to prevent future confusion.
- The ingest script pattern (write_file -> terminal) continues to work reliably in cron context.
- At 12/12 active shifts, the system cannot propose new shifts until decay frees cap space. The oldest shifts (created ~June 14) will approach the 14-day decay window around June 28.

## Gotcha Update

Added references/gotchas-praxis.md gotcha: "Eval file format varies by profile -- use dual-format matching" to document that eval IDs may or may not include .json depending on profile, and the safe approach is to store both variants.
