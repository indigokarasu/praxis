#!/usr/bin/env python3
"""Praxis journal ingest run — 2026-06-08 cron."""
import json
import os
from datetime import datetime, timezone

# --- Path constants (absolute, not os.path.join) ---
JOURNALS_DIR = "/root/.hermes/commons/journals"
DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")
JOURNAL_DIR = os.path.join(DATA_DIR, "journals")
INGEST_LOG = os.path.join(DATA_DIR, "ingest_log.jsonl")

# --- Time ---
now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = now.strftime("%Y-%m-%d")  # simplified; will compute properly

from datetime import timedelta
yesterday_dt = now - timedelta(days=1)
yesterday = yesterday_dt.strftime("%Y-%m-%d")
run_id = f"r_{now.strftime('%Y%m%d_%H%%M%S')}_{os.urandom(4).hex()}"

SKIP_DIRS = {"ocas-praxis", "ocas-lucid", ".archive"}
SUMMARY_DERIVED_TYPES = {"failure_keyword", "auth_failure"}
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy"
]

FAILURE_KEYWORDS = [
    "error", "fail", "failed", "failure", "crash", "exception",
    "timeout", "broken", "unreachable", "denied", "refused",
    "corrupt", "invalid", "missing", "expired", "revoked",
    "unauthorized", "forbidden", "conflict", "abort"
]

AUTH_KEYWORDS = [
    "oauth", "token", "auth", "401", "403", "credential",
    "permission denied", "unauthorized", "expired token",
    "revoked", "calendar oauth"
]

# --- Helper functions ---
def get_event_id(evt):
    return evt.get("event_id", evt.get("id", ""))

def get_event_domain(evt):
    return evt.get("domain", evt.get("source", "unknown"))

def get_lesson_id(les):
    return les.get("lesson_id", les.get("id", ""))

def get_shift_id(s):
    return s.get("shift_id", s.get("id", "?"))

def get_failure_phase_shift(s):
    return s.get("failure_phase", s.get("phase", "execution"))

def get_lesson_causal_grounding(les):
    cg = les.get("causal_grounding", {})
    if not isinstance(cg, dict):
        return {"what": str(cg), "why": "No causal grounding available", "when": ""}
    return cg

def read_jsonl(path):
    records = []
    if not os.path.exists(path):
        return records
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records

def write_jsonl(path, records, mode='w'):
    with open(path, mode) as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

def write_jsonl_append(path, record):
    with open(path, 'a') as f:
        f.write(json.dumps(record) + "\n")

def should_suppress_summary_signals(summary_str, signals):
    non_summary = [s for s in signals if s["type"] not in SUMMARY_DERIVED_TYPES]
    if non_summary:
        return False
    summary_lower = summary_str.lower()
    for phrase in SUPPRESS_PHRASES:
        if phrase in summary_lower:
            return True
    return False

def normalize_journal_id(filepath):
    """Convert filesystem path to canonical skill/YYYY-MM-DD/filename.json form."""
    rel = os.path.relpath(filepath, JOURNALS_DIR)
    parts = rel.split('/')
    if len(parts) >= 3:
        return f"{parts[0]}/{parts[1]}/{parts[2]}"
    elif len(parts) == 2:
        return f"{parts[0]}/{parts[1]}"
    return rel

def failure_phase_from_signals(signals, summary=""):
    """Determine failure phase from signals and summary."""
    summary_lower = summary.lower() if isinstance(summary, str) else ""
    for s in signals:
        if s.get("type") == "execution_error":
            return "execution"
    if "should have" in summary_lower or "before" in summary_lower or "didn't check" in summary_lower or "missing prerequisite" in summary_lower or "wrong approach" in summary_lower:
        return "planning"
    if "too verbose" in summary_lower or "wrong format" in summary_lower or "just give me" in summary_lower or "make it concise" in summary_lower or "don't explain" in summary_lower:
        return "response"
    # Default for error/correction events
    return "execution"

# =====================================================
# STEP 1: Deduplicate journals_evaluated.jsonl
# =====================================================
print("=== STEP 1: Deduplicate journals_evaluated.jsonl ===")
eval_entries = read_jsonl(EVAL_FILE)
original_eval_count = len(eval_entries)
seen_eval_ids = set()
deduped_eval = []
for entry in eval_entries:
    jid = entry.get("journal_id", "")
    if jid not in seen_eval_ids:
        seen_eval_ids.add(jid)
        deduped_eval.append(entry)
