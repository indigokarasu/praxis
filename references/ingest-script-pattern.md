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

### 1b. Compact if >5,000 entries

After dedup, if the entry count exceeds 5,000, remove entries older than 30 days to keep scan diffs fast:

```python
from datetime import datetime, timedelta, timezone

if len(eval_entries) > 5000:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    # Keep entries that are either recent OR lack an evaluated_at (safety)
    compacted = [e for e in eval_entries
                 if e.get("evaluated_at", "9999") > cutoff
                 or not e.get("evaluated_at")]
    removed = len(eval_entries) - len(compacted)
    if removed > 0:
        eval_entries = compacted
        with open(EVAL_FILE, 'w') as f:
            for e in eval_entries:
                f.write(json.dumps(e) + "\n")
        print(f"    Compacted: removed {removed} entries older than 30 days")
```

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

### 3. Compute unevaluated set (set difference) + existence filter

```python
seen_ids = {e.get("journal_id", "") for e in eval_entries}
unevaluated = [(c, p) for c, p in all_files if c not in seen_ids and os.path.exists(p)]
```

The `os.path.exists(p)` guard is **mandatory** — journals may be deleted, moved, or rotated between the filesystem scan and the evaluation phase. Without this guard, the script will crash on `json.load()` for a missing file, losing all journals queued after the missing one.

Do NOT use `comm -23` — it fails on unsorted legacy entries and concurrent-write visibility issues.

## Signal Extraction Checklist

**CRITICAL: Apply noise filters from `journal_ingestion.md` inline during extraction.** Do not produce raw keyword matches for post-hoc review. Every signal must pass all noise filters before being emitted as an event candidate.

For each unevaluated journal, check in this order:

1. Top-level `escalation_needed: true`
2. `decision.execution_result.status` — `ok`, `partial`, `error`, or `completed_with_errors`. Any `error`, `partial`, or `completed_with_errors` result is a candidate for event recording. Also check top-level `status` for `"completed_with_errors"` — used by ocas-weave and other skills that report partial failure alongside partial success. Do NOT treat `"completed_with_errors"` as a success/no-signal status.
3. `decision.summary` (or top-level `summary`) — only if non-empty string
4. `actions_taken[].outcome` — error/failure/correction
5. Top-level `fixes_applied` count
6. `checks.fixes_applied > 0`
7. `new_findings[]` — check `title`, `severity`, `detail`
8. **Nested `findings[]` array** — scan each finding for `escalation_needed: true`, `status: "error"/"failed"`, and `action_taken` containing fix/correction keywords. This is the #1 missed signal path: custodian escalation-runner journals store per-finding escalation state inside `findings[]`, NOT at the top level. Always scan nested findings arrays regardless of top-level status.
9. For finch scan journals: check **both** `signals.*` and `sources.*` — finch journals use `signals.cron` (not `sources.cron`) for cron-related data. The `sources` key may be empty while `signals` contains all the data.
10. **Finch `signals.cron.new_errors[]`** — for each new error, extract the job name, error message, and severity. Each entry is a separate `cron_errors` signal. Also check `signals.cron.error_breakdown` for non-zero counts (`http_401`, `http_429`, `script_path_blocked`, `stale_401`). Also check `signals.*.notes` for escalation keywords.
10b. **Finch `tasks_added[]`** — check each task string for error/failure keywords. Tasks containing "error" or model names that failed are `failure_keyword` signals. Also check `tasks_resolved[]` for positive signals.
11. For list-format journals: check `isinstance(data, list)` first
12. For dict-format summaries: use `json.dumps(d)` for keyword scanning

**Guard every field access.** Check `isinstance(summary, str)` before `.lower()`. Check `if summary and len(summary.strip()) > 0` before keyword matching.

