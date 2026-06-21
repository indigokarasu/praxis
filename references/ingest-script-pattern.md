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
        # Handle mixed formats: some entries are plain strings, some are JSON dicts
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            entry = line  # plain string entry

        if isinstance(entry, dict):
            jid = entry.get("journal_id", "")
        elif isinstance(entry, str):
            jid = entry
        else:
            continue

        if jid not in seen_ids:
            seen_ids.add(jid)
            # Normalize to dict format for consistent downstream handling
            if isinstance(entry, str):
                eval_entries.append({"journal_id": entry, "action_taken": "no_signal", "evaluated_at": "legacy"})
            else:
                eval_entries.append(entry)

with open(EVAL_FILE, 'w') as f:
    for e in eval_entries:
        f.write(json.dumps(e) + "\n")
```

Use JSON-aware parsing (Python `json.loads`), NOT `grep`/`comm` which fail on mixed formats. **CRITICAL:** The eval file accumulates both plain strings (from shell rebuilds) and JSON dicts (from Python ingest scripts). Always check `isinstance(entry, dict)` before calling `.get()`.

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

JOURNALS_DIR = "/root/.hermes/profiles/indigo/commons/journals"
SKIP_DIRS = {"ocas-praxis"}

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
                skill = path_parts[0]
                canonical = f"{skill}/{date_dir}/{fname}"
                all_files.append((canonical, full_path))
```

**CRITICAL: Eval IDs include `.json` extension.** The `journals_evaluated.jsonl` file stores journal IDs with the `.json` extension (e.g., `ocas-bones/2026-06-15/scan-20260615-1430.json`). Your `path_to_rel_id` function MUST preserve the extension. Stripping it causes ALL journals to appear unevaluated (4,661 instead of 86). Correct pattern:

```python
def path_to_rel_id(jf_path):
    """Convert absolute path to canonical journal_id. MUST keep .json extension."""
    parts = jf_path.parts
    try:
        idx = parts.index("journals")
    except ValueError:
        return None
    # Reconstruct relative path from journals/ root, KEEPING .json extension
    rel = "/".join(parts[idx+1:])
    return rel  # e.g., "ocas-bones/2026-06-15/scan-20260615-1430.json"
```

### 2b. Batch limit when unevaluated set is large

When the unevaluated set exceeds 500 journals, cap the batch to avoid timeout. Prioritize OCAS skill journals (which contain behavioral signals) over non-OCAS journals (mostly routine run logs):

```python
OCAS_SKILLS = {
    "ocas-mentor", "ocas-custodian", "ocas-forge", "ocas-spot",
    "ocas-finch", "ocas-sands", "ocas-rally", "ocas-taste",
    "ocas-dispatch", "ocas-elephas", "ocas-expansion", "ocas-bones",
    "ocas-bower", "ocas-fellow", "ocas-genie", "ocas-haiku",
    "ocas-imagine", "ocas-inception", "ocas-look", "ocas-lucid",
    "ocas-multipass", "ocas-reach", "ocas-sift", "ocas-vibes",
    "ocas-voyage", "ocas-weave", "ocas-vesper", "ocas-styx",
    "ocas-corvus", "ocas-actualization", "ocas-autobio",
}

MAX_BATCH = 500
ocas_uneval = [(jid, jf) for jid, jf in all_unevaluated if jid.split("/")[0] in OCAS_SKILLS]
other_uneval = [(jid, jf) for jid, jf in all_unevaluated if jid.split("/")[0] not in OCAS_SKILLS]

if len(ocas_uneval) + len(other_uneval) > MAX_BATCH:
    remaining = max(0, MAX_BATCH - len(ocas_uneval))
    to_process = ocas_uneval + other_uneval[:remaining]
else:
    to_process = all_unevaluated
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
12. For dict-format summaries: use `json.dumps(d)` for keyword scanning. **EXCEPTION: For finch scan journals (`ocas-finch` skill), do NOT use `json.dumps()` keyword scanning on dict summaries.** Finch scan summaries contain filenames (`drive.notable[]`), email subjects, and reference data that can include failure keywords (e.g., "exception" in a filename) without any actual system failure. Rely only on structured signal paths (`signals.*`, `findings[]`, `tasks_added[]`) for finch journals. See `gotchas-praxis.md` §Finch scan summary dict `json.dumps()` false positives.

**Guard every field access.** Check `isinstance(summary, str)` before `.lower()`. Check `if summary and len(summary.strip()) > 0` before keyword matching.

**Top-level `summary` string noise filter (MANDATORY):** Some journals (e.g., custodian light/deep scans, finch scans) store a plain string `summary` at the top level (not inside `decision`). These summaries often describe routine scan results and contain failure keywords in non-failure contexts — e.g., "All 13 error-state jobs are transient HTTP 429 rate limits" or "Calendar OAuth still expired" or "Cron errors stable at 15 (all 429s)." Keyword-matching these produces false-positive `failure_keyword` and `auth_failure` events. **Before emitting any `failure_keyword` signal from a top-level `summary` string, apply this semantic suppression check:**

```python
# Semantic suppression for failure_keyword signals from summary strings
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy",
    "escalations verified resolved", "escalations resolved",
    "no new urgent issues"
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

**Dispatch `auth_failure` false positive from dict summaries (MANDATORY):** ocas-dispatch journals store `summary` as a dict with fields like `gmail_auth_status: "unknown"`, `total_messages_scanned: 0`, etc. When this dict is converted to a string (via `json.dumps()` or `str()`), the word "auth" matches the `auth_failure` keyword filter — but `gmail_auth_status: "unknown"` is a routine scan result, not an actual auth failure. **Fix:** When the top-level `summary` is a dict AND the skill is `ocas-dispatch`, do NOT extract `auth_failure` signals from it. More broadly: for ALL skills, when `summary` is a dict, never extract `auth_failure` — the structured signal paths (`escalation_needed`, `execution_result.status`, etc.) are the only reliable auth failure indicators. In the 2026-06-14 ingest, 2 false-positive dispatch auth_failure events required manual cleanup.

