# Praxis Inline Code Examples

Reference copy of code blocks embedded in SKILL.md. Load these only when you are
about to write or modify the corresponding artifact — do NOT read this file during
a normal ingest run.

## When to read

- **Before creating `ingest_state.json` for the first time** (or repairing a missing
  `last_lesson_extraction_event_id` field) → see "Ingest state bootstrap".
- **When fixing a broken `last_lesson_extraction_event_id` after a 0-event run**
  (the `null` vs `""` pitfall) → see "Repair last_lesson_extraction_event_id".
- **When writing or patching Bug 2 noise-lesson cleanup** → see
  `is_bug2_noise_lesson`.
- **When writing or patching lesson dedup** → see `lesson_dedup_key`.

---

## Ingest state bootstrap

The state file at `{agent_root}/commons/data/ocas-praxis/ingest_state.json` tracks
`last_lesson_extraction_event_id` for scoped lesson extraction. If the file doesn't
exist, create it with all required fields on first run:

```python
state = {
    "last_ingest_run": now.isoformat(),
    "last_ingest_mtime": now.timestamp(),
    "last_lesson_extraction_event_id": None,
    "journals_processed": 0,
    "total_ingests": 0,
    "last_evaluated_count": 0,
}
```

## Repair `last_lesson_extraction_event_id`

If the ingest state shows `last_lesson_extraction_event_id: null` or `""` (empty
string) but `events.jsonl` has entries, the scoping mechanism is broken — lesson
extraction will re-process the full history every run. Both `null` and `""` fail the
`event_id > marker` comparison. Fix by setting it to the last event's ID:

```bash
# Get the last event_id from events.jsonl
LAST_EVT=$(tail -1 {root}/commons/data/ocas-praxis/events.jsonl | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('event_id',''))")
# Update the state file — only set if LAST_EVT is non-empty
if [ -n "$LAST_EVT" ]; then
  python3 -c "import json; f='{root}/commons/data/ocas-praxis/ingest_state.json'; s=json.load(open(f)); s['last_lesson_extraction_event_id']='$LAST_EVT'; json.dump(s, open(f,'w'), indent=2)"
  echo "Set to $LAST_EVT"
else
  echo "events.jsonl empty or has no event_id field — leaving as-is"
fi
```

## Bug 2 noise-lesson classifier

Cleanup filters MUST check all four conditions (the `signal_type` key may be entirely
absent from Bug-2 noise lessons, not just set to `?`):

```python
def is_bug2_noise_lesson(les):
    st = les.get("signal_type")  # returns None if key missing
    if st is None:
        return True  # key missing entirely = Bug 2 noise
    st = str(st).strip().lower()
    if st in ("?", "", "null", "none"):
        return True
    if les.get("confidence") == "low":
        return True
    return False
```

## Lesson dedup key (normalize failure_phase)

The `(signal_type, failure_phase)` dedup key is case-sensitive; existing lessons may
use `Planning` while new ones use `planning`. Normalize both sides to lowercase:

```python
def lesson_dedup_key(les):
    st = les.get("signal_type", "").strip().lower()
    phase = les.get("failure_phase", "execution").strip().lower()
    return (st, phase)
```
