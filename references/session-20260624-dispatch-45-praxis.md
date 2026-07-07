# Dispatch #45 — 2026-06-24T12:32Z (Praxis: second-wave skip + third-wave mitigation)

**Trigger:** Journal dispatch (2 new files: rally preopen + mentor light)

## Phase: Praxis
- **Dispatcher `new_files`:** `ocas-rally/2026-06-24/run_preopen_20260624053014.json`, `ocas-mentor/2026-06-24/mentor-light-20260624T122711Z.json`
- **Both already in `journals_evaluated.jsonl`** — second-wave detection, skipped silently
- **mtime-based discovery:** 0 new journals (state already advanced past these)
- **Third-wave mitigation:** Added new `mentor-light-20260624T124445Z.json` (from this dispatch's Mentor heartbeat) to eval file, advanced `last_ingest_run`

## Key Observations

### Second-wave skip pattern confirmed
When the dispatcher re-detects journals from the same dispatch wave, Praxis correctly identifies them as already evaluated and skips silently. This is the expected no-op.

### Third-wave mitigation for mentor-light
The mentor-light journal written by this dispatch's heartbeat (`mentor-light-20260624T124445Z.json`) was NOT in `journals_evaluated.jsonl` because it was written AFTER the prior Praxis cron run. Added it manually and advanced `ingest_state.json:last_ingest_run` to prevent re-detection.
