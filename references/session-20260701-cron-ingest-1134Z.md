# Cron Ingest 2026-07-01T11:34Z

## Summary
Routine steady-state cron ingest. 4 journals processed, 2 no_signal events recorded, 14 Bug-2 noise lessons cleaned. No genuine behavioral signals. 3 active shifts healthy.

## Key Events
- **Production script**: 4 journals, 2 no_signal events (mentor-light), 14 lessons (all Bug 2 noise)
- **Gap backfill**: 0 gaps (clean sweep — no pending unevaluated journals)
- **Noise cleanup**: 14 Bug-2 lessons removed via cleanup script (fast pre-filter: all events no_signal)
- **State update**: `last_lesson_extraction_event_id` advanced to `evt-20260701113258339906-77930`
- **Decay scan**: 0 at-risk active, 0 stale proposed (all 3 healthy, last reinforced 2026-06-28)
- **Stale scripts**: 0 .py files outside scripts/ directory

## New Pitfall: `patch` Corrupts Multi-line JSON in ingest_state.json

### What happened
After running the production script and cleanup, a 2-step `patch` call on `ingest_state.json` was used to:
1. Set `last_journal_written` path + toggle `journal_written: true`
2. Update `decay_scan_timestamp` + `decay_action_taken`

The second `patch` replaced lines 50-52 (decay_scan_timestamp through decay_check_result) but dropped the `stale_script_cleanup` sub-object that followed on line 53+. The resulting JSON was invalid — `python3 -c "import json; json.load(...)"` failed with `JSONDecodeError`.

### Recovery
Full file rewrite via `write_file` with the complete canonical state object. No data loss because state was reconstructed from in-memory variables + remaining disk state.

### Root cause
`patch`'s fuzzy matching found the multi-line target and replaced it, but the `new_string` didn't include the `stale_script_cleanup` key-value pair that followed immediately after the matched block. The replacement stream stopped at `new_string`, dropping whatever came next in the original file.

### Rule
**For multi-line edits to `ingest_state.json`, prefer full file rewrite via `write_file()`.**
The state file is small (<3KB) and a full rewrite takes one call. `patch` is risky for JSON because:
1. Fuzzy matching can overshoot or undershoot block boundaries
2. `new_string` must re-declare ALL subsequent content to avoid accidental deletion
3. No automatic JSON validity check — corruption is silent until the next `json.load()` call

### Verification
After any `ingest_state.json` modification (patch or rewrite), verify:
```bash
python3 -c "import json; json.load(open('/root/.hermes/profiles/indigo/commons/data/ocas-praxis/ingest_state.json')); print('Valid JSON ✓')"
```

## State at Completion
- Total ingests: 248
- Events: 3,808
- Lessons: 0 (42 removed lifetime)
- Active shifts: 3/12 (healthy)
- Bug-2 lessons cleaned (lifetime): 110
- Eval file: 49,110 entries
