# Gotcha: ingest_state.json active_shifts_count vs shifts.jsonl mismatch

## Symptom

`ingest_state.json` reports `active_shifts_count: 9` but filtering `shifts.jsonl` by `status == "active"` returns only 4 entries.

## Root Cause

The ingest scripts that update `ingest_state.json` may:
1. Count both `active` + `proposed` status shifts
2. Use a different status value (e.g., counting `extracted` lessons as shift-adjacent)
3. Not re-count after shift expiration (stale count from last bulk update)

## Workaround

**Always use `shifts.jsonl` filtered by `status == "active"` as ground truth for active shift count.**

`ingest_state.json:active_shifts_count` is useful as a quick trend indicator but not as an authoritative count.

## When Observed

- 2026-06-24: state=9, shifts.jsonl active=4. Difference was 5 (likely proposed/expired entries miscounted).

## Fix Needed

The ingest script (`praxis_ingest_run.py`) should recompute `active_shifts_count` from `shifts.jsonl` at the end of each run rather than incrementally updating.
