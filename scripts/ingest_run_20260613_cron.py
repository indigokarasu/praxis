#!/usr/bin/env python3
"""
Praxis Journal Ingest Run — 2026-06-13 cron
Scans skill journals, extracts behavioral signals, records events,
extracts lessons (two-pass), proposes/activates shifts.
"""

import json
import os
from datetime import datetime, timedelta, timezone

# === PATHS (absolute literals — os.path.join strips leading dot) ===
DATA_DIR = "/root/.hermes/profiles/indigo/commons/data/ocas-praxis"
JOURNALS_DIR = "/root/.hermes/commons/journals"
JOURNAL_DIR = os.path.join(DATA_DIR, "journals")
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")
EVIDENCE_FILE = os.path.join(DATA_DIR, "evidence.jsonl")

SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
FORGE_NO_OP_RESULTS = {"no_op", "clean"}

SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy"
]

MEANINGFUL_SIGNAL_TYPES = {
    "auth_failure", "escalation", "execution_error", "correction",
    "cron_errors", "failure_keyword", "model_fallback", "timeout",
    "scope_failure", "completed_with_errors"
}

# === HELPER FUNCTIONS (defined before any call site) ===

def get_event_id(evt):
    return evt.get("event_id", evt.get("id", ""))

def get_event_domain(evt):
    return evt.get("domain", evt.get("source", "unknown"))

def get_lesson_id(les):
    return les.get("lesson_id", les.get("id", ""))

def get_shift_id(s):
    return s.get("shift_id", s.get("id", "?"))

def get_failure_phase(s):
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
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records

