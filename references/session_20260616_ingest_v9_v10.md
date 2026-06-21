# Session 2026-06-16 Praxis Ingest v9/v10 — Cap Enforcement Bug & Lesson Null-Phase Filter

## Summary

Two-pass ingest of 2 new `ocas-forge` journals (both routine no-op scans). First attempt (v9) produced a cascade of bad lessons and shifts due to two bugs. Second attempt (v10) was targeted and clean.

## What Happened

### v9 Full Scan (2,501 journals, 2 unevaluated)
- Both new journals were `ocas-forge` no-op scans (`result: "clean"`)
- Extracted 2 `no_op` events — correct
- Lesson extraction then ran against ALL 552+2 events on disk
- Produced 26 new lessons — **BUG**: didn't filter events with `null`/`None` phases before grouping
- Activated 5 shifts when cap was already at 12 — **BUG**: `active_shifts` list mutated during activation loop
- 15 additional shifts proposed at cap

### Cleanup
- Expired 20 bad v9 shifts
- Removed 5 bad v9 lessons (null-phase)
- Removed 2 bad v9 events
- State restored to 6 active shifts, 66 lessons, 552 events

### v10 Targeted Re-ingest (2 journals only)
- Processed same 2 forge journals
- Extracted 2 `no_op` events (deduped by source_journal)
- No new lessons (no_op+Execution already well-represented, threshold not crossed)
- No new shifts needed
- Clean completion: 6 active shifts, 66 lessons, 554 events

## Bugs Discovered

### 1. Cap Enforcement via Mutable List (NEW)

**Symptom**: 5 shifts activated when cap was already at 12.

**Root cause**: The activation loop appended each newly activated shift to `active_shifts` and checked `len(active_shifts) < CAP`. Since the list grew on every iteration, the cap check always passed.

**Fix**: Use a separate counter variable computed once before the loop:
```python
active_count = len([s for s in all_shifts if s.get('status') == 'active'])
# Inside loop:
if active_count < CAP:
    shift["status"] = "active"
    active_count += 1
```

**Files updated**: `SKILL.md`, `references/ingest-script-pattern.md` (Shift Activation section), `references/gotchas-praxis.md`

### 2. Lesson Extraction from Events with Null Phases (NEW)

**Symptom**: 26 lessons produced with phases like "None", "null", "MISSING".

**Root cause**: Lesson extraction grouped events by `(signal_type, failure_phase)` without filtering out events where `failure_phase` was `None`, `null`, or empty. 90 events (86 null + 4 None + 1 MISSING) from legacy ingest runs produced meaningless lesson groups.

**Fix**: Filter events before grouping:
```python
valid_events = [e for e in all_events 
                if str(e.get('failure_phase', '')).lower() not in ('none', 'null', '', 'missing')]
```

Also: normalize phase to lowercase in lesson content dedup to prevent case-variance duplicates.

**Files updated**: `SKILL.md`, `references/ingest-script-pattern.md` (Lesson Content Dedup section), `references/gotchas-praxis.md`

## Journal State After v10

| Metric | Count |
|--------|-------|
| Events | 554 |
| Lessons | 66 |
| Active Shifts | 6 |
| Proposed Shifts | 45 |
| Expired Shifts | 26 |
| Evaluated Journals | 2,546 |

## Key Takeaway

Two distinct bugs in the same ingest run — both related to not validating data before using it in loops. The cap enforcement bug is a classic mutable-state-in-loop issue. The null-phase bug is a data quality issue that's been lurking in the event store for weeks (90 legacy events with invalid phases). Both are now documented in gotchas and the ingest script pattern.