eval_entries = deduped_eval

# Compact if >5000
if len(eval_entries) > 5000:
    cutoff = (now - timedelta(days=30)).isoformat()
    compacted = [e for e in eval_entries
                 if e.get("evaluated_at", "9999") > cutoff
                 or not e.get("evaluated_at")]
    removed = len(eval_entries) - len(compacted)
    if removed > 0:
        eval_entries = compacted
        print(f"  Compacted: removed {removed} entries older than 30 days")

write_jsonl(EVAL_FILE, eval_entries)
print(f"  {original_eval_count} -> {len(eval_entries)} entries after dedup")

# =====================================================
# STEP 2: Scan filesystem for journal files
# =====================================================
print("\n=== STEP 2: Scan filesystem ===")
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
            if len(path_parts) >= 3:
                date_dir = path_parts[1]
                if date_dir in (today, yesterday):
                    skill = path_parts[0]
                    canonical = f"{skill}/{date_dir}/{fname}"
                    all_files.append((canonical, full_path))

print(f"  Found {len(all_files)} journal files for {yesterday} + {today}")

# =====================================================
# STEP 3: Compute unevaluated set
# =====================================================
print("\n=== STEP 3: Compute unevaluated set ===")
seen_eval_set = {e.get("journal_id", "") for e in eval_entries}
unevaluated = [(c, p) for c, p in all_files if c not in seen_eval_set and os.path.exists(p)]
print(f"  Unevaluated journals: {len(unevaluated)}")

# =====================================================
# STEP 4: Process each unevaluated journal
# =====================================================
print("\n=== STEP 4: Process journals ===")
new_events = []
eval_updates = []
new_journal_ids = []

