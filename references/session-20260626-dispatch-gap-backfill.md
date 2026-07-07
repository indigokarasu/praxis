# Session 2026-06-26 Dispatch Gap Backfill (04:03Z)

**Run type:** Multi-skill dispatch (Forge + Mentor + Praxis)
**Profile:** indigo

## Signals

### 1. `ingest_state.json` double timezone suffix

`last_ingest_run` was stored as `2026-06-26T03:56:13.223625+00:00+00:00` — a double `+00:00` suffix. `datetime.fromisoformat()` raises `ValueError: Invalid isoformat string`.

**Root cause:** Code concatenated `isoformat()` output (which already includes `+00:00`) with another `+00:00` suffix.

**Fix applied:** `re.sub(r'\+00:00\+00:00$', '+00:00', ts)` then rewrite state file.

**Lesson:** Never do `ts.isoformat() + "+00:00"` — `isoformat()` already includes the offset.

### 2. Gap backfill after template mtime discovery

**Scenario:**
- Dispatcher flagged 2 journals (`forge-scan-20260626T035450Z`, `mentor-light-20260626T035053Z`) with mtime ~03:50-03:54
- But concurrent Praxis cron heartbeat had advanced `last_ingest_run` to `03:56:13` (past those mtimes)
- Template discovery (`mtime >= last_ingest_run`) found only 2 journals (the ones with mtime > 03:56:13)
- 7 additional journals with mtime between 03:40 and 03:55 remained unevaluated

**Fix applied:** After template run, SECOND PASS scanned ALL journals not in `journals_evaluated.jsonl` regardless of mtime, added 7 as `gap_backfill` entries.

**Journals requiring backfill:**
- `ocas-dispatch/2026-06-26/dispatch-20260626T034223Z.json`
- `ocas-forge/2026-06-26/forge-scan-20260626T034231Z.json`
- `ocas-forge/2026-06-26/forge-scan-20260626T035450Z.json`
- `ocas-mentor/2026-06-26/mentor-light-20260626T034031Z.json`
- `ocas-mentor/2026-06-26/mentor-light-20260626T034527Z.json`
- `ocas-mentor/2026-06-26/mentor-light-20260626T035053Z.json`
- `ocas-praxis/2026-06-26/praxis-cron-20260626T035559Z.json`

**Lesson:** On EVERY multi-skill dispatch, after running the template, do a full scan of unevaluated journals (not mtime-filtered) and gap-backfill them. This catches the concurrency gap between dispatcher detection and last_ingest_run advancement.

### 3. Concurrent cron journals mid-dispatch

During dispatch processing (between Praxis template run and verification), 2 additional journals appeared from concurrent cron runs:
- `ocas-custodian/2026-06-26/light-scan-20260626T04:01:54Z.json`
- `ocas-mentor/2026-06-26/mentor-light-20260626T04:0315Z.json`

These were added as `concurrent_cron_eval` entries to prevent re-detection.

## Results

- **Forge:** no_op, 0 unprocessed proposals
- **Mentor:** success, light heartbeat, gap_detected=false
- **Praxis:** 9 journals evaluated (2 template + 7 gap backfill), 0 events
- **Email:** 2 threads reviewed, both `action:none` (second-wave re-detection), 0 escalations
- **All dispatch-output journals:** gap-backfilled into eval file
- **Final state:** 0 unevaluated journals
