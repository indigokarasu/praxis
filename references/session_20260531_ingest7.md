# Session: 2026-05-31 Ingest Run (journal_ingest #7)

## Run Summary
- **Date**: 2026-05-31T09:49:21Z
- **Journals scanned**: 8 new (from today+yesterday)
- **Journals with signals**: 3 (all ocas-custodian)
- **Events recorded**: 4 (after dedup: 4 unique)
- **Lessons extracted**: 1
- **Shifts activated**: 1 → cap now 12/12

## Events Recorded
1. `evt-ocas-custodian-escalation` — Escalation signaled (custodian light-scan no-date)
2. `evt-ocas-custodian-execution_error` — Google auth token file missing (both primary + backup absent); MCP stealth-broker module issue
3. `evt-ocas-custodian-escalation` — `google_token_missing` requires user re-auth; 3x transient HTTP 429s
4. `evt-ocas-custodian-execution_error` — Same auth token missing pattern confirmed (second scan)

## Lesson Extracted
- **ID**: `les-ocas-custodian-execution-execution_error-20260531094921`
- **Confidence**: high (upgraded from low — specific causal content)
- **What**: 2 execution_error events in ocas-custodian
- **Why**: Google auth token file missing in both primary and backup locations
- **When**: ocas-custodian scan execution phase

## Shift Activated
- **ID**: `shift-custodian-auth-token-20260531095314`
- **Text**: "Before ocas-custodian scan execution: verify Google auth token file exists (both primary and backup). If missing, alert user to re-auth immediately rather than proceeding with degraded monitoring."
- **Cap status**: 12/12 (FULL)

## Bugs Found and Fixed

### 1. Batch event ID collision (CRITICAL)
**Problem**: `generate_id()` used `datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')` which has microsecond resolution. When called in a tight loop, multiple calls within the same microsecond produce identical IDs. This caused 6 duplicate events (3 of one ID, 2 of another).

**Fix**: Changed `generate_id()` to use `time.monotonic_ns()` (nanosecond resolution, guaranteed monotonic within a process) plus an incrementing counter suffix.

**Status**: Fixed in `scripts/praxis_ingest_run.py` v3.0.1.

### 2. Lesson source_event_ids referencing phantom events
**Problem**: Lesson extraction ran before post-write event dedup. Lessons recorded `source_event_ids` that included event IDs subsequently removed as duplicates. In this run, both source_event_ids were identical (same ID twice).

**Fix**: Reordered pipeline to: (1) append events → (2) dedup events → (3) lesson extraction. Added `dedup_events_file()` function. Lesson extraction now filters `source_event_ids` to only include IDs that exist in the deduped event store.

**Status**: Fixed in `scripts/praxis_ingest_run.py` v3.0.1.

### 3. Duplicate events in events.jsonl (post-hoc cleanup)
**Problem**: Despite the `comm -23` pre-filter, 6 duplicate events were written because the timestamp-based ID function produced collisions in a tight loop.

**Fix**: Post-write dedup pass reads all events, keeps first occurrence per `event_id`, rewrites. This is now a mandatory step in the ingest script (step 4/6).

## System State Post-Run
| Metric | Value |
|--------|-------|
| events.jsonl | 124 |
| lessons.jsonl | 63 |
| shifts.jsonl | 29 (12 active / 12 cap) |
| journals_evaluated.jsonl | 3,691 |
| evidence.jsonl | 44 |

## SKILL.md Updates
- Added gotcha: **Batch event ID collision** — `datetime.now()` microsecond granularity is insufficient
- Added gotcha: **Lesson source_event_ids can reference phantom events after dedup**

## Observations
- **Shift cap at 12/12**: Next ingest cycle with a new pattern will require merge/expire. The 12 active shifts include several generic "verify preconditions" variants that could be consolidated.
- **Casascius sweep noise**: 3 ocas-spot sweeps were evaluated as no-signal (routine nominal). These are expected and correct — no events should be recorded for routine successful sweeps.
- **Custodian auth token**: This is a real user-actionable issue. The shift recommends alerting the user rather than silently proceeding with degraded monitoring.
