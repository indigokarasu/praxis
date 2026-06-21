# Session 2026-06-18 Ingest Cron D — Lesson Extraction Scope Bug

## What happened

The ingest script (`ingest_cron_20260618_d.py`) scanned 29 unevaluated journals and extracted 2 new events:
- `tier1_fix_applied` (ocas-custodian): finch:scan scheduler reset, 2nd recurrence
- `tier2_issue` (ocas-custodian): state.db at 6GB

The lesson extraction Pass 1 loaded ALL 2,520 events from `events.jsonl` and grouped by `(signal_type, failure_phase)`. This produced 8 lessons — 4 legitimate, 4 noise:

| Lesson | Signal Type | Domain | Events | Verdict |
|--------|-------------|--------|--------|---------|
| les-47 | auth_failure | ocas-finch | 19 | Legitimate |
| les-48 | platform_failure | ocas-spot | 27 | Legitimate |
| les-49 | correction | ocas-finch | 9 | Legitimate |
| les-50 | escalation | ocas-custodian | 7 | Legitimate |
| les-45 | failure | unknown | 28 | Bad domain |
| les-46 | failure | unknown | 4 | Bad domain |
| les-51 | no_active_watches | ocas-spot | 5 | Noise (routine spot) |
| les-52 | system_memory_drop | ocas-finch | 2 | Noise (finch scan artifact) |

The 4 noise lessons were cleaned up post-hoc. The 4 legitimate lessons produced shifts, but 3 of the proposed shifts had bad domains (`general`, empty) from the lesson extraction and had to be expired and replaced.

## Root cause

Lesson extraction Pass 1 uses `all_events` from the full `events.jsonl` history. Every ingest run re-processes 2,500+ events and creates lessons for any `(signal_type, phase)` group with >=2 events, regardless of when those events were recorded. This causes:

1. **Stale lesson re-creation**: Old patterns (e.g., `no_active_watches` from spot sweeps) keep reappearing
2. **Unknown-domain lessons**: Legacy events (pre-2026-06-15) use `outcome_type` schema without a `skill` field, so lesson gets `domain: unknown`
3. **Noise accumulation**: Routine signals that happened to occur 2+ times in history get lessons

## Fix

**Scope lesson extraction to new events only.** Before Pass 1 grouping, filter to only events recorded in the current ingest run. Track `last_lesson_extraction_event_id` in the ingest state file.

## Additional cleanup performed

- Expired 3 shifts: `failure/unknown`, duplicate `execution_error`, duplicate `escalation`
- Proposed 3 replacement shifts: `tier1_fix_applied/custodian`, `tier2_issue/custodian`, `auth_failure/finch`
- Active shifts: 12/12 (back at cap)
- Cleaned up 8 bad lessons from `lessons.jsonl` (back to 44)

## Key patterns from this scan

- **finch:scan scheduler recurrence**: Tier 1 fix applied 2nd time
- **OVH Kepler 403**: 4+ jobs affected by single auth failure
- **state.db growth**: 6GB, needs VACUUM scheduling
- **Forge clean**: 9 routine no-op scans, no unprocessed files
