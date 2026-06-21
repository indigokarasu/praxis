# Praxis Ingest — 2026-06-25 Session Notes

## New Gotchas Discovered

### `journals_evaluated.jsonl` Mixed Format Crash

**Problem:** The eval file contains entries in two different formats:
1. Plain strings from shell rebuild operations: `"ocas-forge/2026-06-18/r_20260618_journal-scan-1781851338"`
2. JSON dicts from Python ingest scripts: `{"journal_id": "...", "evaluated_at": "...", ...}`

After `json.loads()`, plain strings become `str` objects. Calling `.get("journal_id")` on a `str` raises `AttributeError: 'str' object has no attribute 'get'`, crashing the ingest.

**Fix:** When building the evaluated set, check `isinstance(e, dict)` before `.get()`:
```python
for line in f:
    line = line.strip()
    if not line:
        continue
    try:
        e = json.loads(line)
    except json.JSONDecodeError:
        continue
    if isinstance(e, str):
        evaluated.add(e)
        continue
    if isinstance(e, dict):
        jid = e.get("journal_id", "")
        if jid:
            evaluated.add(jid)
            evaluated.add(jid + ".json")
```

**Impact:** First run of ingest_cron_20260625.py crashed immediately. Fixed by adding isinstance check.

### Finch Journal Schema Variance

**Problem:** Not all finch scan journals use the same schema. The `actionable` and `new_tasks_added` fields are not always present. Some scans use `findings` and `tasks_updated` instead.

**Fix:** Use safe defaults: `data.get("actionable", 0)` returns 0 when missing. For `new_tasks_added`, use `data.get("new_tasks_added") or []` to coerce None to empty list before `len()`.

**Impact:** Without the `or []` guard, `len(None)` would crash.

## Ingest Results

- 16 unevaluated journals found
- All 16 correctly filtered as no-signal (mentor-light routine, forge no-op, spot observation, finch no actionable)
- 0 new events, 0 new lessons, 0 new shifts
- Active shifts: 12/12 (cap full)
- Total events: 2,598
- Total lessons: 50

## System State

- Stable, quiet period
- All journals from June 20-25 evaluated
- No new behavioral signals detected
- Shift cap at 12/12 blocks new activations until decay