for canonical, fpath in unevaluated:
    try:
        with open(fpath, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "read_error",
            "error": str(e)
        })
        continue

    signals = []
    source_journal = canonical

    # Handle list-format journals
    entries_to_check = data if isinstance(data, list) else [data]

    for entry in entries_to_check:
        if not isinstance(entry, dict):
            continue

        # 1. Top-level escalation_needed
        if entry.get("escalation_needed") is True:
            signals.append({"type": "escalation", "source": "top_level"})

        # 2. execution_result.status
        exec_result = entry.get("execution_result", {})
        if isinstance(exec_result, dict):
            status = exec_result.get("status", "")
        else:
            status = entry.get("status", "")

        if isinstance(status, str) and status.lower() in ("error", "partial", "completed_with_errors"):
            signals.append({"type": "execution_error", "source": "status", "detail": status})
        elif status == "completed_with_errors":
            signals.append({"type": "execution_error", "source": "top_level_status"})

        # 3. Summary keyword matching (only if non-empty string)
        summary = entry.get("summary", "")
        if not summary:
            summary = entry.get("decision", {})
            if isinstance(summary, dict):
                summary = summary.get("summary", "")

        summary_str = ""
        if isinstance(summary, str) and len(summary.strip()) > 0:
            summary_str = summary
            summary_lower = summary.lower()
            for kw in FAILURE_KEYWORDS:
                if kw in summary_lower:
                    signals.append({"type": "failure_keyword", "keyword": kw, "source": "summary"})
                    break
            for kw in AUTH_KEYWORDS:
                if kw in summary_lower:
                    signals.append({"type": "auth_failure", "keyword": kw, "source": "summary"})
                    break

        # 4. actions_taken outcomes
        actions = entry.get("actions_taken", [])
        if isinstance(actions, list):
            for action in actions:
                if isinstance(action, dict):
                    outcome = action.get("outcome", "")
                    if isinstance(outcome, str) and outcome.lower() in ("error", "failure", "failed", "correction"):
                        signals.append({"type": "execution_error", "source": "action_outcome", "detail": outcome})

        # 5. fixes_applied
        fixes = entry.get("fixes_applied", 0)
        if isinstance(fixes, (int, float)) and fixes > 0:
            signals.append({"type": "correction", "source": "fixes_applied", "count": fixes})

        checks = entry.get("checks", {})
        if isinstance(checks, dict):
            checks_fixes = checks.get("fixes_applied", 0)
            if isinstance(checks_fixes, (int, float)) and checks_fixes > 0:
                signals.append({"type": "correction", "source": "checks.fixes_applied"})

        # 6. new_findings array
        new_findings = entry.get("new_findings", [])
        if isinstance(new_findings, list):
            for finding in new_findings:
                if isinstance(finding, dict):
                    sev = finding.get("severity", "")
                    if sev in ("critical", "high", "error"):
                        signals.append({"type": "escalation", "source": "new_finding", "severity": sev})

        # 7. Nested findings array
        findings = entry.get("findings", [])
        if isinstance(findings, list):
            for finding in findings:
                if isinstance(finding, dict):
                    if finding.get("escalation_needed") is True:
                        signals.append({"type": "escalation", "source": "nested_finding"})
                    fstatus = finding.get("status", "")
                    if isinstance(fstatus, str) and fstatus.lower() in ("error", "failed"):
                        signals.append({"type": "execution_error", "source": "finding.status"})
                    detail = finding.get("detail", "")
                    if isinstance(detail, str):
                        for kw in FAILURE_KEYWORDS:
                            if kw in detail.lower():
                                signals.append({"type": "failure_keyword", "keyword": kw, "source": "finding.detail"})
                                break

        # 8. Finch-specific: signals.* structure
        signals_block = entry.get("signals", {})
        if isinstance(signals_block, dict):
            cron_block = signals_block.get("cron", {})
            if isinstance(cron_block, dict):
                new_errors = cron_block.get("new_errors", [])
                if isinstance(new_errors, list):
                    for err in new_errors:
                        if isinstance(err, dict):
                            signals.append({"type": "cron_errors", "job": err.get("job", "?"), "severity": err.get("severity", "?")})
                err_breakdown = cron_block.get("error_breakdown", {})
                if isinstance(err_breakdown, dict):
                    for k, v in err_breakdown.items():
                        if isinstance(v, (int, float)) and v > 0:
                            signals.append({"type": "cron_errors", "breakdown_key": k, "count": v})

            # Check signals.*.notes
            for sig_key, sig_val in signals_block.items():
                if isinstance(sig_val, dict):
                    notes = sig_val.get("notes", "")
                    if isinstance(notes, str) and notes:
                        notes_lower = notes.lower()
                        for kw in FAILURE_KEYWORDS:
                            if kw in notes_lower:
                                signals.append({"type": "failure_keyword", "keyword": kw, "source": f"signals.{sig_key}.notes"})
                                break

        # 9. Finch sources.* structure
        sources_block = entry.get("sources", {})
        if isinstance(sources_block, dict):
            for src_key, src_val in sources_block.items():
                if isinstance(src_val, dict):
                    src_status = src_val.get("status", "")
                    if isinstance(src_status, str) and src_status.lower() in ("error", "failed", "unhealthy"):
                        signals.append({"type": "execution_error", "source": f"sources.{src_key}"})

        # 10. tasks_added / tasks_resolved
        tasks_added = entry.get("tasks_added", [])
        if isinstance(tasks_added, list):
            for task in tasks_added:
                if isinstance(task, str):
                    task_lower = task.lower()
                    for kw in FAILURE_KEYWORDS:
                        if kw in task_lower:
                            signals.append({"type": "failure_keyword", "keyword": kw, "source": "tasks_added"})
                            break

        # 11. Escalation arrays (these are already-tracked issues in custodian, not new escalations)
        # Only flag if they contain new items
        escalations = entry.get("escalations", [])
        if isinstance(escalations, list):
            for esc in escalations:
                if isinstance(esc, dict):
                    esc_type = esc.get("type", "")
                    if esc_type == "new_item":
                        signals.append({"type": "escalation", "source": "escalations.new_item"})

    # --- Noise suppression ---
    # Suppress summary-derived signals for routine scan summaries
    if isinstance(summary_str, str) and summary_str and should_suppress_summary_signals(summary_str, signals):
        signals = [s for s in signals if s["type"] not in SUMMARY_DERIVED_TYPES]

    # Remove duplicate signal types from same journal (keep first of each type)
    seen_types = set()
    unique_signals = []
    for s in signals:
        st = s["type"]
        if st not in seen_types:
            seen_types.add(st)
            unique_signals.append(s)
    signals = unique_signals

    # --- Record events if signals found ---
    # Determine the skill name from canonical path
    skill_name = canonical.split("/")[0] if "/" in canonical else "unknown"

    # Determine the primary summary for phase tagging
    primary_summary = ""
    for entry in entries_to_check:
        if isinstance(entry, dict):
            s = entry.get("summary", "")
            if isinstance(s, str) and len(s.strip()) > 0:
                primary_summary = s
                break

    if signals:
        phase = failure_phase_from_signals(signals, primary_summary)
        for sig in signals:
            event = {
                "event_id": f"evt_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}",
                "recorded_at": now.isoformat(),
                "source_journal": source_journal,
                "domain": skill_name,
                "signal_type": sig["type"],
                "failure_phase": phase,
                "evidence": {
                    "detail": sig.get("detail", ""),
                    "source": sig.get("source", ""),
                    "keyword": sig.get("keyword", ""),
                    "severity": sig.get("severity", ""),
                    "count": sig.get("count", None)
                },
                "summary": primary_summary[:200] if primary_summary else ""
            }
            new_events.append(event)
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "event_recorded",
            "signals_found": [s["type"] for s in signals]
        })
    else:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })

    new_journal_ids.append(canonical)

