**Dispatch #85 (2026-06-25):** Steady-state multi-skill dispatch, Praxis pipeline.

### Ingest
- Mtime-based discovery found 1 new self-referential journal: `decay-check-20260625T100342Z.json`
- Ingested 1 journal, produced 24 micro-lessons (all `no_signal` domain)
- Dispatcher `new_files` (mentor-light journals) already in eval file — concurrent Praxis heartbeat evaluated them

### Third-wave mitigation
- Added eval entries for current run's mentor-light journal (100756Z) — not yet in eval file
- Added eval entry for forge-scan journal (101059Z) — not yet in eval file
- Advanced `last_ingest_run` to 2026-06-25T10:10:00Z

### Pattern confirmed
- Praxis eval file steadily growing, 0 gap backfill needed (3rd+ consecutive)
- Directory filter correctly excludes non-praxis journals — cross-skill mitigation by caller is mandatory
- `no_signal` lessons dominate when system is healthy (journals report routine operation, no behavioral issues)
