# Session 2026-06-27 Cron Ingest @ 20:32Z

**Run type:** Cron ingest (inline Python — production script bypassed due to known bugs)
**Findings:** 2 no-signal journals, 2 gap backfill, 0 events, 7 decay-risk shifts at 9d

## Why Inline Script Instead of Production Script

The production script `praxis_ingest_run.py` has three active bugs:
1. **Date filter too narrow** — only scans today/yesterday date directories, misses ~25% of journals
2. **Lesson extraction processes full history** — produces noise lessons from stale events
3. **Does not update `ingest_state.json`** — caller must update manually

When the cron window is tight (last ingest was <5 min ago) and the production script's date filter misses journals, an inline Python script using mtime-based discovery is more reliable for finding genuinely new journals.

## Inline Script Pattern (20:32Z)

```python
import json, os
from datetime import datetime, timezone

DATA_DIR = "/root/.hermes/profiles/indigo/commons/data/ocas-praxis"
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
STATE_FILE = os.path.join(DATA_DIR, "ingest_state.json")

now = datetime.now(timezone.utc)
now_iso = now.isoformat()

# Load state
with open(STATE_FILE) as f:
    state = json.load(f)

# Mtime-based discovery (both journal dirs)
JOURNAL_DIRS = [
    "/root/.hermes/profiles/indigo/commons/journals",
    "/root/.hermes/commons/journals"
]

# Load evaluated IDs (handle mixed formats)
evaluated = set()
with open(EVAL_FILE) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            entry = json.loads(line)
            if isinstance(entry, dict):
                evaluated.add(entry.get("journal_id", ""))
            elif isinstance(entry, str):
                evaluated.add(entry)
        except:
            evaluated.add(line)

# Expand with .json suffix variations
evaluated_expanded = set(evaluated)
for eid in evaluated:
    if eid.endswith(".json"):
        evaluated_expanded.add(eid[:-5])
    else:
        evaluated_expanded.add(eid + ".json")

# Find new journals via mtime comparison
li_ts = datetime.fromisoformat(state["last_ingest_run"]).timestamp()
new_journals = []
for jdir in JOURNAL_DIRS:
    if not os.path.isdir(jdir): continue
    for root, dirs, files in os.walk(jdir):
        for fname in files:
            if not fname.endswith(".json"): continue
            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, jdir)
            mtime = os.stat(fpath).st_mtime
            if mtime >= li_ts:
                continue  # already past last ingest
            if relpath in evaluated_expanded:
                continue  # already evaluated
            if relpath.startswith("ocas-praxis/"):
                continue  # skip own output
            new_journals.append(relpath)
```

**Key difference from production script:** Uses mtime comparison against `last_ingest_run` instead of date-directory filter. Finds journals regardless of which date directory they were written to.

## Results

- **New journals found:** 2 (mentor-light routine, dispatch-wave no-op)
- **Gap backfill found:** 2 (dispatch-wave prior wave, mentor-light earlier heartbeat)
- **Events recorded:** 0 (both new journals were no-signal per gotcha filters)
- **Noise lessons cleaned:** 0 (none in this run — production script wasn't used)

## Decay Risk Update

7 of 9 active shifts remain at 9 days with 0 reinforcements. No change from the 18:04Z observation. These shifts will auto-expire at 14 days (2026-07-02) if not reinforced or consolidated.

## Operational Notes

- The 4-minute gap between the previous cron run (20:28) and this run (20:32) demonstrates that 30min cron cadence can produce near-consecutive runs with very few new journals. This is expected and not a failure.
- Gap backfill remains essential even with mtime-based discovery — 2 additional journals were found that the main scan missed (they had mtime < last_ingest_run but were in the evaluated set with a different format).
- Third-wave mitigation was NOT needed this session (no dispatch wave ran concurrently).