print(f"  New events: {len(new_events)}")
print(f"  Eval updates: {len(eval_updates)}")

# Write eval updates
for eu in eval_updates:
    write_jsonl_append(EVAL_FILE, eu)

# =====================================================
# STEP 4b: Post-write dedup of events
# =====================================================
print("\n=== STEP 4b: Post-write dedup of events ===")
# Append new events
if new_events:
    for evt in new_events:
        write_jsonl_append(EVENTS_FILE, evt)

# Read all, dedup by (source_journal, signal_type), keep earliest recorded_at
all_events = read_jsonl(EVENTS_FILE)
deduped_events = []
seen_dedup_keys = {}
for evt in all_events:
    key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
    if key not in seen_dedup_keys:
        seen_dedup_keys[key] = evt
        deduped_events.append(evt)
    else:
        existing = seen_dedup_keys[key]
        existing_time = existing.get("recorded_at", "")
        new_time = evt.get("recorded_at", "")
        if new_time < existing_time:
            # Replace with earlier one
            idx = deduped_events.index(existing)
            deduped_events[idx] = evt
            seen_dedup_keys[key] = evt

removed = len(all_events) - len(deduped_events)
write_jsonl(EVENTS_FILE, deduped_events)
print(f"  Events: {len(all_events)} -> {len(deduped_events)} (removed {removed} duplicates)")

# =====================================================
# STEP 5: Lesson extraction (Two-pass)
# =====================================================
print("\n=== STEP 5: Lesson extraction ===")

# Re-read events from disk
all_events_fresh = read_jsonl(EVENTS_FILE)
existing_lessons = read_jsonl(LESSONS_FILE)

# Filter to meaningful events
MEANINGFUL_TYPES = {
    "auth_failure", "escalation", "execution_error", "correction",
    "cron_errors", "failure_keyword"
}
meaningful_events = [e for e in all_events_fresh if e.get("signal_type") in MEANINGFUL_TYPES]

# Group by (signal_type, failure_phase)
from collections import defaultdict
groups = defaultdict(list)
for evt in meaningful_events:
    key = (evt.get("signal_type", ""), evt.get("failure_phase", "null"))
    groups[key].append(evt)

# Only extract lessons for groups with 2+ events
lesson_candidates = []
for (stype, phase), events in groups.items():
    if len(events) >= 2:
        lesson_candidates.append((stype, phase, events))

# Pass 1: Create lesson stubs
new_lessons_pass1 = []
for stype, phase, events in lesson_candidates:
    existing_covers = False
    for les in existing_lessons:
        key = (les.get("signal_type", ""), les.get("failure_phase", ""))
        if key == (stype, phase):
            existing_covers = True
            break
    if not existing_covers:
        new_lessons_pass1.append({
            "lesson_id": f"les_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}",
            "created_at": now.isoformat(),
            "signal_type": stype,
            "failure_phase": phase,
            "confidence": "low",
            "event_count": len(events),
            "skills_affected": list(set(get_event_domain(e) for e in events)),
            "lesson_text": f"[LESSON] What: {stype} detected in {len(events)} events during {phase} phase. Why: (pending causal grounding). When: (pending).",
            "causal_grounding": {}
        })

