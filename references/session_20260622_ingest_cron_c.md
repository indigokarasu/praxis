# Session 2026-06-22 Cron Ingest C — Findings

**Run:** `praxis-ingest-20260622T051527Z` (follow-up to crashed `praxis-ingest-20260622T051247Z`)
**Trigger:** Scheduled cron job
**Profile:** indigo

## What happened

1. **15 new journals found** via Python mtime comparison (both indigo + legacy journal paths)
   - `find -newermt` returned 0 results due to UTC/local-time timezone mismatch — Python comparison was correct
   - Journals: 8 mentor-light, 3 dispatch, 1 forge, 1 custodian, 1 rally, 1 finch

2. **Signal extraction:** 14 no-signal, 1 event recorded
   - Event: `dispatch_outcome` from `dispatch-cron-20260622T045455Z` (ocas-dispatch, Response phase)

3. **Script crash:** `groups[key].key = key` typo caused `AttributeError` after event write + eval mark
   - Events and eval entries were already persisted (crash-safe ordering worked)
   - Follow-up script completed lesson extraction, shift proposal, state update, journal write

4. **Lesson extraction:** 3 candidate lessons from 140 historical events (scoping gap)
   - All 3 were noise (`no_signal`, `no_op`, `success`) — removed from `lessons.jsonl`
   - 76 lessons remain (unchanged from pre-run)

5. **Shift proposal:** 0 new shifts (cap at 12/12 blocks activation)

6. **State corruption from follow-up:** Follow-up script initially set `events_recorded: 140` instead of `1`
   - Manually corrected to reflect actual run results

## New gotchas discovered

### `find -newermt` UTC timezone bug
`find -newermt "2026-06-22T04:48:21"` interprets the timestamp as local time, not UTC. Even on a UTC system, the `T` format may not be parsed correctly by all `find` implementations. **Always use Python mtime comparison.**

### Ad-hoc script crash follow-up pattern
When a script crashes after writing events but before completing the pipeline:
- Write a follow-up script that does NOT re-scan journals or re-count totals
- Set `events_recorded` to actual new events, not total events loaded
- Write evidence BEFORE eval entries (crash safety)

### List vs dict assignment typo
`groups[key] = []` then `groups[key].key = key` raises `AttributeError`. Use dict literals `{}` for structured data.

## Files modified
- `events.jsonl`: 2840 → 2841 (+1 event)
- `journals_evaluated.jsonl`: 25102 → 25117 (+15 entries)
- `lessons.jsonl`: 76 → 79 → 76 (3 noise added then removed)
- `shifts.jsonl`: 264 (unchanged, 12 active)
- `ingest_state.json`: total_ingests 128 → 129

## Stale scripts cleaned
- `ingest_cron_20260622_c.py` (removed from data root)
- `ingest_followup_20260622_c.py` (removed from data root)