**Spot sweep `failure_keyword` false positive from routine no-ops (MANDATORY):** ocas-spot sweep journals (not just "observation" type — many use type "sweep" or no type field) routinely report all watches inactive, skipped, or deactivated. Summaries contain "inactive", "skipped", "deactivated", "zero active watches" — which match failure keyword filters. These are routine no-op states. **Fix:** After extracting `failure_keyword` signals from spot journals, apply a secondary check: if the summary contains phrases like "all watches inactive", "zero active watches", "all skipped", "all deactivated", clear the `failure_keyword` signals as routine no-op. The existing spot observation handler only catches type "Observation" (capital O) — it misses type "sweep" and typeless spot journals entirely. In the 2026-06-14 ingest, 6 false-positive spot failure_keyword events required manual cleanup.

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

This replaces the earlier pattern of checking `status in ("ok", ...)` as the sole no-signal filter.

**`break` vs `continue` in per-journal no-op handlers (MANDATORY):** When a journal is identified as a no-op inside the `for canonical, fpath in unevaluated:` loop (forge returning `"clean"`/`"no_op"`, spot observation with all-skipped results, etc.), the handler MUST use `continue` — NOT `break`. `break` exits the entire loop, leaving all remaining journals unprocessed and skipping lesson extraction, shift proposal, decision logging, and the Praxis journal write. In the 2026-06-14 ingest, a `break` on the 3rd forge no-op (of 7 unevaluated) silently dropped 4 journals and all downstream steps. **Rule:** After writing a `no_signal` eval_update for a no-op journal, always `continue`. The only legitimate `break` is for `FileNotFoundError`.

**Nested scan rule:** Never rely solely on top-level fields.

### Mentor Journal Schema Variation: `evaluation_coverage` vs `coverage` (MANDATORY)
Mentor-light heartbeat journals use two schema variants:
- **Variant A** (older): `metrics.coverage` (float, 0.0–1.0) — the skill's behavioral coverage
- **Variant B** (newer): `metrics.evaluation_coverage` (float, 0.0–1.0) — Praxis's journal evaluation coverage

When extracting `low_coverage` signals from mentor journals, check `metrics.get("coverage")` ONLY.
Do NOT fall back to `evaluation_coverage` — it measures Praxis scan progress, not behavioral coverage.
If `coverage` key is absent, default to 1.0 (no low_coverage signal).

```python
# CORRECT — only check behavioral coverage
coverage = metrics.get("coverage", 1.0)  # absent → 1.0 → no signal

# WRONG — conflates evaluation coverage with behavioral coverage
coverage = metrics.get("coverage", metrics.get("evaluation_coverage", 1.0))
```

### Phase Case Normalization (MANDATORY)
Always normalize `failure_phase` to lowercase before grouping, dedup, and comparison:
```python
normalize_phase = lambda p: str(p).strip().lower()
```
Use `normalize_phase(phase)` in ALL lesson grouping keys, lesson dedup checks, and shift overlap comparisons.
Without this, `"Planning"` and `"planning"` are treated as separate groups, causing duplicate lessons
and preventing events from merging with existing lesson groups.

## Complete `extract_signals_from_dict` Reference Implementation

Every ingest script needs this function. Copy and adapt — don't reconstruct from scratch. The function below is production-tested across 15+ runs and handles all known schema variants:

