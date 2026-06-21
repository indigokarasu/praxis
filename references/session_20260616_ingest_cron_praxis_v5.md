# Session 2026-06-16 Praxis Ingest Cron v5

## Summary

Praxis journal ingest cron run. Scanned 12 unevaluated journals from 2026-06-16. All were routine no-ops — no new behavioral signals, lessons, or shifts.

## Journals Scanned

| Skill | Count | Signals | Notes |
|-------|-------|---------|-------|
| ocas-forge | 10 | all no-op | `clean`, `no_op`, `no_unprocessed_files` variants. All scan directories empty. |
| ocas-spot | 1 | no events | Observation sweep, all 4 watches inactive/skipped. Transient platform state. |
| ocas-finch | 1 | no events | scan-1913. Same 3 transient cron errors. 0 new errors, 0 actionable emails. |

## Bugs Encountered

### 1. Event Schema Mismatch (`outcome_type` vs `signal_type`)

**Symptom:** v4 ingest script crashed with `KeyError: 'signal_type'` during lesson extraction.

**Root cause:** `events.jsonl` contains two schemas:
- Legacy (pre-2026-06-15): uses `outcome_type` + `domain` + `source_journal` (no `signal_type`, no `skill`)
- Current: uses `signal_type` + `skill` + `source_journal`

The lesson extraction code accessed `evt["signal_type"]` directly, which crashes on legacy events.

**Fix:** Added `get_signal_type()` helper:
```python
def get_signal_type(evt):
    return evt.get("signal_type") or evt.get("outcome_type") or "unknown"
```

**Status:** Fixed in v5 ingest script.

### 2. Forge Journal Double-Nested Path Canonicalization

**Symptom:** Some forge journals had canonical IDs like `ocas-forge/r_20260616_journal-scan-1781597158.json/r_20260616_journal-scan-1781597158.json` (double-nested).

**Root cause:** Forge cron jobs write to `ocas-forge/r_<timestamp>.json/` directories. The canonical ID computation `f"{skill}/{date_dir}/{fname}"` used the `r_` prefixed directory as `date_dir`, but the filename inside matched the directory name.

**Impact:** Eval entries had non-canonical IDs. Would cause re-scan on next cycle if the same path pattern appears.

**Fix:** In v5, the scan function uses `path_parts[-2]` as date_dir and `path_parts[-1]` as fname, normalizing nested paths.

### 3. Evidence Record Gap from Partial Crash

**Symptom:** v4 crash after writing eval entries but before evidence record left incomplete audit trail.

**Root cause:** Script crashed during lesson extraction (Step 6) after eval entries were already appended (Step 5). Evidence (Step 8) was never written.

**Fix:** In v5, evidence is written immediately after signal extraction completes, before lesson extraction. Also added retroactive evidence record for v4.

## System State After Run

- Events: 550 total (no new)
- Lessons: 45 high-confidence (no new)
- Shifts: 6 active / 45 proposed / 6 expired
- Evaluated journals: 2,533
- Active shift cap: 6/12

## Micro-Lessons

- Forge stable: 10+ consecutive no-op scans confirm healthy idle state
- Spot watches inactive: All 4 venues inactive 3+ days, no booking opportunities
- Finch cron errors unchanged: Same 3 transient errors, no infrastructure action needed
