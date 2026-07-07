# Session 2026-06-22 Dispatch #25 — Praxis Ingest

## Summary

Dispatch triggered Forge + Mentor + Praxis pipelines. Praxis ingest ran after Mentor heartbeat, requiring third-wave mitigation.

## Timeline

1. **14:42:06Z** — Dispatcher detected: 1 email (Wing rejection), 1 new journal (mentor-update)
2. **14:44:00Z** — Prior Praxis ingest updated `last_ingest_run` to this timestamp
3. **14:51:09Z** — Mentor heartbeat completed, wrote `mentor-light-20260622T145109Z.json`
4. **14:51:XXZ** — Praxis ingest ran with `CAPTURED_TS=2026-06-22T14:44:00Z`
5. **14:55:XXZ** — Third-wave mitigation: added dispatch-output journals to eval, advanced state

## Key Issue: Template Doesn't Update State

The `dispatch_ingest_template.py` found 2 new journals (mtime > 14:44:00Z) and wrote eval entries, but did NOT update `ingest_state.json`. The caller had to manually:
1. Add 3 dispatch-output journals to `journals_evaluated.jsonl`
2. Advance `last_ingest_run` to `now + 1 second`
3. Update all counters

## Key Issue: mentor-update Journal Missed by mtime Discovery

The dispatcher's `new_files` included `ocas-mentor/2026-06-22/mentor-update-20260622T143917Z.json` (mtime 14:39:17Z), which is BEFORE `last_ingest_run` (14:44:00Z). The mtime-based discovery missed it. The fallback check of the dispatcher's `new_files` list caught it, and it was ingested directly.

The template found 2 journals with mtime > 14:44:00Z (likely the mentor-light journal from the current dispatch and possibly another). The mentor-update journal was NOT found by the template's mtime scan — it was only caught by the caller's fallback check.

## Third-Wave Mitigation Applied

After the ingest, the following journals were added to `journals_evaluated.jsonl` with `action_taken: "dispatch_output_skip"`:
- `forge-scan-20260622T145629Z.json` (written after ingest)
- `mentor-light-20260622T145109Z.json` (written by mentor heartbeat)
- `mentor-update-20260622T143917Z.json` (dispatcher's new_files)
- `praxis-dispatch-20260622T145532Z.json` (praxis journal)
- `dispatch-triage-20260622T145611Z.json` (dispatch journal)

`last_ingest_run` advanced to `2026-06-22T14:57:01Z`.

## Evidence Log Bloat

A prior dispatch run (14:50) created a `dispatch-cron` evidence entry marking the Wing rejection as `no_op`. This dispatch run created a second evidence entry for the same thread. The duplicate entry pattern is a known issue — see the dispatch skill's gotcha about second-wave re-detection.

## Lessons

1. **Always capture `last_ingest_run` BEFORE running sibling pipelines** — The Mentor heartbeat doesn't update Praxis's state, but a concurrent Praxis cron might.
2. **The template is intentionally minimal** — It delegates state management to the caller. This is by design, not a bug. The caller must always update state after running the template.
3. **Dispatcher's `new_files` is the authoritative fallback** — Even when mtime-based discovery finds journals, always check the dispatcher's `new_files` list for journals that fell through the cracks.
