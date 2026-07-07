# Session: 2026-06-22 Cron Ingest 14:35Z

## Summary

Cron ingest run. 4 new journals found, 2 events recorded, 0 lessons, cap at 12/12.

## Journals Processed

| Journal | Signal | Outcome |
|---------|--------|---------|
| ocas-dispatch/2026-06-22/dispatch-cron-20260622T142332Z | no_signal (success) | Routine dispatch wave |
| ocas-dispatch/dispatch-cron-20260622T1427Z | no_signal (second_wave_skip) | Routine re-detection skip |
| ocas-taste/2026-06-22/spotify_sync | auth_failure | SPOTIFY_REFRESH_TOKEN missing (persistent since 2026-04-13) |
| ocas-mentor/2026-06-22/mentor-light-20260622T143507Z | mentor_error | 1 error, outcome=partial |

## Events Recorded

1. evt-20260622144242-d61cb774 — auth_failure from ocas-taste/spotify_sync
2. evt-20260622144242-b6e548d4 — mentor_error from ocas-mentor/mentor-light

## Bugs Encountered

### Events written to EVAL_FILE instead of EVENTS_FILE

The ad-hoc ingest script had a copy-paste bug: `append_jsonl(EVAL_FILE, e)` was used instead of `append_jsonl(EVENTS_FILE, e)` for deduped events. Events appeared as eval entries with event_id fields, NOT in events.jsonl. Recovery: manually moved 2 misplaced entries from eval to events file, rewrote eval file.

New gotcha added to gotchas-praxis.md: "Deduped events written to EVAL_FILE instead of EVENTS_FILE (2026-06-22)".

### glob import missing

Stale script cleanup used glob.glob() but glob was not imported. NameError after main pipeline completed. Fixed by running cleanup separately.

## State

- events.jsonl: 2931 entries (was 2929)
- lessons.jsonl: 76 entries (no new lessons)
- shifts.jsonl: 264 entries, 12 active (cap reached)
- journals_evaluated.jsonl: 25433 entries
- total_ingests: 12

## Observations

- Spotify auth_failure is a known persistent issue (3rd occurrence). Will produce a lesson once >=2 new events accumulate in a single ingest cycle.
- Mentor-light partial outcome with 1 error is a new signal to watch.
- Cap at 12/12 blocks all new shift activation.
