# Praxis Cron Ingest — 2026-06-22 @ 11:08Z

**Date**: 2026-06-22T11:08Z  
**Run ID**: praxis-cron-20260622T1108Z  
**Type**: Scheduled cron ingest

## New Journals Found: 3 (via mtime comparison, last_ingest_run: 2026-06-22T11:02:18Z)

| Journal | Type | Signals |
|---------|------|---------|
| `ocas-finch/2026-06-22/scan-0600.json` | finch scan (overwritten) | 2 finch_actionable_email — GitHub PAT expiry (high), GFiber visit TODAY (high) |
| `ocas-custodian/2026-06-22/light-scan-2026-06-22-040602.json` | custodian light-scan (type: observation) | no_signal — filtered by observation type |
| `ocas-mentor/2026-06-22/mentor-light-20260622T110659Z.json` | mentor light heartbeat | no_signal — filtered by mentor_light_success |

## Results

- **Events recorded**: 2 (both finch_actionable_email)
- **Lessons extracted**: 0 (existing lesson covers finch_actionable_email/execution, 16 total events)
- **Shifts activated**: 0 (cap at 12/12, existing shift covers pattern)
- **Net new behavioral content**: 0 shifts, 0 lessons

## Key Issue: Overwritten Journal Pattern

The finch `scan-0600.json` was already in `journals_evaluated.jsonl` (evaluated at 09:17Z as no_signal), but the file was overwritten at 11:05Z with new content containing 2 actionable emails. The eval dedup by `journal_id` prevented re-evaluation.

**Resolution**: A targeted follow-up script re-extracted signals using the correct nested schema path (`sources.email.actionable`) and recorded 2 events.

**Gotcha added**: Overwritten journal files evade eval dedup — see `gotchas-praxis.md`.

## Nested Schema Path Issue

The initial follow-up script failed because it checked `data.get("actionable", [])` (top-level) instead of `data.get("sources", {}).get("email", {}).get("actionable", [])` (nested). The finch scan journal schema nests actionable emails under `sources.email.actionable`, not at the top level. The production `extract_signals` function handles this, but ad-hoc scripts must be aware of the nested path.

## State After

- `total_ingests`: 25
- `journals_processed`: 78
- `last_evaluated_count`: 68
- `active_shifts`: 12/12 (unchanged)
- `last_ingest_run`: 2026-06-22T11:16:14Z

## Stale Scripts Cleaned

- `ingest_cron_20260622_1108.py` (main ingest)
- `ingest_followup_20260622_1114.py` (follow-up)
- `ingest_followup_20260622_1111.py` (first follow-up, failed)
