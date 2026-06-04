# Production-Proven Ingest Script Pattern

## Overview

The Praxis journal ingest follows a specific multi-step pattern refined across 15+ production sessions. This document captures the exact approach so future ingest runs don't rediscover it.

## Mandatory Pre-Scan Steps

### 1. Deduplicate `journals_evaluated.jsonl`

```python
import json

eval_entries = []
seen_ids = set()
with open(EVAL_FILE, 'r') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        jid = entry.get("journal_id", "")
        if jid not in seen_ids:
            seen_ids.add(jid)
            eval_entries.append(entry)

with open(EVAL_FILE, 'w') as f:
    for e in eval_entries:
        f.write(json.dumps(e) + "\n")
```

Use JSON-aware parsing (Python `json.loads`), NOT `grep`/`comm` which fail on mixed formats.

### 2. Scan filesystem for journal files

```python
import os

JOURNALS_DIR = "/root/.hermes/commons/journals"
SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}

all_files = []
for root_dir, dirs, files in os.walk(JOURNALS_DIR):
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    parts = root_dir.replace(JOURNALS_DIR, "").strip('/').split('/')
    if parts and parts[0] in SKIP_DIRS:
        continue
    for fname in files:
        if fname.endswith('.json'):
            full_path = os.path.join(root_dir, fname)
            rel_path = os.path.relpath(full_path, JOURNALS_DIR)
            path_parts = rel_path.split('/')
            if len(path_parts) >= 2:
                date_dir = path_parts[1] if len(path_parts) > 1 else ""
                if date_dir in (today, yesterday):
                    skill = path_parts[0]
                    canonical = f"{skill}/{date_dir}/{fname}"
                    all_files.append((canonical, full_path))
```

### 3. Compute unevaluated set (set difference)

```python
seen_ids = {e.get("journal_id", "") for e in eval_entries}
unevaluated = [(c, p) for c, p in all_files if c not in seen_ids]
```

Do NOT use `comm -23` — it fails on unsorted legacy entries and concurrent-write visibility issues.

## Signal Extraction Checklist

For each unevaluated journal, check in this order:

1. Top-level `escalation_needed: true`
2. `decision.execution_result.status` — `ok`, `partial`, or `error`
3. `decision.summary` (or top-level `summary`) — only if non-empty string
4. `actions_taken[].outcome` — error/failure/correction
5. Top-level `fixes_applied` count
6. `checks.fixes_applied > 0`
7. `new_findings[]` — check `title`, `severity`, `detail`
8. For finch scan journals: `sources.*.status` and `new_tasks_added[]`
9. For list-format journals: check `isinstance(data, list)` first
10. For dict-format summaries: use `json.dumps(d)` for keyword scanning

**Guard every field access.** Check `isinstance(summary, str)` before `.lower()`. Check `if summary and len(summary.strip()) > 0` before keyword matching.

## Event Recording Rules

- Record ONLY when a real signal is found (error, partial, escalation, failure keywords)
- Do NOT record observation events for routine no-op journals
- Tag every event with `failure_phase` (planning/execution/response/null)
- Use canonical signal_type values: `auth_failure`, `escalation`, `execution_error`, `correction`, etc.
- Legacy schema events with `signal_type` in `("unknown", "?", None, "")` are noise — skip them

## Post-Write Dedup (MANDATORY)

After appending events to `events.jsonl`:
1. Read ALL events from disk
2. Group by `source_journal`
3. If duplicates exist (same `source_journal`), keep the earliest `recorded_at`
4. Rewrite `events.jsonl` with deduplicated list

## Lesson Extraction — Two-Pass Pattern (MANDATORY)

### Pass 1: Initial Extraction
1. Re-read `events.jsonl` from disk (newly written events must be visible)
2. Filter to meaningful events (skip unknown/?/None signal_types)
3. Group by `(signal_type, failure_phase)`
4. Extract lessons for groups with 2+ events
5. Write lesson stubs (they will be `confidence: low`)

### Pass 2: Causal Grounding Upgrade
1. For each low-confidence lesson, add full what/why/when grounding
2. Use event evidence and domain knowledge:
   - **What**: specific pattern observed (include event count)
   - **Why**: causal mechanism (not just symptom description)
   - **When**: boundary conditions (when does this apply vs. not)
3. Set `confidence: high` and add `causal_grounding` dict
4. Rewrite `lessons.jsonl`

**Do NOT skip Pass 2.** Without it, no lessons can produce shifts.

## Shift Activation

1. Read all shifts from `shifts.jsonl`
2. Active shifts = `status: "active"`, Proposed = `status: "proposed"`
3. **Merge-overlap check**: For each proposed shift, check domain+phase against all active shifts
   - Use `s.get('shift_id') or s.get('id', '?')` for shift IDs
   - Use `s.get('failure_phase') or s.get('phase', 'execution')` for phase
   - Use `s.get('domain')` — if empty, fall back to lesson's `skills_affected[0]` or source journal skill
4. If overlap found: expire proposed shift, reinforce active one
5. If no overlap and under cap (12): activate proposed shift
6. If at cap: leave proposed for next cycle

## Key Constants

- Active shift cap: 12
- Shift TTL (decay): 14 days without reinforcement
- Journal scan window: today + yesterday
- Skip directories: `ocas-praxis`, `ocas-lucid`, `.archive`
