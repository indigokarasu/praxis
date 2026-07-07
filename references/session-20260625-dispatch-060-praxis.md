# Praxis — Dispatch #60 (2026-06-25T02:08Z)

**Input:** 5 journals discovered via mtime comparison (all from this dispatch wave's own output)
**Captured TS:** `2026-06-25T02:05:41.795527+00:00` (from prior dispatch #59's `last_ingest_run`)
**Output:** 0 events, 5 eval entries, 2 gap backfill

## Journals Processed
- 5 journals with mtime >= captured timestamp
- All routine/no-op (mentor-light, forge-scan, taste-scan, praxis-cron, dispatch-output)
- 0 events recorded, 0 behavioral signals

**Key Pitfall — `new_files` Timestamp Mismatch:**
- Dispatcher listed `mentor-light-20260625T020800Z.json` but actual file was `mentor-light-20260625T020902Z.json` (62-second discrepancy)
- Dispatcher listed `praxis-dispatch-20260625T015715Z.json` — naive grep returned NOT_EVALUATED but it WAS in eval file (line 37990, `self_referential_skip`)
- Root cause: `$(date)` rollover in `cron-heartbeat-light.py` between `run_id` composition and filename composition
- Fix: Always use mtime-based discovery as ground truth, then grep actual filenames from disk

## Gap Backfill
- **2** older journals (mtime < `last_ingest_run`) not in `journals_evaluated.jsonl`
- Dramatic decrease from #59's 14,772 — the accumulated backlog was cleared
- Expected to stabilize at 0-5 per dispatch going forward

## State After
- `last_ingest_run`: `2026-06-25T02:13:23.724810+00:00` (advanced to now+1s for third-wave mitigation)
- `journals_evaluated.jsonl`: 37,999 entries (+5 ingest + 2 backfill + 1 self-eval)

## Third-Wave Mitigation
- All 5 dispatch-output journals added to eval file with `action_taken: "dispatch_output_skip"`
- Praxis's own journal self-evaluated
- `last_ingest_run` advanced past all their mtimes

## Key Observation

The gap backfill dropped from 14,772 (#59) to 2 (#60) — confirming the "accumulated backlog" hypothesis. The large backfill on #59 was caused by multiple dispatch waves' output journals being caught in a single advance of `last_ingest_run`. With the backlog cleared, future dispatches should see 0-5 gap backfill entries.