**Top-level `summary` string noise filter (MANDATORY):** Some journals (e.g., custodian light/deep scans, finch scans) store a plain string `summary` at the top level (not inside `decision`). These summaries often describe routine scan results and contain failure keywords in non-failure contexts — e.g., "All 13 error-state jobs are transient HTTP 429 rate limits" or "Calendar OAuth still expired" or "Cron errors stable at 15 (all 429s)." Keyword-matching these produces false-positive `failure_keyword` and `auth_failure` events. **Before emitting any `failure_keyword` signal from a top-level `summary` string, apply this semantic suppression check:**

```python
# Semantic suppression for failure_keyword signals from summary strings
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy"
]

def should_suppress_failure_keyword(summary_str, signals):
    \"\"\"Return True if failure_keyword signals should be suppressed.\"\"\"
    # Only suppress if the ONLY signals are failure_keyword (no escalation, execution_error, etc.)
    non_keyword_signals = [s for s in signals if s["type"] != "failure_keyword"]
    if non_keyword_signals:
        return False  # Real signals exist, don't suppress
    summary_lower = summary_str.lower()
    for phrase in SUPPRESS_PHRASES:
        if phrase in summary_lower:
            return True
    return False
```

**Apply this check after collecting all signals but before writing events.** If it returns `True`, clear all `failure_keyword` signals for that journal. If all signals were `failure_keyword`, the journal produces no events (only a `no_signal` eval_update). In the 2026-06-07 ingest, this filter would have prevented 5 false-positive events from custodian light scan and finch scan journals.

**`auth_failure` suppression gap (MANDATORY):** The `should_suppress_failure_keyword` function above only suppresses `failure_keyword` type signals. However, `auth_failure` signals extracted from summary keyword matching (e.g., "oauth", "token", "401") are equally susceptible to false positives in routine scan summaries — e.g., a finch scan summary saying "All cron jobs healthy. Google Calendar OAuth expired. No new errors" produces a false-positive `auth_failure` event. **Extend the suppression function to also cover `auth_failure`:**

```python
def should_suppress_summary_signals(summary_str, signals):
    \"\"\"Return True if summary-derived signals should be suppressed.\"\"\"
    # Only suppress if ALL signals are summary-derived keywords (no escalation, execution_error, etc.)
    SUMMARY_DERIVED_TYPES = {"failure_keyword", "auth_failure"}
    non_summary_signals = [s for s in signals if s["type"] not in SUMMARY_DERIVED_TYPES]
    if non_summary_signals:
        return False  # Real signals exist, don't suppress
    summary_lower = summary_str.lower()
    for phrase in SUPPRESS_PHRASES:
        if phrase in summary_lower:
            return True
    return False
```

**Use `should_suppress_summary_signals` (not `should_suppress_failure_keyword`) in all new ingest scripts.** It covers both `failure_keyword` and `auth_failure` from summary strings. In the 2026-06-07 ingest, the finch scan journal `scan-2210.json` produced a false-positive `auth_failure` event because the old filter didn't cover it.

**Schema-ambiguous journal noise filter (MANDATORY):** Some journals (e.g., ocas-elephas) use non-standard schemas without a top-level `status` field. When `data.get("status", "")` returns `""`, the noise filter `if status in ("ok", "success", "complete", "completed") and not signals` does NOT match, and the journal falls through without an eval_update. This causes two problems: (1) the journal is not marked as evaluated and will be re-scanned next cycle, and (2) if eval_updates are written in a batch append, the journal may inherit a wrong `action_taken` from a previous journal. **Fix:** After the signal extraction loop, if `signals` is empty AND no eval_update was appended for this journal, append a `no_signal` eval_update explicitly. Also handle the case where `status` is absent/empty by treating it as a non-failure when no other signals are present:

```python
# After all signal checks, before the signals guard:
if not signals:
    # No signals found — mark as no_signal regardless of status
    eval_updates.append({
        "journal_id": canonical,
        "evaluated_at": now,
        "action_taken": "no_signal",
        "signals_found": [],
        "reason": "No behavioral signals after noise filtering"
    })
    continue
```

