# Session 2026-06-22 Cron Ingest @ 04:09Z

## Summary
Routine cron ingest: 10 new journals, 2 events recorded (both noise - removed), 1 noise lesson extracted (removed). Net: 0 events, 0 lessons. Cap at 12/12.

## What Happened
- State at start: `last_ingest_run: 2026-06-22T03:38:00Z`, `journals_processed: 10826`
- Production script `praxis_ingest_run.py` ran successfully
- Found 10 new journals (9 mentor-light heartbeats + 1 custodian light-scan)
- Recorded 2 events: 1 custodian `failure_keyword` + 1 mentor `correction`
- Both events identified as noise and removed post-hoc
- 1 noise lesson extracted from 8 historical `no_signal` events (scoping bug) — removed
- State file updated manually (production script gap)

## Noise Events Removed

### 1. Custodian `failure_keyword` (evt-20260622040659798061-19505)
- Source: `ocas-custodian/2026-06-21/light-scan-2026-06-21-210000.json`
- Summary: "Light scan 21:00: 125 jobs scanned, 18 with errors. No new issues since deep scan at 20:00. All errors are known patterns: 5 manifest.build 401 (already escalated), 5 transient 429, 5 monitor no-op ex..."
- Verdict: False positive — routine scan reporting known/tracked errors, "No new issues"
- Gotcha: Custodian `action` journals with error mentions but no escalation → filter at extraction

### 2. Mentor `correction` (evt-20260622040659800466-19506)
- Source: `ocas-mentor/2026-06-22/mentor-light-20260622T035450Z.json`
- Summary: "Light heartbeat completed. Script succeeded on all 3 writes. active_skills_30d corrected 14→18 (OCAS). 2 evidence lines written (script + correction)."
- Verdict: False positive — routine active_skills count update, not a behavioral failure
- Gotcha: NEW — mentor-light `correction` from routine data updates is noise

## Noise Lesson Removed
- `les-20260622040659833234-19507`: "In ocas-custodian during execution: no_signal errors recur (n=8)"
- Extracted from 8 historical `no_signal` events spanning 2026-06-21 to 2026-06-22
- Root cause: Production script lesson extraction scoping bug (re-processes full history)

## Gotchas Confirmed
1. **Production script lesson scoping bug** — lesson extraction loads entire `events.jsonl` history (2,832 events) and groups all of them. Produces noise lessons from historically-accumulated `no_signal` events. The `last_lesson_extraction_event_id` tracking exists in the state file but is NOT used by the production script.
2. **Production script doesn't update `ingest_state.json`** — caller must update manually after every run.
3. **Mentor-light `correction` false positive** — new gotcha, added to gotcha catalog.

## State Transitions
- `journals_processed`: 10826 → 10836 (+10)
- `last_evaluated_count`: 10965 → 10975 (+10)
- `total_ingests`: 123 → 124 (+1)
- `active_shifts`: 12/12 (unchanged)

## Files Modified
- `journals_evaluated.jsonl`: +10 entries
- `events.jsonl`: +2 entries, then -2 (noise removal) = net 0
- `lessons.jsonl`: +1 entry, then -1 (noise removal) = net 0
- `ingest_state.json`: manually updated post-run
- `evidence.jsonl`: +1 entry
- `journals/ocas-praxis/2026-06-22/praxis-cron-20260622T040902Z.json`: new journal

## Disk Cleanup
Removed 2 temporary scripts: `cleanup_noise_events.py`, `update_state.py`