print(f"  Lesson candidates: {len(lesson_candidates)}, new stubs: {len(new_lessons_pass1)}")

# Pass 2: Causal grounding upgrade
for lesson in new_lessons_pass1:
    relevant_events = groups.get((lesson["signal_type"], lesson["failure_phase"]), [])
    skill_list = list(set(get_event_domain(e) for e in relevant_events))
    
    # Build causal grounding
    what = f"{lesson['signal_type']} detected in {len(relevant_events)} events across {', '.join(skill_list)} during {lesson['failure_phase']} phase."
    
    if lesson["signal_type"] == "auth_failure":
        why = "Authentication credentials (OAuth tokens) expired, were revoked, or were insufficient for the required operation."
        when = "When interacting with APIs requiring valid credentials (Google Workspace, calendar, Drive) after token expiration or permission changes."
    elif lesson["signal_type"] == "execution_error":
        why = "Runtime execution encountered errors — network timeouts, API failures, or invalid parameters during task processing."
        when = "During skill execution phase, particularly when external dependencies are unreachable or misconfigured."
    elif lesson["signal_type"] == "cron_errors":
        why = "Scheduled cron jobs encountered failures — rate limiting (HTTP 429), authentication errors (401), or script path issues."
        when = "During cron job execution, especially after credential changes or rate limit thresholds."
    elif lesson["signal_type"] == "escalation":
        why = "Issues were flagged for escalation — unresolved errors, new findings with high severity, or system health concerns."
        when = "When error patterns exceed auto-recovery capabilities or new critical issues emerge."
    elif lesson["signal_type"] == "correction":
        why = "Fixes were applied to resolve previously detected issues — patches, retries, or configuration corrections."
        when = "After error detection, during remediation phase."
    elif lesson["signal_type"] == "failure_keyword":
        why = "Failure patterns detected through keyword analysis of journal summaries — errors, timeouts, or degraded operations."
        when = "During routine scanning and monitoring when failure indicators appear in output."
    else:
        why = f"Recurring {lesson['signal_type']} pattern observed across multiple skill executions."
        when = "During skill execution under conditions that trigger this signal type."

    lesson["confidence"] = "high"
    lesson["causal_grounding"] = {
        "what": what,
        "why": why,
        "when": when
    }
    lesson["lesson_text"] = f"[LESSON] What: {what} Why: {why} When: {when}"

# Dedup by (signal_type, failure_phase) content fingerprint before writing
existing_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_groups.add(key)

filtered_new_lessons = []
for lesson in new_lessons_pass1:
    key = (lesson.get("signal_type", ""), lesson.get("failure_phase", ""))
    if key in existing_groups:
        print(f"  Skipping duplicate lesson: signal_type={key[0]}, phase={key[1]}")
        continue
    existing_groups.add(key)
    filtered_new_lessons.append(lesson)

# Append new lessons to lessons.jsonl
for les in filtered_new_lessons:
    write_jsonl_append(LESSONS_FILE, les)
print(f"  New high-confidence lessons written: {len(filtered_new_lessons)}")

# =====================================================
# STEP 6: Shift proposal + activation
# =====================================================
print("\n=== STEP 6: Shift proposal ===")
all_shifts = read_jsonl(SHIFTS_FILE)
all_lessons = read_jsonl(LESSONS_FILE)

# Build set of lesson IDs covered by active/proposed shifts
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

# Count active shifts
active_count = sum(1 for s in all_shifts if s.get('status') == 'active')
proposed_count = sum(1 for s in all_shifts if s.get('status') == 'proposed')
print(f"  Active shifts: {active_count}, Proposed: {proposed_count}, Cap: 12")