This replaces the earlier pattern of checking `status in ("ok", ...)` as the sole no-signon filter.

**Nested scan rule:** Never rely solely on top-level fields. Always drill into `findings[]`, `sources.*`, and `new_findings[]` arrays. The initial extraction pass in the 2026-06-04 ingest missed 5 real signals (1 escalation, 2 platform_failures, 1 auth_failure, 1 execution_error) because the script only checked top-level `escalation_needed` and didn't scan `findings[].escalation_needed` or `sources.*.error_breakdown`. A targeted re-extraction pass recovered them. Build nested scanning into the initial pass to avoid this two-phase overhead.

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

**Known limitation:** Dedup by `source_journal` keeps only 1 event per journal file. A single journal can contain multiple distinct signal types (e.g., escalation + correction from different findings). When both signal types are important, consider deduping by `(source_journal, signal_type)` instead of just `source_journal`. This is especially relevant for custodian escalation-runner journals that may report both new escalations and auto-resolved issues in the same run.

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

### Lesson Content Dedup (MANDATORY — before writing any lesson)

**The `lesson_id` includes a random/timestamp component, so dedup by ID alone does NOT prevent semantic duplicates.** Each ingest run generates different IDs for the same `(signal_type, phase)` group, causing lesson accumulation (e.g., 49 "today" lessons when many are semantically identical).

**Fix: Dedup by content fingerprint, not just ID.**

```python
# Build set of (signal_type, failure_phase) tuples already covered by existing lessons
existing_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_groups.add(key)

# Only write lessons for groups not already covered
filtered_new_lessons = []
for lesson in new_lessons:
    key = (lesson.get("signal_type", ""), lesson.get("failure_phase", ""))
    if key in existing_groups:
        print(f"  Skipping duplicate lesson: signal_type={key[0]}, phase={key[1]}")
        continue
    existing_groups.add(key)
    filtered_new_lessons.append(lesson)

new_lessons = filtered_new_lessons
```

**Always apply content dedup BEFORE writing to `lessons.jsonl`.** The `lesson_id`-based dedup catches exact ID matches but NOT semantic duplicates with different IDs. Without this filter, `lessons.jsonl` grows by ~9-49 entries per ingest run with no new information.

**Verified production result**: On 2026-06-06, without content dedup, one ingest run produced 49 "today" lessons covering the same 16 `(signal_type, phase)` groups that already had lessons from prior runs. After adding content dedup, subsequent runs produce 0 duplicate lessons.

## Shift Proposal Dedup (MANDATORY — before proposing any new shift)

Active shifts reference lessons via heterogeneous fields: `lesson_id`, `source_lesson` (string), or `source_lesson_ids` (array). The dedup set MUST be built from ALL of these fields:

```python
# Build set of ALL lesson IDs referenced by active/proposed shifts
covered_lesson_ids = set()
for s in all_shifts:
    if s.get('status') in ('active', 'proposed'):
        for field in ['lesson_id', 'lesson_ref', 'source_lesson', 'source_lesson_ids']:
            val = s.get(field)
            if val:
                if isinstance(val, list):
                    covered_lesson_ids.update(val)
                elif isinstance(val, str):
                    covered_lesson_ids.add(val)

# Only propose shifts for lessons NOT already covered
for lesson in all_lessons:
    lid = get_lesson_id(lesson)
    if lesson.get('confidence') == 'high' and lid not in covered_lesson_ids:
        # ... propose shift ...
```

**Do NOT** check only `lesson_id` — this misses shifts using `source_lesson_ids` or `source_lesson`, causing hundreds of duplicate proposals.

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

## Schema Normalization Helpers (MANDATORY)

`events.jsonl` contains mixed schemas: v2.8+ events use `event_id` + `domain`, legacy events use `id` + `source`. `lessons.jsonl` uses `lesson_id` in production but `id` in the schema. `shifts.jsonl` uses `shift_id` in some entries and `id` in others.

