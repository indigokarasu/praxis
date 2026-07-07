# Praxis Dispatch Ingest — 2026-06-22

**Date**: 2026-06-22T01:45Z  
**Run ID**: praxis-dispatch-20260622T014824Z  
**Source**: Multi-skill dispatch (Forge + Mentor + Praxis) + second-wave self-referential cleanup

## New Journals Found: 6 (first wave) + 3 (second wave)

### First Wave
| Journal | Type | Signals |
|---------|------|---------|
| `ocas-forge/forge-scan-20260622T014004Z.json` | forge no_op | None — clean scan |
| `ocas-mentor/mentor-light-20260622T013548Z.json` | mentor light | None — success, 0 errors |
| `ocas-mentor/mentor-light-20260622T013717Z.json` | mentor light (caller-corrected) | None — success, active_skills_30d corrected 14→22 |
| `ocas-mentor/mentor-light-20260622T013926Z.json` | mentor light | None — success, 0 errors |
| `ocas-dispatch/dispatch-email-20260622T014158Z.json` | dispatch email triage | None — 3 CI failures flagged for review |
| `ocas-praxis/praxis-dispatch-20260622T014128Z.json` | praxis dispatch | None — self-referential, excluded from ingest |

### Second Wave (self-referential)
| Journal | Type | Signals |
|---------|------|---------|
| `ocas-dispatch/dispatch-email-20260622T014842Z.json` | self-referential | Excluded (ocas-praxis own) |
| `ocas-forge/forge-scan-20260622T014902Z.json` | self-referential | Evaluated, no_signal |
| `ocas-mentor/mentor-light-20260622T014903Z.json` | self-referential | Evaluated, no_signal |

**Result**: 0 events extracted, 0 lessons, 0 shifts. All journals routine operational scans.

## Key Learning: Dispatcher Path Mismatch

The dispatcher's `details.new_files` field contains paths like `ocas-forge/2026-06-22/forge-scan-*.json`. These are **journal** paths, not data paths. The actual files are at:
- `/root/.hermes/profiles/indigo/commons/journals/<path>` (primary)
- `/root/.hermes/commons/journals/<path>` (legacy)

NOT at `/root/.hermes/commons/data/<skill>/...` — that directory doesn't exist for journals.

**Diagnostic pattern**: When `read_file` fails on dispatcher-provided paths, use `find` to locate by filename:
```bash
find /root/.hermes/profiles/indigo/commons/journals/ /root/.hermes/commons/journals/ -name "<filename>" 2>/dev/null
```

## Email Triage Results

3 GitHub CI failure notifications reviewed:
- 2× Contributor Attribution Check failures (commit author email not in AUTHOR_MAP)
- 1× Tests failure (test job 6 failed)

All classified as `flag_for_review` — no drafts created. `high_priority=0` after filtering.

## State After

- `total_ingests`: 108 → 110 (first wave + second wave)
- `active_shifts`: 12/12 (at cap, no changes)
- `last_ingest_events_added`: 0
- Queue cleared after second wave

## Follow-up Dispatch — 2026-06-22T10:25Z

Second dispatch of the day. Dispatcher detected 4 new journals but Praxis `last_ingest_run` (10:24:52Z) was already PAST the dispatcher's `latest_ts` (10:24:07Z). All dispatcher-listed journals had already been ingested.

**New journals found**: 1 (`mentor-light-20260622T102552Z.json` — written after `last_ingest_run`)
**Result**: 0 events, 0 lessons, 0 shifts. All no-signal.

**Confirmed pattern**: When `last_ingest_run > dispatcher.latest_ts`, the Praxis ingest finds 0 new journals from the dispatcher's list. Only truly new journals (written after `last_ingest_run`) need evaluation.

**Third-wave mitigation**: Added 3 dispatch-output journals to eval file with `dispatch_output_skip`, advanced `last_ingest_run` to `now + 1s`. Queue cleared.