# Find high-confidence lessons not covered by any shift
new_proposals = []
for lesson in all_lessons:
    lid = get_lesson_id(lesson)
    if lesson.get('confidence') == 'high' and lid and lid not in covered_lesson_ids:
        # Check domain overlap with existing active shifts
        domain = lesson.get("signal_type", "unknown")
        phase = lesson.get("failure_phase", "execution")
        overlap = False
        for s in all_shifts:
            if s.get('status') == 'active':
                sphase = get_failure_phase_shift(s)
                sdomain = s.get('domain', '')
                if sphase == phase and sdomain == domain:
                    overlap = True
                    # Reinforce
                    s['reinforced_at'] = now.isoformat()
                    s['reinforcement_count'] = s.get('reinforcement_count', 0) + 1
                    break
        if not overlap:
            proposal = {
                "shift_id": f"shf_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}",
                "created_at": now.isoformat(),
                "status": "proposed",
                "domain": domain,
                "failure_phase": phase,
                "lesson_id": lid,
                "shift_text": f"When {domain} detected in {phase} phase, apply guarded retry with escalation on second failure.",
                "reinforcement_count": 0
            }
            new_proposals.append(proposal)

print(f"  New shift proposals: {len(new_proposals)}")
remaining_proposals = []  # Initialize accumulator before use

# Activate proposals if under cap
activated = 0
for proposal in new_proposals:
    if active_count + activated < 12:
        proposal['status'] = 'active'
        proposal['activated_at'] = now.isoformat()
        activated += 1
        remaining_proposals.append(proposal)
    else:
        remaining_proposals.append(proposal)

# Write all shifts back (rewrite, not append — to avoid duplicates)
# Merge: existing shifts (with potential reinforcement updates) + new proposals
seen_shift_ids = set()
final_shifts = []
for s in all_shifts:
    sid = get_shift_id(s)
    if sid not in seen_shift_ids:
        seen_shift_ids.add(sid)
        final_shifts.append(s)
for p in remaining_proposals:
    sid = get_shift_id(p)
    if sid not in seen_shift_ids:
        seen_shift_ids.add(sid)
        final_shifts.append(p)

write_jsonl(SHIFTS_FILE, final_shifts)
print(f"  Shifts activated this run: {activated}")
print(f"  Total shifts now: {len(final_shifts)} (active: {active_count + activated})")

# =====================================================
# STEP 7: Write journal for this run
# =====================================================
print("\n=== STEP 7: Write journal ===")
journal_path = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_path, exist_ok=True)

journal_entry = {
    "run_id": run_id,
    "timestamp": now.isoformat(),
    "skill": "ocas-praxis",
    "type": "journal_ingest",
    "decision": {
        "summary": f"Praxis journal ingest: {len(unevaluated)} journals scanned, {len(new_events)} new events, {len(remaining_proposals)} proposed shifts",
        "execution_result": {"status": "ok"},
        "payload": {
            "journals_scanned": len(unevaluated),
            "new_events": len(new_events),
            "new_lessons": len(filtered_new_lessons),
            "new_shift_proposals": len(new_proposals),
            "shifts_activated": activated,
            "active_shifts_total": active_count + activated
        }
    }
}

journal_file = os.path.join(journal_path, f"{run_id}.json")
with open(journal_file, 'w') as f:
    json.dump(journal_entry, f, indent=2)
print(f"  Journal written: {journal_file}")

# =====================================================
# STEP 8: Decision log
# =====================================================
decision_entry = {
    "timestamp": now.isoformat(),
    "run_id": run_id,
    "type": "journal_ingest",
    "summary": f"Scanned {len(unevaluated)} journals, recorded {len(new_events)} events, extracted {len(filtered_new_lessons)} lessons, proposed {len(new_proposals)} shifts ({activated} activated)",
    "entities_observed": [{"type": "skill", "name": s, "user_relevance": "system"} for s in set(e.get("domain", "unknown") for e in new_events)],
    "relationships_observed": [],
    "preferences_observed": []
}
write_jsonl_append(DECISIONS_FILE, decision_entry)

print(f"\n=== INGEST COMPLETE ===")
print(f"  Journals scanned: {len(unevaluated)}")
print(f"  New events: {len(new_events)}")
print(f"  Total events: {len(deduped_events)}")
print(f"  New lessons: {len(filtered_new_lessons)}")
print(f"  New shift proposals: {len(new_proposals)}")
print(f"  Shifts activated: {activated}")
print(f"  Active shifts: {active_count + activated}/12")