**Define these helpers at the TOP of every ingest script, before any data loading:**

```python
def get_event_id(evt):
    """Normalize event ID across v2.8+ and legacy schemas."""
    return evt.get("event_id", evt.get("id", ""))

def get_event_domain(evt):
    """Normalize domain across v2.8+ and legacy schemas."""
    return evt.get("domain", evt.get("source", "unknown"))

def get_lesson_id(les):
    """Normalize lesson ID across production and schema variants."""
    return les.get("lesson_id", les.get("id", ""))

def get_shift_id(s):
    """Normalize shift ID across production and schema variants."""
    return s.get("shift_id", s.get("id", "?"))

def get_failure_phase(s):
    """Normalize failure phase across shift variants."""
    return s.get("failure_phase", s.get("phase", "execution"))
```

```python
def get_lesson_causal_grounding(les):
    """Normalize causal_grounding to dict. Legacy lessons may store it as a string."""
    cg = les.get("causal_grounding", {})
    if not isinstance(cg, dict):
        return {"what": str(cg), "why": "No causal grounding available", "when": ""}
    return cg
```

Use `cg = get_lesson_causal_grounding(les)` before any `.get("why")` or `.get("what")` access.

## Key Constants

- Active shift cap: 12
- Shift TTL (decay): 14 days without reinforcement
- Journal scan window: today + yesterday
- Skip directories: `ocas-praxis`, `ocas-lucid`, `.archive`

## Critical Fix: No-Early-Exit Path

When `unevaluated` is empty (no new journals found), the script must **NOT** exit before lesson extraction and shift proposal. The event backlog may not have been fully consolidated. Correct pattern:

```python
if not unevaluated:
    print("\n  No new journals to process.")
    # DO NOT exit here — continue to lesson extraction
    # Mark a no-op journal entry so the run is tracked
    run_id = f"r_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
    journal_path = os.path.join(JOURNAL_DIR, today)
    os.makedirs(journal_path, exist_ok=True)
    # ... write journal entry for tracking ...
    # BUT CONTINUE to Step 4b/5/6 below instead of calling exit(0)
```

The early-exit pattern (`exit(0)` or `return` when `len(unevaluated) == 0`) caused one ingest run to skip lesson extraction on a 91-event backlog, losing 8 high-defensibility lessons.

## Critical Fix: Shift Write Pattern (MANDATORY)

After reinforcing active shifts in memory, do NOT append them to `shifts.jsonl` alongside the originals — this creates duplicate active entries with the same `shift_id`, inflating the active count past the cap.

**Correct pattern:**
1. Read ALL shifts from disk into memory
2. Perform merge/reinforce against the in-memory list
3. Propose new shifts, check cap, activate/reject
4. **Rewrite** `shifts.jsonl` with the complete merged set (all statuses), NOT append
5. This ensures each `shift_id` appears exactly once

The append-only write pattern (`write_jsonl(SHIFTS_FILE, new_proposals, mode="a")`) is only safe for **new proposed shifts that have never been seen before**. Active/proposed shifts that were reinforced in memory must be written back by rewriting the entire file.

## File Path Pitfall

- **Verify JSONL filenames exactly** — A single character typo (e.g., `events.jsons` instead of `events.jsonl`) produces a silent 0-result from file reads. This caused one ingest run to report 0 total events and 0 lesson groups, leading to a "no lessons needed" conclusion that was incorrect. After loading any JSONL file, assert `len(records) > 0` if the file is known to have content, and double-check the filename.

