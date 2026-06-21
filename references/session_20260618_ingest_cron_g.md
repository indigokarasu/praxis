# Session 2026-06-18: Journal Ingest Cron

## Summary

Praxis journal ingest cron ran successfully. 499 new journals processed, 82 new events extracted.

## Key Findings

### 1. Two Journal Directory Paths Exist

- `/root/.hermes/commons/journals/` — 2,929 files (legacy/default profile)
- `/root/.hermes/profiles/indigo/commons/journals/` — 7,667 files (indigo profile, active)

The indigo profile path contains the active, up-to-date journals. The skill's `ingest-script-pattern.md` incorrectly references `/root/.hermes/commons/journals/`. **Fix:** Always use `/root/.hermes/profiles/indigo/commons/journals/`.

### 2. `tier_1_fixes_applied` Int-vs-List Bug

Custodian journals store `tier_1_fixes_applied` as either an integer count or a list. The ingest script crashed with `TypeError: object of type 'int' has no len()` when calling `len()` on the field.

**Fix applied:**
```python
fixes = data.get("tier_1_fixes_applied", [])
fixes_count = fixes if isinstance(fixes, int) else len(fixes) if isinstance(fixes, list) else 0
```

### 3. `new_errors` None Guard

Custodian journals may have `new_errors: null`. Need `or []` guard:
```python
new_errors = data.get("new_errors", []) or []
```

### 4. Active Shift Cap Full at 12/12

All 12 active shift slots are filled with 0 reinforcements. All shifts are approaching the 14-day decay threshold. A decay check should be run soon.

### 5. Eval File Growth

`journals_evaluated.jsonl` is at 3,954 entries (928K). Approaching the 5,000 compaction threshold. Next ingest should include compaction.

## Ingest Script

- Written to: `ingest_cron_20260618_g.py`
- Processed: 499 journals (from 5,147 unevaluated, batched at 500)
- New events: 82 (80 escalation, 2 execution_error)
- New lessons: 0 (all signal_type+phase combinations already covered)
- New shifts: 0 (cap full)

## Recommendations

1. Fix `JOURNALS_DIR` in `ingest-script-pattern.md` to use profile-aware path
2. Run decay check on active shifts (all 12 are 0-reinforcement, approaching 14-day expiry)
3. Compact `journals_evaluated.jsonl` when it exceeds 5,000 entries
4. Consider running a full (non-batched) ingest to clear the 5,147 journal backlog