```python
FORGE_NO_OP_RESULTS = {"no_op", "clean"}

def extract_signals_from_dict(data, skill):
    """Extract behavioral signals from a journal dict. Returns (signals, summary, status)."""
    signals = []
    summary = ""
    status = ""

    # Top-level status
    status = data.get("status", "")
    if isinstance(status, dict):
        status = status.get("status", "")

    # Top-level summary
    raw_summary = data.get("summary", "")
    if isinstance(raw_summary, str):
        summary = raw_summary
    elif isinstance(raw_summary, dict):
        # Don't keyword-scan dict summaries — high false positive risk
        # (dispatch gmail_auth_status, finch drive.notable filenames, etc.)
        summary = ""

    # Check escalation_needed
    if data.get("escalation_needed") is True:
        signals.append({"type": "escalation", "phase": "planning", "evidence": {"source": "top-level"}})

    # Check decision.execution_result.status
    decision = data.get("decision", {})
    if isinstance(decision, dict):
        exec_result = decision.get("execution_result", {})
        if isinstance(exec_result, dict):
            exec_status = exec_result.get("status", "")
            if exec_status in ("error", "partial"):
                signals.append({"type": "execution_error", "phase": "execution",
                                "evidence": {"exec_status": exec_status}})

        # Check decision.summary for keywords (only if non-empty string)
        dec_summary = decision.get("summary", "")
        if isinstance(dec_summary, str) and dec_summary.strip():
            dec_lower = dec_summary.lower()
            if any(kw in dec_lower for kw in ["failed", "failure", "error", "timeout", "exception"]):
                signals.append({"type": "failure_keyword", "phase": "execution",
                                "evidence": {"summary": dec_summary[:200]}})
            if any(kw in dec_lower for kw in ["oauth", "token", "401", "auth"]):
                signals.append({"type": "auth_failure", "phase": "execution",
                                "evidence": {"summary": dec_summary[:200]}})

    # Check actions_taken
    actions = data.get("actions_taken", [])
    if isinstance(actions, list):
        for action in actions:
            if isinstance(action, dict):
                outcome = action.get("outcome", "")
                if isinstance(outcome, str) and outcome.lower() in ("error", "failure", "failed"):
                    signals.append({"type": "execution_error", "phase": "execution",
                                    "evidence": {"action": action.get("action", "")}})

    # Check fixes_applied
    checks = data.get("checks", {})
    if isinstance(checks, dict) and checks.get("fixes_applied", 0) > 0:
        signals.append({"type": "correction", "phase": "execution",
                        "evidence": {"fixes_applied": checks["fixes_applied"]}})

    # Check new_findings
    findings = data.get("new_findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict):
                sev = finding.get("severity", "")
                if sev in ("error", "critical", "high"):
                    signals.append({"type": "escalation", "phase": "execution",
                                    "evidence": {"finding": finding.get("title", "")}})

    # Check nested findings array
    nested_findings = data.get("findings", [])
    if isinstance(nested_findings, list):
        for finding in nested_findings:
            if isinstance(finding, dict):
                f_status = finding.get("status", "")
                if f_status in ("error", "failed"):
                    signals.append({"type": "execution_error", "phase": "execution",
                                    "evidence": {"finding_status": f_status}})
                if finding.get("escalation_needed"):
                    signals.append({"type": "escalation", "phase": "execution",
                                    "evidence": {"finding_escalation": True}})

    # Check findings dict (finch-style)
    findings_dict = data.get("findings", {})
    if isinstance(findings_dict, dict):
        for src_name, src_data in findings_dict.items():
            if isinstance(src_data, dict):
                src_status = src_data.get("status", "")
                if src_status in ("ERROR", "error", "FAILED", "failed"):
                    signals.append({"type": "execution_error", "phase": "execution",
                                    "evidence": {"source": src_name, "status": src_status}})

    # Finch-specific: signals.* structure
    finch_signals = data.get("signals", {})
    if isinstance(finch_signals, dict):
        cron_data = finch_signals.get("cron", {})
        if isinstance(cron_data, dict):
            new_errors = cron_data.get("new_errors", [])
            if isinstance(new_errors, list) and new_errors:
                signals.append({"type": "cron_errors", "phase": "execution",
                                "evidence": {"count": len(new_errors)}})
            error_breakdown = cron_data.get("error_breakdown", {})
            if isinstance(error_breakdown, dict):
                for err_type, count in error_breakdown.items():
                    if isinstance(count, (int, float)) and count > 0:
                        signals.append({"type": "cron_errors", "phase": "execution",
                                        "evidence": {"error_type": err_type, "count": count}})
        tasks_added = finch_signals.get("tasks_added", [])
        if isinstance(tasks_added, list):
            for task in tasks_added:
                if isinstance(task, str) and any(kw in task.lower() for kw in ["error", "failed", "failure"]):
                    signals.append({"type": "failure_keyword", "phase": "execution",
                                    "evidence": {"task": task[:200]}})
        # Finch new_tasks_added is a list of dicts, not an int
        new_tasks_added = data.get("new_tasks_added", [])
        if isinstance(new_tasks_added, list) and len(new_tasks_added) > 0:
            signals.append({"type": "new_tasks_found", "phase": "execution",
                            "evidence": {"count": len(new_tasks_added)}})

    # Check for completed_with_errors status
    if status == "completed_with_errors":
        signals.append({"type": "completed_with_errors", "phase": "execution",
                        "evidence": {"status": status}})

    # Forge no-op filter — MUST come after signal extraction but BEFORE event recording.
    # Note: Do NOT check `files_processed` for forge activity detection — the field is a
    # list, not an int, and comparing it to 0 raises TypeError. The `result` field alone
    # is sufficient to distinguish no-op from activity.
    # Also checks `status` field: newer forge journals use `status: "complete"` (not `result`).
    # Also checks `action.result`: newest forge schema nests result under `action` key.
    if skill == "ocas-forge":
        result = data.get("result", "")
        forge_status = data.get("status", "")
        # Check nested action.result (new schema variant)
        action = data.get("action", {})
        if isinstance(action, dict):
            action_result = action.get("result", "")
            if isinstance(action_result, str) and action_result.lower().strip() in FORGE_NO_OP_RESULTS:
                return [], summary, status
        if isinstance(result, str) and result.lower().strip() in FORGE_NO_OP_RESULTS:
            return [], summary, status
        if isinstance(forge_status, str) and forge_status.lower().strip() in ("complete", "completed", "no_new_files", "clean"):
            return [], summary, status

    # Spot observation/sweep no-op filter
    if skill == "ocas-spot":
        obs_type = data.get("type", "")
        if isinstance(obs_type, str) and obs_type.lower() == "observation":
            results = data.get("results", [])
            if isinstance(results, list) and results:
                all_skipped = all(
                    isinstance(r, dict) and r.get("status", "").lower().startswith(("skipped", "deactivated"))
                    for r in results
                )
                if all_skipped:
                    return [], summary, status
        # Also check sweep-type spot journals for all-inactive no-op
        if isinstance(summary, str) and summary.strip():
            summary_lower = summary.lower()
            NO_OP_PHRASES = [
                "all watches inactive", "zero active watches", "all skipped",
                "all deactivated", "no active automatable", "all 4 watch records are inactive"
            ]
            if any(phrase in summary_lower for phrase in NO_OP_PHRASES) and not signals:
                return [], summary, status

    return signals, summary, status
```

**IMPORTANT:** Define this function BEFORE the `for canonical, fpath in unevaluated:` loop. Python does not hoist function definitions.

## Event Recording Rules

- Record ONLY when a real signal is found (error, partial, escalation, failure keywords)
- Do NOT record observation events for routine no-op journals
- Tag every event with `failure_phase` (planning/execution/response/null)
- Use canonical signal_type values: `auth_failure`, `escalation`, `execution_error`, `correction`, etc.
- Legacy schema events with `signal_type` in `("unknown", "?", None, "")` are noise — skip them

## Lesson Merge/Proposal — Schema Variance Gotchas (MANDATORY)

### Lesson `lesson_text` vs `summary` field variance
`lessons.jsonl` contains mixed schemas: production lessons use `lesson_text`, but legacy lessons use `summary` (and some use neither). When reading lessons for shift merge/proposal, use:
```python
text = l.get("lesson_text", "") or l.get("summary", "")
```
A `KeyError` on `lesson_text` crashes the shift merge loop and blocks all downstream processing. Discovered 2026-06-16: 2 lessons in `lessons.jsonl` used `summary` instead of `lesson_text`.

### Lesson Noise Gate (MANDATORY before writing any lesson)

Signal types that are routine system noise MUST NOT become lessons. Filter at lesson creation time, not at shift proposal time:

```python
NOISE_SIGNAL_TYPES = {"", "unknown", "?", "no_op", "forge_activity", "routine", "no_signal", "cron_error", "cron_errors", "observation"}
```
NOISE_SIGNAL_TYPES = {"", "unknown", "?", "no_op", "forge_activity", "routine", "no_signal", "cron_error", "cron_errors", "observation", "success",
    # Specific noise signal types observed in practice (2026-06-17 through 2026-06-18)
    "forge_no_unprocessed_files", "forge_no-op", "cron_healthy",
    "journal_entry", "mentor_light", "warning",
    "skipped", "coverage_gap", "no_action_needed",
    "observation",  # spot observation records are routine, not behavioral patterns (added 2026-06-18)
}
# After Pass 2 lesson extraction, before writing lessons to lessons.jsonl:
# MANDATORY: Filter out events with null/None/empty failure_phase BEFORE grouping
for lesson in new_lessons:
    if lesson.get("signal_type", "") in NOISE_SIGNAL_TYPES:
        print(f"  Skipping noise lesson: signal_type={lesson.get('signal_type')}")
        continue
    # ... write lesson ...
```

This prevents polluting the lesson pool with patterns like "routine no-op scans across 17 events" that produce non-actionable shifts.
`no_op` and `forge_activity` signal types can be extracted as valid lessons when forge no-op filtering misses edge cases. These are always routine and should be filtered at the lesson quality check:
```python
NOISE_SIGNAL_TYPES = {"", "unknown", "?", "no_op", "forge_activity", "routine", "no_signal", "cron_error", "cron_errors", "observation"}
if lesson.get("signal_type", "") in NOISE_SIGNAL_TYPES:
    continue  # Skip — routine system noise, not a behavioral pattern
```
In the 2026-06-16 ingest, 2 such lessons were extracted and had to be removed in post-hoc cleanup.

**2026-06-16 v2 ingest update:** `cron_error` and `cron_errors` added to NOISE_SIGNAL_TYPES. These are routine cron infrastructure signals (timeouts, rate limits, module import failures) — not behavioral patterns. The v2 ingest script did not apply this filter and produced 3 low-quality lessons (cron_error, forge_activity, no_op). All 3 should have been suppressed. The cleanup pattern below was used to remove them.

### Post-ingest lesson cleanup pattern
After every ingest run, run a cleanup pass that removes:
- Lessons with `signal_type` in `NOISE_SIGNAL_TYPES` (empty, unknown, no_op, forge_activity)
- Lessons with `confidence` != `high` (low-confidence stubs)
- Lessons where `lesson_text` and `summary` are both empty/malformed
- Any shifts that reference removed lessons (orphaned shift references)

```python
NOISE_SIGNAL_TYPES = {"", "unknown", "?", "no_op", "forge_activity"}

