# Dispatch 2026-06-26: append_jsonl Dict-Key Corruption Bug

## Summary

During a routine multi-skill dispatch (email triage + Praxis journal ingest), the `append_jsonl` function in `praxis_common.py` silently corrupted `journals_evaluated.jsonl` by writing dict keys as bare strings instead of JSON objects.

## Root Cause

`append_jsonl(path, records)` iterates over `records` and calls `json.dumps(r)` on each element. When callers passed a **single dict** (e.g., `append_jsonl(EVAL_FILE, {"journal_id": ..., "action_taken": ...})`), Python iterated over the dict's **keys** (strings), writing each key as a separate line:

```
"journal_id"
"evaluated_at"
"action_taken"
"reason"
```

This corrupted the JSONL file with 8 bare-string entries that broke downstream `json.loads()` parsing.

## Trigger Pattern

The bug fires when `append_jsonl` is called with a single dict instead of a list:
```python
# BUG — iterates over dict keys
append_jsonl(EVAL_FILE, {"journal_id": jid, "evaluated_at": now, ...})

# CORRECT — wraps in list
append_jsonl(EVAL_FILE, [{"journal_id": jid, "evaluated_at": now, ...}])
```

## Fix Applied

Added a guard at the top of `append_jsonl`:
```python
if isinstance(records, dict):
    records = [records]
```

This auto-wraps single-dict calls, making the function safe for both calling conventions.

## Detection

After every Praxis ingest run, verify the eval file tail:
```bash
tail -5 journals_evaluated.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        obj = json.loads(line)
        assert isinstance(obj, dict), f'NOT A DICT: {line}'
    except (json.JSONDecodeError, AssertionError) as e:
        print(f'CORRUPTED: {e}')
"
```

## Recovery

If corruption is detected, filter and rewrite:
```python
valid = []
with open('journals_evaluated.jsonl') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                valid.append(line)
        except json.JSONDecodeError:
            pass  # skip corrupted lines
with open('journals_evaluated.jsonl', 'w') as f:
    for line in valid:
        f.write(line + '\n')
```

## Lesson

When writing utility functions that iterate over "records", always handle the single-item case explicitly. Python's iteration over a dict yields keys, not items — a silent corruption that only manifests downstream.
