# Dispatch #96 — Praxis Journal Ingest (2026-06-25)

**Timestamp:** 2026-06-25T12:27Z (post-Mentor)

## Summary

- 5 unevaluated journals found via mtime-based discovery (floor: dispatcher latest_ts 2026-06-25T12:20:05Z)
- Ingest script processed all 5 (directory filter: ocas-praxis only, but these were all cross-skill dispatch-output journals)
- 0 events, 5 no-signal
- **Gap backfill: 15,238 entries** — accumulated same-day concurrent heartbeat eval gaps
  - 31 Praxis dispatch journals from today (concurrent heartbeats didn't add to eval file)
  - Remaining from prior waves' dispatch-output journals
- Eval file: 38,612 → 53,851 entries

## Journals Evaluated

1. `ocas-mentor/2026-06-25/mentor-light-20260625T122005Z.json` — dispatcher new_file
2. `ocas-mentor/2026-06-25/mentor-light-20260625T122127Z.json` — dispatcher new_file
3. `ocas-forge/2026-06-25/forge-scan-20260625T122516Z.json` — dispatch output (this run)
4. `ocas-mentor/2026-06-25/mentor-light-20260625T122539Z.json` — dispatch output (Mentor script)
5. `ocas-mentor/2026-06-25/mentor-light-20260625T122540Z.json` — dispatch output (Mentor script, near-duplicate timestamp)

## Concurrent Heartbeat Eval Gap Pattern

31 Praxis dispatch journals from today were missing from `journals_evaluated.jsonl` despite being written by concurrent Praxis heartbeats earlier in the day. These heartbeats processed the journals but didn't add their own output to the eval file (the ingest script only evaluates source journals, never its own output). The gap backfill in this dispatch caught all of them.

This is expected recovery behavior — concurrent heartbeats don't coordinate eval file writes, so each heartbeat may write journals that the next dispatch wave's gap backfill must catch up.

## State

- `last_ingest_run` advanced to: 2026-06-25T12:27:12Z
- Eval file: 53,851 entries
- Dispatch journal written and added to eval file (manual step)