def write_jsonl(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

def append_jsonl(path, records):
    with open(path, "a") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

def should_suppress_summary_signals(summary_str, signals):
    SUMMARY_DERIVED_TYPES = {"failure_keyword", "auth_failure"}
    non_summary_signals = [s for s in signals if s["type"] not in SUMMARY_DERIVED_TYPES]
    if non_summary_signals:
        return False
    summary_lower = summary_str.lower()
    for phrase in SUPPRESS_PHRASES:
        if phrase in summary_lower:
            return True
    return False

def get_skill_from_journal_id(journal_id):
    parts = journal_id.split("/")
    return parts[0] if parts else "unknown"

# === SIGNAL EXTRACTION ===

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
        # Don't keyword-scan finch dict summaries (false positive risk)
        if skill != "ocas-finch":
            summary = json.dumps(raw_summary)
        else:
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
                signals.append({"type": "execution_error", "phase": "execution", "evidence": {"exec_status": exec_status}})
        
        # Check decision.summary for keywords
        dec_summary = decision.get("summary", "")
        if isinstance(dec_summary, str) and dec_summary.strip():
            dec_lower = dec_summary.lower()
            if any(kw in dec_lower for kw in ["failed", "failure", "error", "timeout", "exception"]):
                signals.append({"type": "failure_keyword", "phase": "execution", "evidence": {"summary": dec_summary[:200]}})
            if any(kw in dec_lower for kw in ["oauth", "token", "401", "auth"]):
                signals.append({"type": "auth_failure", "phase": "execution", "evidence": {"summary": dec_summary[:200]}})
    
    # Check actions_taken
    actions = data.get("actions_taken", [])
    if isinstance(actions, list):
        for action in actions:
            if isinstance(action, dict):
                outcome = action.get("outcome", "")
                if isinstance(outcome, str) and outcome.lower() in ("error", "failure", "failed"):
                    signals.append({"type": "execution_error", "phase": "execution", "evidence": {"action": action.get("action", "")}})
    
    # Check fixes_applied
    checks = data.get("checks", {})
    if isinstance(checks, dict) and checks.get("fixes_applied", 0) > 0:
        signals.append({"type": "correction", "phase": "execution", "evidence": {"fixes_applied": checks["fixes_applied"]}})
    
    # Check new_findings
    findings = data.get("new_findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict):
                sev = finding.get("severity", "")
                if sev in ("error", "critical", "high"):
                    signals.append({"type": "escalation", "phase": "execution", "evidence": {"finding": finding.get("title", "")}})
    
    # Check nested findings array
    nested_findings = data.get("findings", [])
    if isinstance(nested_findings, list):
        for finding in nested_findings:
            if isinstance(finding, dict):
                f_status = finding.get("status", "")
                if f_status in ("error", "failed"):
                    signals.append({"type": "execution_error", "phase": "execution", "evidence": {"finding_status": f_status}})
                f_escalation = finding.get("escalation_needed", False)
                if f_escalation:
                    signals.append({"type": "escalation", "phase": "execution", "evidence": {"finding_escalation": True}})
    
    # Check findings dict (finch-style)
    findings_dict = data.get("findings", {})
    if isinstance(findings_dict, dict):
        for src_name, src_data in findings_dict.items():
            if isinstance(src_data, dict):
                src_status = src_data.get("status", "")
                if src_status in ("ERROR", "error", "FAILED", "failed"):
                    signals.append({"type": "execution_error", "phase": "execution", "evidence": {"source": src_name, "status": src_status}})
    
    # Finch-specific: signals.* structure
    finch_signals = data.get("signals", {})
    if isinstance(finch_signals, dict):
        cron_data = finch_signals.get("cron", {})
        if isinstance(cron_data, dict):
            new_errors = cron_data.get("new_errors", [])
            if isinstance(new_errors, list) and new_errors:
                signals.append({"type": "cron_errors", "phase": "execution", "evidence": {"count": len(new_errors)}})
            
            error_breakdown = cron_data.get("error_breakdown", {})
            if isinstance(error_breakdown, dict):
                for err_type, count in error_breakdown.items():
                    if isinstance(count, (int, float)) and count > 0:
                        signals.append({"type": "cron_errors", "phase": "execution", "evidence": {"error_type": err_type, "count": count}})
        
        # Check tasks_added for error keywords
        tasks_added = finch_signals.get("tasks_added", [])
        if isinstance(tasks_added, list):
            for task in tasks_added:
                if isinstance(task, str) and any(kw in task.lower() for kw in ["error", "failed", "failure"]):
                    signals.append({"type": "failure_keyword", "phase": "execution", "evidence": {"task": task[:200]}})
    
    # Check top-level summary string for keywords (only if no other signals found)
    if isinstance(summary, str) and summary.strip() and not signals:
        summary_lower = summary.lower()
        if any(kw in summary_lower for kw in ["failed", "failure", "error", "timeout", "exception"]):
            signals.append({"type": "failure_keyword", "phase": "execution", "evidence": {"summary": summary[:200]}})
        if any(kw in summary_lower for kw in ["oauth", "token", "401", "auth"]):
            signals.append({"type": "auth_failure", "phase": "execution", "evidence": {"summary": summary[:200]}})
    
    # Check for completed_with_errors status
    if status == "completed_with_errors":
        signals.append({"type": "completed_with_errors", "phase": "execution", "evidence": {"status": status}})
    
    # Forge no-op filter
    if skill == "ocas-forge":
        result = data.get("result", "")
        if isinstance(result, str) and result.lower().strip() in FORGE_NO_OP_RESULTS:
            return [], summary, status
    
    # Spot observation filter
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
    
    return signals, summary, status


# === MAIN ===

now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
run_id = f"r_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"

print(f"=== Praxis Journal Ingest Run ===")
print(f"Run ID: {run_id}")
print(f"Time: {now.isoformat()}")
print(f"Scan window: {yesterday} – {today}")
print()

# --- Step 1: Deduplicate journals_evaluated.jsonl ---
eval_entries = read_jsonl(EVAL_FILE)
original_eval_count = len(eval_entries)
seen_ids = set()
deduped_eval = []
for entry in eval_entries:
    jid = entry.get("journal_id", "")
    if jid not in seen_ids:
        seen_ids.add(jid)
        deduped_eval.append(entry)
eval_entries = deduped_eval

if len(eval_entries) < original_eval_count:
    print(f"  Deduped journals_evaluated.jsonl: {original_eval_count} → {len(eval_entries)} entries")

# --- Step 1b: Compact if >5,000 entries ---
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
print(f"  journals_evaluated.jsonl: {len(eval_entries)} entries after dedup/compaction")

# --- Step 2: Scan filesystem for journal files ---
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

print(f"  Total journal files found: {len(all_files)}")

# --- Step 3: Compute unevaluated set ---
seen_eval_ids = {e.get("journal_id", "") for e in eval_entries}
unevaluated = [(c, p) for c, p in all_files if c not in seen_eval_ids and os.path.exists(p)]
print(f"  Unevaluated journals: {len(unevaluated)}")
print()

# --- Step 4: Process each unevaluated journal ---
new_events = []
eval_updates = []
journals_processed = 0
journals_with_signals = 0
journals_no_signal = 0
journals_error = 0

for canonical, fpath in unevaluated:
    skill = get_skill_from_journal_id(canonical)
    signals = []
    summary = ""
    status = ""
    
    try:
        with open(fpath, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "error",
            "signals_found": [],
            "reason": f"Failed to read: {str(e)[:100]}"
        })
        journals_error += 1
        continue

    # Handle list-format journals
    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                entry_signals, entry_summary, entry_status = extract_signals_from_dict(entry, skill)
                signals.extend(entry_signals)
                if entry_summary:
                    summary = entry_summary
                if entry_status:
                    status = entry_status
        # Dedup signals by type for this journal
        seen_signal_types = set()
        deduped_signals = []
        for s in signals:
            key = (canonical, s["type"])
            if key not in seen_signal_types:
                seen_signal_types.add(key)
                deduped_signals.append(s)
        signals = deduped_signals
        
        if not signals:
            eval_updates.append({
                "journal_id": canonical,
                "evaluated_at": now.isoformat(),
                "action_taken": "no_signal",
                "signals_found": [],
                "reason": "No behavioral signals after noise filtering (list format)"
            })
            journals_no_signal += 1
            continue
    else:
        # Dict-format journal
        signals, summary, status = extract_signals_from_dict(data, skill)
        
        # Apply summary string noise filter
        if isinstance(summary, str) and signals:
            if should_suppress_summary_signals(summary, signals):
                signals = [s for s in signals if s["type"] not in ("failure_keyword", "auth_failure")]
        
        if not signals:
            eval_updates.append({
                "journal_id": canonical,
                "evaluated_at": now.isoformat(),
                "action_taken": "no_signal",
                "signals_found": [],
                "reason": "No behavioral signals after noise filtering"
            })
            journals_no_signal += 1
            continue

    # Dedup signals by (source_journal, signal_type)
    seen_signal_types = set()
    deduped_signals = []
    for s in signals:
        key = (canonical, s["type"])
        if key not in seen_signal_types:
            seen_signal_types.add(key)
            deduped_signals.append(s)
    signals = deduped_signals

    # Record events for each signal
    for sig in signals:
        sig_type = sig["type"]
        if sig_type not in MEANINGFUL_SIGNAL_TYPES:
            continue
        
        # Determine failure phase
        failure_phase = "execution"  # default
        if sig.get("phase"):
            failure_phase = sig["phase"]
        
        event = {
            "event_id": f"evt_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}",
            "recorded_at": now.isoformat(),
            "source_journal": canonical,
            "skill": skill,
            "domain": skill,
            "signal_type": sig_type,
            "failure_phase": failure_phase,
            "summary": str(summary)[:500] if summary else "",
            "evidence": sig.get("evidence", {}),
            "outcome_type": "failure" if sig_type in ("execution_error", "auth_failure", "cron_errors", "timeout") else "partial"
        }
        new_events.append(event)

    eval_updates.append({
        "journal_id": canonical,
        "evaluated_at": now.isoformat(),
        "action_taken": "event_recorded",
        "signals_found": [s["type"] for s in signals],
        "reason": f"Extracted {len(signals)} signal(s)"
    })
    journals_with_signals += 1

    journals_processed += 1

print(f"  Journals processed: {journals_processed}")
print(f"  Journals with signals: {journals_with_signals}")
print(f"  Journals no signal: {journals_no_signal}")
print(f"  Journals error: {journals_error}")
print(f"  New events to record: {len(new_events)}")
print()

# --- Step 4b: Write new events to events.jsonl ---
if new_events:
    append_jsonl(EVENTS_FILE, new_events)
    print(f"  Wrote {len(new_events)} new events to events.jsonl")

# Post-write dedup of events by (source_journal, signal_type)
all_events = read_jsonl(EVENTS_FILE)
event_dedup_map = {}
for evt in all_events:
    key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
    if key not in event_dedup_map:
        event_dedup_map[key] = evt
    else:
        # Keep earliest recorded_at
        existing = event_dedup_map[key]
        if evt.get("recorded_at", "") < existing.get("recorded_at", ""):
            event_dedup_map[key] = evt

deduped_events = list(event_dedup_map.values())
if len(deduped_events) < len(all_events):
    print(f"  Post-write dedup: {len(all_events)} → {len(deduped_events)} events")
    write_jsonl(EVENTS_FILE, deduped_events)

# --- Write eval_updates ---
if eval_updates:
    append_jsonl(EVAL_FILE, eval_updates)
    print(f"  Wrote {len(eval_updates)} eval updates")

print()

# --- Step 5: Lesson Extraction (Two-Pass) ---
print("=== Lesson Extraction ===")

# Re-read events from disk
all_events = read_jsonl(EVENTS_FILE)
print(f"  Total events on disk: {len(all_events)}")

# Filter to meaningful events
meaningful_events = [e for e in all_events if e.get("signal_type") in MEANINGFUL_SIGNAL_TYPES]
print(f"  Meaningful events: {len(meaningful_events)}")

# Group by (signal_type, failure_phase)
from collections import defaultdict
event_groups = defaultdict(list)
for evt in meaningful_events:
    key = (evt.get("signal_type", ""), evt.get("failure_phase", ""))
    if key[0] and key[1]:
        event_groups[key].append(evt)

print(f"  Event groups: {len(event_groups)}")

# Read existing lessons
existing_lessons = read_jsonl(LESSONS_FILE)
existing_lesson_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_lesson_groups.add(key)

# Pass 1: Extract lesson stubs for groups with 2+ events
new_lessons_pass1 = []
for (sig_type, phase), events in event_groups.items():
    if (sig_type, phase) in existing_lesson_groups:
        continue
    if len(events) < 2:
        continue
    
    lesson_id = f"les_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"
    lesson = {
        "lesson_id": lesson_id,
        "created_at": now.isoformat(),
        "signal_type": sig_type,
        "failure_phase": phase,
        "domain": events[0].get("skill", "unknown"),
        "skills_affected": list(set(e.get("skill", "") for e in events)),
        "event_count": len(events),
        "confidence": "low",
        "lesson_text": f"Pattern: {sig_type} in {phase} phase ({len(events)} events)",
        "causal_grounding": {}
    }
    new_lessons_pass1.append(lesson)

print(f"  Pass 1: {len(new_lessons_pass1)} new lesson stubs")

# Pass 2: Causal grounding upgrade
new_lessons = []
for lesson in new_lessons_pass1:
    events = event_groups.get((lesson["signal_type"], lesson["failure_phase"]), [])
    
    # Build causal grounding
    what = f"Recurring {lesson['signal_type']} in {lesson['failure_phase']} phase observed across {len(events)} events"
    why = f"Multiple instances of {lesson['signal_type']} detected in {lesson['failure_phase']} phase"
    when = f"Applies to {lesson.get('domain', 'unknown')} skill operations in {lesson['failure_phase']} phase"
    
    # Try to extract more specific why from event summaries
    summaries = [e.get("summary", "") for e in events if e.get("summary")]
    if summaries:
        why += f". Evidence: {'; '.join(summaries[:3])}"
    
    lesson["causal_grounding"] = {
        "what": what,
        "why": why,
        "when": when
    }
    lesson["confidence"] = "high"
    new_lessons.append(lesson)

print(f"  Pass 2: {len(new_lessons)} lessons with causal grounding")

if new_lessons:
    append_jsonl(LESSONS_FILE, new_lessons)
    print(f"  Wrote {len(new_lessons)} new lessons to lessons.jsonl")

print()

# --- Step 6: Shift Proposal ---
print("=== Shift Proposal ===")

all_lessons = read_jsonl(LESSONS_FILE)
all_shifts = read_jsonl(SHIFTS_FILE)

# Build set of lesson IDs already covered by active/proposed shifts
covered_lesson_ids = set()
active_shifts = []
proposed_shifts = []
for s in all_shifts:
    sid = get_shift_id(s)
    s_status = s.get("status", "")
    if s_status in ("active", "proposed"):
        for field in ["lesson_id", "lesson_ref", "source_lesson", "source_lesson_ids"]:
            val = s.get(field)
            if val:
                if isinstance(val, list):
                    covered_lesson_ids.update(val)
                elif isinstance(val, str):
                    covered_lesson_ids.add(val)
    if s_status == "active":
        active_shifts.append(s)
    elif s_status == "proposed":
        proposed_shifts.append(s)

print(f"  Active shifts: {len(active_shifts)}")
print(f"  Proposed shifts: {len(proposed_shifts)}")
print(f"  Covered lesson IDs: {len(covered_lesson_ids)}")

# Propose shifts for uncovered high-confidence lessons
new_proposals = []
for lesson in all_lessons:
    lid = get_lesson_id(lesson)
    st = lesson.get("signal_type", "")
    phase = lesson.get("failure_phase", "")
    
    # Guard: skip malformed lessons
    if not st or st in ("unknown", "?", ""):
        continue
    if not phase:
        continue
    
    if lesson.get("confidence") == "high" and lid not in covered_lesson_ids:
        cg = get_lesson_causal_grounding(lesson)
        shift_text = f"Address {st} in {phase} phase: {cg.get('why', 'No causal grounding')}"
        
        shift = {
            "shift_id": f"shf_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}",
            "created_at": now.isoformat(),
            "status": "proposed",
            "signal_type": st,
            "failure_phase": phase,
            "domain": lesson.get("domain", "unknown"),
            "shift_text": shift_text,
            "lesson_id": lid,
            "reinforcement_count": 0,
            "last_reinforced_at": None
        }
        new_proposals.append(shift)

print(f"  New shift proposals: {len(new_proposals)}")

# Check cap and activate
ACTIVE_CAP = 12
remaining_active = ACTIVE_CAP - len(active_shifts)
print(f"  Remaining cap: {remaining_active}")

activated = 0
left_proposed = 0
for proposal in new_proposals:
    if remaining_active > 0:
        proposal["status"] = "active"
        proposal["activated_at"] = now.isoformat()
        active_shifts.append(proposal)
        remaining_active -= 1
        activated += 1
    else:
        left_proposed += 1

print(f"  Activated: {activated}")
print(f"  Left proposed (at cap): {left_proposed}")

# Write all shifts back (rewrite, not append)
all_shifts_to_write = active_shifts + proposed_shifts + new_proposals
write_jsonl(SHIFTS_FILE, all_shifts_to_write)
print(f"  Total shifts on disk: {len(all_shifts_to_write)}")

print()

# --- Step 7: Decision Log ---
decision = {
    "decision_id": f"dec_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}",
    "timestamp": now.isoformat(),
    "decision": "journal_ingest",
    "reasoning": f"Scanned {len(unevaluated)} unevaluated journals. Found {journals_with_signals} with signals, {journals_no_signal} no-signal, {journals_error} errors. Recorded {len(new_events)} events. Extracted {len(new_lessons)} lessons. Proposed {len(new_proposals)} shifts, activated {activated}.",
    "outcome": "completed",
    "entities_observed": [get_skill_from_journal_id(c) for c, _ in unevaluated[:10]],
    "relationships_observed": [],
    "preferences_observed": []
}
append_jsonl(DECISIONS_FILE, [decision])

# --- Step 8: Evidence ---
evidence = {
    "run_id": run_id,
    "timestamp": now.isoformat(),
    "journals_scanned": len(unevaluated),
    "journals_with_signals": journals_with_signals,
    "journals_no_signal": journals_no_signal,
    "journals_error": journals_error,
    "new_events": len(new_events),
    "new_lessons": len(new_lessons),
    "new_shift_proposals": len(new_proposals),
    "shifts_activated": activated,
    "active_shifts_total": len(active_shifts),
    "not_activity_reason": None
}
append_jsonl(EVIDENCE_FILE, [evidence])

# --- Step 9: Praxis Journal ---
journal_entry = {
    "run_id": run_id,
    "timestamp": now.isoformat(),
    "skill": "ocas-praxis",
    "type": "ingest",
    "decision": {
        "summary": f"Ingest complete: {len(unevaluated)} journals scanned, {len(new_events)} events, {len(new_lessons)} lessons, {activated} shifts activated",
        "execution_result": {"status": "ok"},
        "payload": {
            "entities_observed": [],
            "relationships_observed": [],
            "preferences_observed": []
        }
    },
    "actions_taken": [
        {"action": "journal_scan", "outcome": "completed", "count": len(unevaluated)},
        {"action": "event_extraction", "outcome": "completed", "count": len(new_events)},
        {"action": "lesson_extraction", "outcome": "completed", "count": len(new_lessons)},
        {"action": "shift_proposal", "outcome": "completed", "count": len(new_proposals)}
    ],
    "runtime": {
        "model": "owl-alpha",
        "duration_seconds": 0
    }
}

journal_path = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_path, exist_ok=True)
journal_file = os.path.join(journal_path, f"{run_id}.json")
with open(journal_file, "w") as f:
    json.dump(journal_entry, f, indent=2)

print()
print("=== Ingest Complete ===")
print(f"Run ID: {run_id}")
print(f"Journals scanned: {len(unevaluated)}")
print(f"New events: {len(new_events)}")
print(f"New lessons: {len(new_lessons)}")
print(f"Shifts activated: {activated}")
print(f"Active shifts total: {len(active_shifts)}")
