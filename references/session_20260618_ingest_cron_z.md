# Session 2026-06-18 Ingest Cron Z — Findings

## Run Summary
- **Date:** 2026-06-18
- **Journals evaluated:** 20
- **New events:** 11
- **New lessons:** 1
- **New shifts activated:** 1
- **Active shifts:** 11/12

## New Journals Processed

### ocas-mentor (5 new journals, 2026-06-18)
All mentor-light heartbeats. Key signals:
- `gap_detected` in 2/5 journals (gap within tolerance)
- `low_coverage` in 1/5 journals (evaluation_coverage 0.30 < target 0.9)
- `success` in 3/5 journals (routine healthy heartbeats)

### ocas-custodian (1 new journal, 2026-06-17)
- Routine light scan: 116/116 jobs OK, 0 errors

### Legacy journals (14 files)
- Old mentor, finch, weave, sands, dispatch journals — mostly `success` or no signals

## Bugs Fixed This Session

### Domain garbling in shift proposal
**Problem:** Shift proposal used `source_events[0]` (an event_id) as domain instead of extracting skill from source_journal path.
**Fix:** Manually patched domain from `evt-20260618T013824-0000` to `ocas-mentor`.

### Phase case normalization gap
**Problem:** `Execution` vs `execution` caused duplicate `low_coverage` shifts.
**Fix:** Merged duplicates, kept higher-reinforcement one.

## New Finding: Mentor `low_coverage` is Expected Behavior

The `evaluation_coverage` metric in mentor-light heartbeats (0.14-0.30) only counts skills with new journal entries, NOT total active skills. This is expected — the metric measures scan yield, not system health.

**Recommendation:** Filter `low_coverage` as noise when source is mentor-light journals specifically. Do NOT add `low_coverage` globally to NOISE_SIGNAL_TYPES (could be legitimate from other sources).

## Recommendations
1. Filter mentor-light `low_coverage` at extraction time
2. Normalize phase to lowercase before dedup in lesson extraction
3. Always extract domain from source_journal path, never from event_id