def cleanup_lessons_and_shifts(lessons_file, shifts_file):
    # Load and filter lessons
    kept_lessons = []
    removed_ids = set()
    with open(lessons_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            l = json.loads(line)
            sig = l.get("signal_type", "")
            text = l.get("lesson_text", "") or l.get("summary", "")
            if sig in NOISE_SIGNAL_TYPES or not text or len(text.strip()) < 10:
                removed_ids.add(l.get("lesson_id", l.get("id", "")))
                continue
            kept_lessons.append(l)
    
    # Rewrite lessons
    with open(lessons_file, "w") as f:
        for l in kept_lessons:
            f.write(json.dumps(l) + "\n")
    
    # Remove orphaned shifts (shifts referencing removed lesson IDs)
    kept_shifts = []
    with open(shifts_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            s = json.loads(line)
            source_lessons = s.get("source_lessons", [])
            if any(lid in removed_ids for lid in source_lessons):
                continue  # Remove shift referencing bad lesson
            kept_shifts.append(s)
    
    with open(shifts_file, "w") as f:
        for s in kept_shifts:
            f.write(json.dumps(s) + "\n")
    
    return len(kept_lessons), len(removed_ids)
```

## Post-Write Dedup (MANDATORY)

After appending events to `events.jsonl`:
1. Read ALL events from disk
2. Group by `source_journal`
3. If duplicates exist (same `source_journal`), keep the earliest `recorded_at`
4. Rewrite `events.jsonl` with deduplicated list

**Known limitation:** Dedup by `source_journal` keeps only 1 event per journal file. A single journal can contain multiple distinct signal types (e.g., escalation + correction from different findings). When both signal types are important, consider deduping by `(source_journal, signal_type)` instead of just `source_journal`. This is especially relevant for custodian escalation-runner journals that may report both new escalations and auto-resolved issues in the same run.

**Same-type multi-signal collision (MANDATORY recovery):** Even with `(source_journal, signal_type)` dedup, a journal containing multiple distinct issues of the same signal type (e.g., two different `execution_error` findings from one finch scan) will still collapse to one event. The second issue is silently lost. **Recovery pattern**: After writing events, count raw signals per journal before dedup. If a journal produced N signals but only M events survive dedup (N > M), log a `multi_signal_collision` warning in the journal entry and eval_update `reason` field. Example: `"reason": "Extracted 3 signal(s), 1 lost to dedup collision (finch scan-1508: 2 execution_error → 1 event)"`. To fully recover lost signals, manually append them as separate events with distinct `event_id` values and the same `source_journal`. Discovered 2026-06-13: finch scan-1508 produced 2 `execution_error` signals (dead script + context engine) but dedup collapsed them to 1 event; the context engine signal required manual recovery.

## Lesson Extraction — Two-Pass Pattern (MANDATORY)

### Pass 1: Initial Extraction
1. Re-read `events.jsonl` from disk (newly written events must be visible)
2. Filter to meaningful events (skip unknown/?/None signal_types, and any signal_type in `NOISE_SIGNAL_TYPES`)
3. Group by `(signal_type, failure_phase)` — normalize both to lowercase
4. Extract lessons for groups with 2+ events
5. **Noise gate before writing lesson stubs:** Check `st in NOISE_SIGNAL_TYPES` and skip. This filter MUST be applied here at grouping time, not just at event recording time. The event pool contains 2500+ events accumulated over weeks — noise types like `mentor_light` (288 events) and `coverage_gap` (11 events) will produce spurious lessons if not filtered at this step. See `session_20260618_ingest_cron_aa.md`.
6. Write lesson stubs (they will be `confidence: low`)

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
# Normalize to lowercase to prevent case-variance duplicates
existing_groups = set()
for l in existing_lessons:
    st = (l.get("signal_type", "") or "").strip().lower()
    fp = (l.get("failure_phase", "") or "").strip().lower()
    if st and fp and fp not in ("none", "null", ""):
        existing_groups.add((st, fp))

# Only write lessons for groups not already covered
filtered_new_lessons = []
for lesson in new_lessons:
    st = (lesson.get("signal_type", "") or "").strip().lower()
    fp = (lesson.get("failure_phase", "") or "").strip().lower()
    if not st or not fp or fp in ("none", "null", ""):
        print(f"  Skipping lesson with invalid phase: signal_type={st}, phase={fp}")
        continue
    if (st, fp) in existing_groups:
        print(f"  Skipping duplicate lesson: signal_type={st}, phase={fp}")
        continue
    existing_groups.add((st, fp))
    # Normalize phase to lowercase before writing
    lesson["failure_phase"] = fp
    filtered_new_lessons.append(lesson)

new_lessons = filtered_new_lessons
```

**Always apply content dedup BEFORE writing to `lessons.jsonl`.** The `lesson_id`-based dedup catches exact ID matches but NOT semantic duplicates with different IDs. Without this filter, `lessons.jsonl` grows by ~9-49 entries per ingest run with no new information.

**Phase validation is mandatory.** Events with `failure_phase` of `None`, `null`, `""`, or `"MISSING"` must be filtered out BEFORE the lesson grouping step. In the 2026-06-16 ingest, 90 events with invalid phases produced 26 meaningless lessons. Filter: `valid_events = [e for e in all_events if str(e.get('failure_phase', '')).lower() not in ('none', 'null', '', 'missing')]`

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

### Cap Enforcement via Priority Selection (MANDATORY — 2026-06-17)

When selecting which shifts to activate under the 12-shift cap, do NOT simply activate in proposal order and expire the oldest. Instead, build a candidate pool of ALL shifts (existing active + proposed), rank by priority tuple `(reinforcement_count, source_event_count, is_cross_skill, last_reinforced)`, and select the top 12. Expire the rest.

```python
def shift_priority(shift):
    """Calculate priority for shift selection. Higher = better. Tuple for multi-key sort."""
    reinf = shift.get('reinforcement_count', 0)
    event_count = shift.get('source_event_count', 0)
    is_cross_skill = 1 if shift.get('skill') == 'cross-skill' else 0
    last_reinf = shift.get('last_reinforced', '')
    return (reinf, event_count, is_cross_skill, last_reinf)

# Build candidate pool: existing active (some reinforced) + proposed
all_candidates = []
for s in active_shifts:
    if s.get('status') == 'active':
        s['_source'] = 'existing'
        all_candidates.append(s)
for s in proposed_shifts:
    s['_source'] = 'proposed'
    all_candidates.append(s)

# Sort by priority (highest first)
all_candidates.sort(key=shift_priority, reverse=True)

# Select top MAX_ACTIVE_SHIFTS
selected = all_candidates[:MAX_ACTIVE_SHIFTS]
rejected = all_candidates[MAX_ACTIVE_SHIFTS:]

# Update statuses
for s in all_candidates:
    if s in selected:
        s['status'] = 'active'
    else:
        s['status'] = 'rejected' if s.get('_source') == 'proposed' else 'expired'
```

This prevents the bug where activating in proposal order with a mutable `active_shifts` list caused newly added shifts to be immediately expired to make room for later ones, losing high-value shifts (e.g., execution_error with 19 reinforcements).

### Malformed Lesson Guard (MANDATORY — before proposing any shift)

Legacy ingest runs may create lesson entries with empty `signal_type` (e.g., `les-00000228995663230219-0001`). These stubs pass the `confidence == 'high'` check and get proposed as shifts with `signal_type: "unknown"` and `domain: "unknown"`, polluting the active shift list.

**Always validate lesson quality before proposing a shift:**

```python
for lesson in all_lessons:
    lid = get_lesson_id(lesson)
    st = lesson.get("signal_type", "")
    phase = lesson.get("failure_phase", "")

    # GUARD: skip malformed lessons (empty/unknown signal_type or missing phase)
    if not st or st in ("unknown", "?", ""):
        print(f"  Skipping malformed lesson: {lid} (signal_type='{st}')")
        continue
    if not phase:
        print(f"  Skipping malformed lesson: {lid} (failure_phase='{phase}')")
        continue

    if lesson.get('confidence') == 'high' and lid not in covered_lesson_ids:
        # ... propose shift ...
```

**If malformed lessons already exist in `lessons.jsonl`:** Remove them and any shifts that reference them. See `references/session_20260614_ingest.md` for the full cleanup procedure.

## Shift Activation

1. Read all shifts from `shifts.jsonl`
2. Active shifts = `status: "active"`, Proposed = `status: "proposed"`
3. **Compute active_count ONCE before the loop** — `active_count = len([s for s in all_shifts if s.get('status') == 'active'])`. Do NOT use `len(active_shifts)` inside the activation loop if you're appending to the same list.
4. **Merge-overlap check**: For each proposed shift, check domain+phase against all active shifts
   - Use `s.get('shift_id') or s.get('id', '?')` for shift IDs
   - Use `s.get('failure_phase') or s.get('phase', 'execution')` for phase
   - Use `s.get('domain')` — if empty, fall back to lesson's `skills_affected[0]` or source journal skill
5. If overlap found: expire proposed shift, reinforce active one
6. If no overlap and under cap (12): activate proposed shift, increment `active_count += 1`
7. If at cap: leave proposed for next cycle

**CRITICAL: Do NOT append activated shifts to the same list used for the cap check.** If you use `active_shifts.append(shift)` inside the loop and check `len(active_shifts) < CAP`, the list grows on every iteration and the cap is never enforced. Use a separate counter variable instead.

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

### Event Schema Normalization for Lesson Extraction (MANDATORY)

Events created by different ingest runs use different field names for the same semantic content. When reading events.jsonl for lesson extraction, normalize every event before use. Known field mappings: `type` -> `signal_type`, `summary`/`description` -> `evidence`, `source_skill` -> `skill`, `journal_id` -> `source_journal`. Always dedup by `(source_journal, signal_type)`, not just source_journal. See the normalize_events block in the production-proven extract_signals pattern.

## Batch Pre-Filter for Forge No-Ops (MANDATORY)

Before running full signal extraction on forge journals, apply a lightweight pre-filter to batch-process routine no-ops. This avoids the overhead of full `extract_signals_from_dict()` for the ~400+ routine forge scan journals that always return empty.

```python
FORGE_NO_OP_RESULTS = {"no_op", "clean", "no-op", "no_unprocessed_files", "no unprocessed"}

def is_forge_no_op(journal_data):
    """Check if a forge journal is a routine no-op. Handles both legacy and new schemas."""
    # Check top-level result (legacy schema)
    result = journal_data.get("result", "")
    # Check nested action.result (new schema variant)
    action = journal_data.get("action", {})
    if isinstance(action, dict):
        action_result = action.get("result", "")
        if isinstance(action_result, str):
            ar = action_result.lower().strip()
            if any(ar.startswith(prefix) for prefix in FORGE_NO_OP_RESULTS):
                return True
    # Check top-level result
    if isinstance(result, str):
        r = result.lower().strip()
        if any(r.startswith(prefix) for prefix in FORGE_NO_OP_RESULTS):
            return True
    # Check status field
    status = data.get("status", "")
    if isinstance(status, str) and status.lower().strip() in ("complete", "completed", "no_new_files", "clean"):
        return True
    # Check actions_taken as string (natural language no-op description)
    actions_taken = data.get("actions_taken", "")
    if isinstance(actions_taken, str):
        at_lower = actions_taken.lower().strip()
        if any(at_lower.startswith(prefix) for prefix in FORGE_NO_OP_RESULTS):
            return True
    # Check actions_taken as empty list (no actions = no-op)
    if isinstance(actions_taken, list) and len(actions_taken) == 0:
        # Empty actions_taken with no result/status = routine no-op
        # But only if no findings indicate actual work done
        findings = data.get("findings", {})
        if isinstance(findings, dict):
            total_findings = sum(v for v in findings.values() if isinstance(v, (int, float)))
            if total_findings == 0:
                return True
        elif not findings:
            return True
    return False
```

**Usage in ingest loop:**
```python
# Separate forge no-ops from meaningful journals
forge_no_op_batch = []
meaningful_journals = []

for skill, jid, fpath, rel_path in unevaluated:
    if skill == "ocas-forge":
        try:
            with open(fpath) as f:
                content = f.read().strip()
            if not content:
                # Mark empty as evaluated, skip
                continue
            journal_data = json.loads(content)
            if is_forge_no_op(journal_data):
                forge_no_op_batch.append((skill, jid, fpath, rel_path))
                continue
        except json.JSONDecodeError:
            # Mark malformed as evaluated, skip
            continue
    meaningful_journals.append((skill, jid, fpath, rel_path))

# Batch-mark forge no-ops
if forge_no_op_batch:
    batch_evaluated = []
    for skill, jid, fpath, rel_path in forge_no_op_batch:
        batch_evaluated.append({
            "journal_id": rel_path,
            "evaluated_at": now,
            "path": fpath,
            "action_taken": "batch_no_op",
            "signals_found": [],
            "reason": "Forge journal-scan no-op (batched)"
        })
    append_jsonl(EVALUATED_FILE, batch_evaluated)

# Process meaningful journals individually
for skill, jid, fpath, rel_path in meaningful_journals:
    # ... full signal extraction ...
```

**Why this matters:** Without the pre-filter, every forge journal goes through full JSON parsing + signal extraction + noise filtering. For ~400+ no-op journals, this adds ~30 seconds of unnecessary processing. The pre-filter reduces forge processing to a simple string comparison on 2 fields.

**Verified production result**: On 2026-06-16, 4 forge no-ops were batch-processed in <1 second vs. ~15 seconds for individual full extraction.

## Dual Journal Directory Scan (MANDATORY — 2026-06-19)

Journals are stored under BOTH paths:
- `/root/.hermes/commons/journals/` (legacy/default profile) — 2,988 files
- `/root/.hermes/profiles/indigo/commons/journals/` (indigo profile) — 7,682 files

The indigo profile path contains the active, up-to-date journals for mentor, custodian, and some other skills. The legacy path contains forge, finch, spot, and other skills.

**The ingest script MUST check both directories.** Use a `find_journal()` helper:

```python
JOURNALS_DIRS = [
    "/root/.hermes/commons/journals",
    "/root/.hermes/profiles/indigo/commons/journals",
]

def find_journal(jid):
    for d in JOURNALS_DIRS:
        fp = os.path.join(d, jid)
        if os.path.exists(fp):
            return fp
    return None
```

When scanning the filesystem for unevaluated journals, walk BOTH directories and use a single combined `seen` set for dedup. A journal ID like `ocas-forge/2026-06-17/scan-1234.json` may exist in either directory — never assume based on skill name alone.

**Verified**: On 2026-06-19, 11 unevaluated journals were split across both paths: forge/finch/spot in legacy, custodian/mentor in indigo profile. A script using only one path would miss half the new signals.

## Ingest State Update Gap (MANDATORY — 2026-06-21)

**The production `praxis_ingest_run.py` script does NOT update `ingest_state.json`.** When running it standalone (e.g., from a cron job), the state file is left with stale timestamps. This causes the next run's mtime-based journal discovery to miss journals written between the last state update and the current run.

**Fix:** After running `praxis_ingest_run.py`, manually update `ingest_state.json`:

```python
import json
from datetime import datetime, timezone

state_path = '/root/.hermes/profiles/indigo/commons/data/ocas-praxis/ingest_state.json'
with open(state_path) as f:
    state = json.load(f)

now = datetime.now(timezone.utc).isoformat()
state['last_ingest_run'] = now
state['last_run'] = now
state['last_ingest_events_added'] = <events_recorded>
state['last_ingest_journals_evaluated'] = <journals_processed>
state['last_evaluated_count'] = state.get('last_evaluated_count', 0) + <journals_processed>
state['note'] = '<summary>'

with open(state_path, 'w') as f:
    json.dump(state, f, indent=2)
```

The dispatch template (`dispatch_ingest_template.py`) handles this update. When running `praxis_ingest_run.py` directly (cron or manual), the caller MUST update state after the script completes.

## Key Constants

- Active shift cap: 12
- Shift TTL (decay): 14 days without reinforcement
- Journal scan window: ALL date directories (not just today+yesterday)
- Skip directories: `ocas-praxis`, `.archive`

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

- **Periodic stale script cleanup** — Even with the `scripts/` convention, stale `.py` files accumulate in the data dir root over time. During any ingest run, if `ls *.py | wc -l` exceeds ~10 in the data dir root, run the cleanup pattern from `gotchas-praxis.md` §Stale Script Accumulation before proceeding. This prevents disk bloat and avoids the agent's file cleanup silently removing active scripts.

- **`os.path.isdir(name)` vs `os.path.isdir(path)` gotcha** — When iterating date directories, the loop variable is the directory *name* (e.g., `"2026-06-14"`), not the full path. Calling `os.path.isdir(date_dir)` checks relative to the current working directory, not the skill's journal directory. This returns False for all date dirs, causing the scan to find 0 journals. **Always construct the full path first**: `date_path = os.path.join(skill_path, date_dir)` then check `os.path.isdir(date_path)`. Discovered 2026-06-14: first ingest run found 0 journals because `os.path.isdir("2026-06-14")` was checked relative to CWD (`/root/.hermes/profiles/indigo/commons/data/ocas-praxis/`) instead of the actual journal path.

- **Nested f-string anti-pattern in write_file scripts** — When writing Python scripts via `write_file`, nested f-strings with dict access using escaped quotes (`f"{[f'{s[\"signal_type\"]}:{s[\"skill\"]}' for s in signals]}"`) cause `SyntaxError: unexpected character after line continuation character`. This is a Python f-string limitation (pre-3.12): f-string expressions cannot contain backslash escapes. **Fix:** Break the expression into a separate variable before the f-string:
  ```python
  # WRONG — SyntaxError
  print(f"Signals: {[f'{s[\"signal_type\"]}:{s[\"skill\"]}' for s in signals]}")

  # CORRECT — separate the computation
  sig_labels = [s["signal_type"] + ":" + s["skill"] for s in signals]
  print(f"Signals: {sig_labels}")
  ```
  Alternatively, use string concatenation instead of f-strings for the outer expression: `"Signals: " + str(sig_labels)`. Always run `python3 -c "compile(open('script.py').read(), 'script.py', 'exec')"` after writing to catch syntax errors before execution. Discovered 2026-06-20: ad-hoc ingest script crashed on this pattern.

- **Finch weekly journal dedup** — Finch weekly journals (`job: "finch:weekly"`) contain retrospective corrections and directives that may already be covered by existing active shifts. Before recording events from a finch weekly, check each correction's implied `(signal_type, failure_phase)` against the set of pairs already covered by active shifts. Only record events for uncovered pairs. This prevents double-counting when finch re-summarizes sessions that already produced Praxis events. In the 2026-06-14 ingest, 8 of 10 corrections were already covered; only `directive/planning` and `correction/response` produced new events.

- **Define helper functions before any code that calls them** — Ingest scripts may define utility functions (e.g., `get_lesson_id_from_proposal()`) inside a section that already uses them. If the function is defined after the loop that calls it, the script crashes with `NameError` at runtime. All helper functions must be defined at the top of the script or at least before the first call site. This is the same class of bug as the variable initialization gotchas — Python does not hoist function definitions.

## Python Variable Initialization in Ingest Scripts

- **Initialize `all_shifts` BEFORE the `if new_lessons:` block** — The shift proposal section loads `all_shifts` from disk, but the shift write section and final summary reference `all_shifts` and `active_count` OUTSIDE the `if new_lessons:` conditional. If `new_lessons` is empty, these variables are never defined, causing `UnboundLocalError`. **Fix:** Load `all_shifts` at the very top of the shift proposal section, before any conditional:
  ```python
  # --- SHIFT PROPOSAL ---
  new_shifts = []
  all_shifts = []
  if os.path.exists(SHIFTS_FILE):
      with open(SHIFTS_FILE) as f:
          for line in f:
              line = line.strip()
              if line:
                  try:
                      all_shifts.append(json.loads(line))
                  except json.JSONDecodeError:
                      continue
  # NOW safe to use all_shifts in any downstream conditional or summary
  if new_lessons:
      active_shifts = [s for s in all_shifts if s.get('status') == 'active']
      active_count = len(active_shifts)
      # ... shift proposal logic ...
  # Final summary (outside conditional):
  final_active_count = len([s for s in all_shifts if s.get('status') == 'active'])
  print(f"Active shifts: {final_active_count}/{MAX_ACTIVE_SHIFTS}")
  ```
  This applies to ANY variable used in post-section summary/output — initialize before any conditional that might define it.

- **Initialize `truly_new` before the `if new_events:` block** — Ingest scripts that define `truly_new` only inside a conditional block will raise `NameError` at decision-logging time if the condition is false. Always initialize `truly_new = []` before any conditional that might define it. Same applies to any variable used after a conditional block.
- **Initialize ALL accumulator variables before any loop or conditional** — Any variable referenced after a loop or conditional must be initialized before it. The pattern `if 'varname' in dir()` does NOT work (returns false positives from imported names). Examples:
  - `truly_new = []` before `if new_events:` block (existing gotcha)
  - `remaining_proposals = []` before `for proposal in new_proposals:` loop — without this, an empty `new_proposals` list causes `NameError` on the first reference after the loop because the `for/else` body never executed
  - Any `total`, `count`, `results`, or `output` variable used in post-loop print/log statements
  - Default: declare all accumulators at the top of the section, not inside any branch.
- **Never use `dir()` to check variable existence** — The pattern `if 'varname' in dir()` is fragile and returns false positives (matches function names, imported modules, etc.). Use explicit initialization or `try/except NameError` if truly dynamic.
- **Initialize `summary` before the `for entry in data_list` loop** — The `summary` variable is set inside the loop body (`summary = entry.get("summary", "")`) and referenced after the loop for noise suppression (`if isinstance(summary, str) and signals_found:`). If `data_list` is empty or contains no dict entries, `summary` is never assigned, causing `UnboundLocalError` at the suppression check. Always initialize `summary = ""` before the entry loop. Same class of bug as `truly_new`/`remaining_proposals` — any variable set inside a loop and used after it must be initialized before the loop.

## Python Anti-Patterns in Ingest Scripts (MANDATORY)

### Never use `dir()` to check variable existence — in ANY context

The pattern `if 'varname' in dir()` is fragile and returns false positives (matches function names, imported modules, etc.). This applies both to inline Python code AND to expressions embedded in f-strings or print statements:

```python
# WRONG — dir() returns false positives from imports, function names, etc.
print(f"Shifts: {len(final_shifts) if 'final_shifts' in dir() else len(all_shifts)}")

# WRONG — same problem
if 'final_shifts' in dir():
    do_something(final_shifts)

# CORRECT — use locals() for function-local variables
total = len(final_shifts) if 'final_shifts' in locals() else len(all_shifts)

# CORRECT — even better, initialize before the conditional so the variable always exists
final_shifts = all_shifts  # default assignment before if/else
if some_condition:
    final_shifts = compute_shifts()
# Now final_shifts is always defined, no dir()/locals() check needed
```

**Rule:** Initialize ALL variables before any conditional or loop that might define them. Prefer explicit initialization over runtime existence checks. `dir()` is essentially never the right answer.

### Compaction arithmetic: `len()` on both operands

When computing how many entries were removed during compaction, both operands must be integers:

```python
# WRONG — TypeError: unsupported operand type(s) for -: 'int' and 'list'
removed = len(eval_entries) - compacted

# CORRECT — len() on both sides
removed = len(eval_entries) - len(compacted)
```

This caused a crash in the compaction pre-scan step on 2026-06-14 when `journals_evaluated.jsonl` exceeded 5,000 entries.

### `else` clause indentation must match the `if`

When adding an `else` branch to an `if` block, ensure the `else:` is at the **exact same indentation level** as the `if`. A stray `else:` at the wrong indent level causes `SyntaxError: invalid syntax`:

```python
# WRONG — else at wrong indent
if len(active_shifts) >= 12:
    print("Cap reached")
    final_shifts = all_shifts
else:  # ← SyntaxError if this doesn't align with the 'if' above
    # ... shift proposal logic ...

# CORRECT — else aligns with if
if len(active_shifts) >= 12:
    print("Cap reached")
    final_shifts = all_shifts
else:
    # ... shift proposal logic ...
```

### Forge no-op result variants

Forge scan journals use multiple no-op result strings. The `FORGE_NO_OP_RESULTS` set should include all known variants, AND a substring match fallback is needed for verbose variants:

```python
FORGE_NO_OP_RESULTS = {"no_op", "clean", "no files found"}

# Also need substring matching for verbose variants like:
# "clean — no unprocessed VariantProposal or VariantDecision files found"
if skill == "ocas-forge":
    result = data.get("result", "")
    if isinstance(result, str):
        rl = result.lower().strip()
        if rl in FORGE_NO_OP_RESULTS or "no_files_found" in rl or "clean" in rl or "no unprocessed" in rl:
            return [], summary, status
```

Without the substring fallback, a forge journal with `result: "no_files_found"` passes through signal extraction and produces spurious `failure_keyword` events.
- **Lesson content dedup by `(signal_type, failure_phase)` fails on case/phase variance** — When building the `existing_groups` set from existing lessons, the keys are case-sensitive exact matches. New lessons may use `failure_phase: "Execution"` (capitalized) while existing lessons use `"execution"` (lowercase), or `"null"` vs `None` vs `""`. This causes the dedup to miss real duplicates, producing 21+ false-positive lessons from single-event patterns. In the 2026-06-16 ingest, this produced 21 bad lessons and 6 bad shifts that had to be manually reverted. **Fix:** Normalize both sides before comparison: `key = (signal_type.strip().lower(), str(failure_phase).strip().lower() if failure_phase else "")`. Build the existing-keys set with the same normalization. Also normalize at write time: store `failure_phase` as lowercase in new lessons.

- **`sorted(event_groups.items())` crashes on None signal_type** — When grouping events by `(signal_type, failure_phase)`, some legacy events have `signal_type: None`. Python's `sorted()` cannot compare `None` with `str`, raising `TypeError`. **Fix:** Use a sort key that handles None: `sorted(event_groups.items(), key=lambda x: (x[0][0] or "", x[0][1] or ""))`. Better: ensure `get_signal_type()` never returns `None` — it should always fall back to `"unknown"`.

- **Shift append logic: write ONLY new shifts, not all** — After proposing new shifts, the ingest script must append only the newly created shifts to `shifts.jsonl`, NOT iterate over the combined `existing_shifts` list (which includes all pre-existing shifts already on disk). In the 2026-06-16 ingest v6, the shift write loop iterated over `existing_shifts` and wrote all 57 entries, duplicating every pre-existing shift. **Fix:** Track new shifts in a separate `new_shifts = []` list during proposal. After the proposal loop, write only `new_shifts`: `for s in new_shifts: f.write(json.dumps(s) + "\n")`.

- **Mixed event schemas in `events.jsonl`** — Legacy events may use `id` instead of `event_id`, and some may lack `source_journal`. When iterating events for lesson extraction, always use:
  - `e.get("event_id", e.get("id", "?"))` for event IDs
  - `e.get("source_journal", "")` with a guard before `.split("/")`
  - Filter to events that have `signal_type` in the meaningful set; legacy events without `signal_type` are noise
- **Lesson extraction runs against ALL events, not just new ones** — Each ingest cycle re-reads the full `events.jsonl` and re-extracts lessons for all groups with 2+ events. Dedup by checking `lesson_id` against existing `lessons.jsonl` — only write lessons whose `lesson_id` doesn't already exist. This means "new" lessons can appear even when no new journals were scanned, because the event backlog hadn't been fully consolidated yet.
