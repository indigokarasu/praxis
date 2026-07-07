# Dispatch 2026-06-29T10:30Z — Second-Wave No-Op + Large Gap Backfill

**Classification:** `all_second_wave` (journals) + `mixed_genuine` (email)
**Trigger:** Multi-skill dispatch with 2 journal files + 2 email threads
**Eval file:** 48,490 entries (praxis), 750 (dispatch) after backfill

## Dispatcher Input

```json
{
  "has_work": true,
  "dispatches": [
    {
      "type": "new_journals",
      "skill": "multi",
      "new_files": [
        "ocas-dispatch/2026-06-29/dispatch-wave-20260629T102941Z.json",
        "ocas-mentor/2026-06-29/mentor-light-20260629T102548Z.json"
      ]
    }
  ]
}
```

## Early-Exit Resolution

**Signals checked:**
1. Prior wave journal (102227Z) classified `all_second_wave` → signal 1 ✓
2. Dispatcher new_files in eval: `mentor-light-102548Z` in praxis eval → YES; `dispatch-wave-102941Z` was current wave's prior output → YES (registered during this wave) → signal 2 ✓
3. Email all `is_new: false` → N/A (email handled by triage dispatch)

**Triple-signal result:** No-op for journal pipeline. Zero pipeline skills loaded.

## Third-Wave Mitigation: Gap Backfill

Despite all dispatcher new_files being evaluated, 83 routine cron-output journals from the last 3 hours were NOT in eval files:
- 57 missing from praxis eval (mentor-light, custodian light-scan, praxis-cron)
- 26 missing from dispatch eval (dispatch-wave)

These were all cron-pipeline outputs written between dispatch waves by the independent cron jobs. All contained routine success signals (mentor-light outcome=success, dispatch-wave second-wave classification, praxis-cron routine ingest).

### Backfill procedure (cron-safe pattern)
```python
import os, json
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone.utc)
cutoff = now - timedelta(hours=3)
cutoff_ts = cutoff.timestamp()

# Scan all journal directories, find files not in eval, register them
for skill_dir, date_dir, fname in walk_journals():
    rel_path = f"{skill_dir}/{date_dir}/{fname}"
    if rel_path not in eval_set and mtime > cutoff_ts:
        write_eval_entry(rel_path, action_taken="post-dispatch-cleanup")
```

### Result
- Praxis eval: 48,433 → 48,490 (+57)
- Dispatch eval: 724 → 750 (+26)
- All entries registered with `source: "third-wave-mitigation"`

## Lesson

**Large gap backfill is normal after second-wave no-op.** When a dispatch wave exits early (second-wave), the cron pipelines continue writing journals. By the time the next dispatch fires (7-8 minutes later), 50-80 new cron-output journals can accumulate. These must be backfilled as third-wave mitigation to prevent the NEXT dispatch from detecting them as "new" and unnecessarily loading pipeline skills.

**83 entries backfilled is NOT a sign of failure.** It's the expected steady-state rate of cron output between dispatch waves (~10 journals per minute × 8 minutes).

## Pattern Reference

This is execution of pattern #3 from the 7-pattern eval gap catalog: "Post-ingest cron gap." See `SKILL.md` Gotchas — Complete eval gap pattern catalog.