- **`os.path.join` strips leading dot from path components** — `os.path.join("/root", "hermes/commons/data")` returns `/root/hermes/commons/data`, NOT `/root/.hermes/commons/data`. The `.` is treated as a relative path prefix and normalized away. When the agent home is `/root/.hermes/...`, always use **absolute string literals** for path constants, never `os.path.join` with a separate root variable:
  ```python
  # WRONG — produces /root/hermes/... (missing dot)
  AGENT_ROOT = "/root"
  DATA_DIR = os.path.join(AGENT_ROOT, "hermes/commons/data/ocas-praxis")

  # CORRECT — use absolute literals
  DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
  JOURNALS_DIR = "/root/.hermes/commons/journals"
  ```
  This caused one ingest run to silently write all output to the wrong path, then crash on `FileNotFoundError` on the first read-back. The run appeared to complete but all data was written to a nonexistent directory tree.

- **Write ingest scripts to `scripts/` subdirectory, NOT the data directory root** — The agent's file cleanup matches `ingest_*.py` and similar patterns. Scripts written directly to the data directory root (`ocas-praxis/ingest_run.py`) get silently removed before execution. Always write ad-hoc ingest scripts to `ocas-praxis/scripts/ingest_run_YYYYMMDD.py`. Production scripts (`praxis_review.py`, `praxis_ingest_run.py`, `praxis_self_signaler.py`, `update.sh`) are safe there.

- **Define helper functions before any code that calls them** — Ingest scripts may define utility functions (e.g., `get_lesson_id_from_proposal()`) inside a section that already uses them. If the function is defined after the loop that calls it, the script crashes with `NameError` at runtime. All helper functions must be defined at the top of the script or at least before the first call site. This is the same class of bug as the variable initialization gotchas — Python does not hoist function definitions.

## Python Variable Initialization in Ingest Scripts

- **Initialize `truly_new` before the `if new_events:` block** — Ingest scripts that define `truly_new` only inside a conditional block will raise `NameError` at decision-logging time if the condition is false. Always initialize `truly_new = []` before any conditional that might define it. Same applies to any variable used after a conditional block.
- **Initialize ALL accumulator variables before any loop or conditional** — Any variable referenced after a loop or conditional must be initialized before it. The pattern `if 'varname' in dir()` does NOT work (returns false positives from imported names). Examples:
  - `truly_new = []` before `if new_events:` block (existing gotcha)
  - `remaining_proposals = []` before `for proposal in new_proposals:` loop — without this, an empty `new_proposals` list causes `NameError` on the first reference after the loop because the `for/else` body never executed
  - Any `total`, `count`, `results`, or `output` variable used in post-loop print/log statements
  - Default: declare all accumulators at the top of the section, not inside any branch.
- **Never use `dir()` to check variable existence** — The pattern `if 'varname' in dir()` is fragile and returns false positives (matches function names, imported modules, etc.). Use explicit initialization or `try/except NameError` if truly dynamic.
- **Initialize `summary` before the `for entry in data_list` loop** — The `summary` variable is set inside the loop body (`summary = entry.get("summary", "")`) and referenced after the loop for noise suppression (`if isinstance(summary, str) and signals_found:`). If `data_list` is empty or contains no dict entries, `summary` is never assigned, causing `UnboundLocalError` at the suppression check. Always initialize `summary = ""` before the entry loop. Same class of bug as `truly_new`/`remaining_proposals` — any variable set inside a loop and used after it must be initialized before the loop.
- **Mixed event schemas in `events.jsonl`** — Legacy events may use `id` instead of `event_id`, and some may lack `source_journal`. When iterating events for lesson extraction, always use:
  - `e.get("event_id", e.get("id", "?"))` for event IDs
  - `e.get("source_journal", "")` with a guard before `.split("/")`
  - Filter to events that have `signal_type` in the meaningful set; legacy events without `signal_type` are noise
- **Lesson extraction runs against ALL events, not just new ones** — Each ingest cycle re-reads the full `events.jsonl` and re-extracts lessons for all groups with 2+ events. Dedup by checking `lesson_id` against existing `lessons.jsonl` — only write lessons whose `lesson_id` doesn't already exist. This means "new" lessons can appear even when no new journals were scanned, because the event backlog hadn't been fully consolidated yet.
