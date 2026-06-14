#!/usr/bin/env python3
"""
Praxis Journal Ingest Run — 2026-06-15
Scans all skill journals for new entries, extracts behavioral signals,
records events, extracts lessons, proposes/activates shifts.
"""

import json
import os
from datetime import datetime, timedelta, timezone

# === PATHS (absolute literals — os.path.join strips leading dot) ===
DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
JOURNALS_DIR = "/root/.hermes/commons/journals"
JOURNAL_DIR = "/root/.hermes/commons/journals/ocas-praxis"
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")

SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy"
]

# === HELPER FUNCTIONS (defined before any code that uses them) ===

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

def append_jsonl(path, records):
    write_jsonl(path, records, mode='a')

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def should_suppress_summary_signals(summary_str, signals):
    """Return True if summary-derived signals should be suppressed."""
    SUMMARY_DERIVED_TYPES = {"failure_keyword", "auth_failure"}
    non_summary_signals = [s for s in signals if s["type"] not in SUMMARY_DERIVED_TYPES]
    if non_summary_signals:
        return False
    summary_lower = summary_str.lower()
    for phrase in SUPPRESS_PHRASES:
        if phrase in summary_lower:
            return True
    return False

def extract_signals_from_journal(journal_data, canonical):
    """Extract behavioral signals from a journal entry. Returns list of signal dicts."""
    signals = []
    summary = ""
    
    # Handle list-format journals
    if isinstance(journal_data, list):
        for entry in journal_data:
            if isinstance(entry, dict):
                s = extract_signals_from_journal(entry, canonical)
                signals.extend(s)
        return signals
    
    if not isinstance(journal_data, dict):
        return signals
    
    # 1. Top-level escalation_needed
    if journal_data.get("escalation_needed") is True:
        signals.append({"type": "escalation", "detail": "top-level escalation_needed=true"})
    
    # 2. decision.execution_result.status
    decision = journal_data.get("decision", {})
    if isinstance(decision, dict):
        exec_result = decision.get("execution_result", {})
        if isinstance(exec_result, dict):
            status = exec_result.get("status", "")
            if status in ("error", "partial", "completed_with_errors"):
                signals.append({"type": "execution_error", "detail": f"status={status}"})
    else:
        # Check top-level status
        status = journal_data.get("status", "")
        if status in ("error", "partial", "completed_with_errors"):
            signals.append({"type": "execution_error", "detail": f"status={status}"})
    
    # 3. Summary field (top-level or decision.summary)
    dec_summary = ""
    if isinstance(decision, dict):
        dec_summary = decision.get("summary", "")
    
    top_summary = journal_data.get("summary", "")
    
    # Use whichever summary is a non-empty string
    if isinstance(dec_summary, str) and dec_summary.strip():
        summary = dec_summary
    elif isinstance(top_summary, str) and top_summary.strip():
        summary = top_summary
    elif isinstance(top_summary, dict):
        summary = json.dumps(top_summary)
    elif isinstance(dec_summary, dict):
        summary = json.dumps(dec_summary)
    
    # 4. actions_taken[].outcome
    actions_taken = journal_data.get("actions_taken", [])
    if isinstance(actions_taken, list):
        for action in actions_taken:
            if isinstance(action, dict):
                outcome = action.get("outcome", "")
                if outcome in ("error", "failure", "failed"):
                    signals.append({"type": "execution_error", "detail": f"action_outcome={outcome}"})
                elif outcome in ("corrected", "fix_applied", "fixed"):
                    signals.append({"type": "correction", "detail": f"action_outcome={outcome}"})
    
    # 5. fixes_applied
    fixes = journal_data.get("fixes_applied", 0)
    if isinstance(fixes, int) and fixes > 0:
        signals.append({"type": "correction", "detail": f"fixes_applied={fixes}"})
    
    checks = journal_data.get("checks", {})
    if isinstance(checks, dict):
        checks_fixes = checks.get("fixes_applied", 0)
        if isinstance(checks_fixes, int) and checks_fixes > 0:
            signals.append({"type": "correction", "detail": f"checks.fixes_applied={checks_fixes}"})
    
    # 6. new_findings[]
    new_findings = journal_data.get("new_findings", [])
    if isinstance(new_findings, list):
        for finding in new_findings:
            if isinstance(finding, dict):
                sev = finding.get("severity", "")
                if sev in ("error", "critical", "high"):
                    signals.append({"type": "execution_error", "detail": f"finding: {finding.get('title', '')}"})
    
    # 7. findings[] (nested — custodian escalation-runner)
    findings = journal_data.get("findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict):
                if finding.get("escalation_needed") is True:
                    signals.append({"type": "escalation", "detail": f"finding escalation: {finding.get('title', finding.get('id', ''))}"})
                f_status = finding.get("status", "")
                if f_status in ("error", "failed"):
                    signals.append({"type": "execution_error", "detail": f"finding status={f_status}: {finding.get('title', finding.get('id', ''))}"})
                action_taken = finding.get("action_taken", "")
                if isinstance(action_taken, str) and any(kw in action_taken.lower() for kw in ["fix", "correct", "update", "applied"]):
                    signals.append({"type": "correction", "detail": f"finding action: {action_taken}"})
    
    # 8. Finch signals.* and sources.*
    finch_signals = journal_data.get("signals", {})
    if isinstance(finch_signals, dict):
        cron_signals = finch_signals.get("cron", {})
        if isinstance(cron_signals, dict):
            new_errors = cron_signals.get("new_errors", [])
            if isinstance(new_errors, list):
                for err in new_errors:
                    if isinstance(err, dict):
                        signals.append({"type": "cron_errors", "detail": f"new_cron_error: {err.get('job', err.get('name', ''))} — {err.get('error', err.get('message', ''))}"})
                    elif isinstance(err, str):
                        signals.append({"type": "cron_errors", "detail": f"new_cron_error: {err}"})
            
            error_breakdown = cron_signals.get("error_breakdown", {})
            if isinstance(error_breakdown, dict):
                for key, val in error_breakdown.items():
                    if isinstance(val, int) and val > 0:
                        signals.append({"type": "cron_errors", "detail": f"error_breakdown.{key}={val}"})
        
        # Check signals.*.notes
        for sig_key, sig_val in finch_signals.items():
            if isinstance(sig_val, dict):
                notes = sig_val.get("notes", "")
                if isinstance(notes, str) and notes.strip():
                    notes_lower = notes.lower()
                    for kw in ["error", "fail", "escalat", "correction", "fix"]:
                        if kw in notes_lower:
                            signals.append({"type": "failure_keyword", "detail": f"signals.{sig_key}.notes: {notes}"})
                            break
    
    # 9. Finch tasks_added[]
    tasks_added = journal_data.get("tasks_added", [])
    if isinstance(tasks_added, list):
        for task in tasks_added:
            if isinstance(task, str):
                task_lower = task.lower()
                if any(kw in task_lower for kw in ["error", "fail"]):
                    signals.append({"type": "failure_keyword", "detail": f"task_added: {task}"})
    
    # 10. Keyword scanning on summary (only if non-empty string)
    if isinstance(summary, str) and summary.strip():
        summary_lower = summary.lower()
        # Check for failure keywords
        failure_keywords = ["error", "failed", "failure", "timeout", "truncat", "crash", "exception"]
        for kw in failure_keywords:
            if kw in summary_lower:
                signals.append({"type": "failure_keyword", "detail": f"summary contains '{kw}'"})
                break
        # Check for auth keywords
        auth_keywords = ["oauth", "token", "401", "unauthorized", "auth"]
        for kw in auth_keywords:
            if kw in summary_lower:
                signals.append({"type": "auth_failure", "detail": f"summary contains '{kw}'"})
                break
    
    # Apply semantic suppression for summary-derived signals
    if isinstance(summary, str) and summary.strip():
        if should_suppress_summary_signals(summary, signals):
            # Remove all summary-derived signals
            signals = [s for s in signals if s["type"] not in ("failure_keyword", "auth_failure")]
    
    return signals

def determine_failure_phase(signal_type, detail):
    """Determine failure phase from signal type and detail."""
    detail_lower = detail.lower() if isinstance(detail, str) else ""
    
    # Planning indicators
    if any(kw in detail_lower for kw in ["should have", "before", "wrong approach", "didn't check", "missing prerequisite", "planning"]):
        return "planning"
    
    # Response indicators
    if any(kw in detail_lower for kw in ["too verbose", "wrong format", "just give me", "make it concise", "don't explain", "response"]):
        return "response"
    
    # Execution indicators (default for most errors)
    if signal_type in ("execution_error", "cron_errors", "escalation"):
        return "execution"
    
    if signal_type == "correction":
        return "execution"
    
    return "execution"  # default

def generate_event_id(canonical, signal_type, timestamp):
    """Generate a unique event ID."""
    import hashlib
    base = f"{canonical}_{signal_type}_{timestamp}"
    h = hashlib.md5(base.encode()).hexdigest()[:8]
    return f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{h}"

# === MAIN INGEST PIPELINE ===

print("=" * 60)
print("PRAXIS JOURNAL INGEST — 2026-06-15")
print("=" * 60)

now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
run_id = f"r_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"

print(f"\nRun ID: {run_id}")
print(f"Scan window: {yesterday} to {today}")

# === STEP 1: Deduplicate journals_evaluated.jsonl ===
print("\n[STEP 1] Deduplicating journals_evaluated.jsonl...")
eval_entries = read_jsonl(EVAL_FILE)
original_count = len(eval_entries)
seen_ids = set()
deduped = []
for entry in eval_entries:
    jid = entry.get("journal_id", "")
    if jid not in seen_ids:
        seen_ids.add(jid)
        deduped.append(entry)
eval_entries = deduped
if len(eval_entries) < original_count:
    print(f"  Removed {original_count - len(eval_entries)} duplicates")
write_jsonl(EVAL_FILE, eval_entries)
print(f"  {len(eval_entries)} entries after dedup")

# === STEP 1b: Compact if >5000 ===
if len(eval_entries) > 5000:
    cutoff = (now - timedelta(days=30)).isoformat()
    compacted = [e for e in eval_entries
                 if e.get("evaluated_at", "9999") > cutoff
                 or not e.get("evaluated_at")]
    removed = len(eval_entries) - len(compacted)
    if removed > 0:
        eval_entries = compacted
        write_jsonl(EVAL_FILE, eval_entries)
        print(f"  Compacted: removed {removed} entries older than 30 days")

# === STEP 2: Scan filesystem for journal files ===
print("\n[STEP 2] Scanning filesystem for journal files...")
all_files = []
for root_dir, dirs, files in os.walk(JOURNALS_DIR):
    # Skip hidden/archive dirs
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

print(f"  Found {len(all_files)} journal files in scan window")

# === STEP 3: Compute unevaluated set ===
print("\n[STEP 3] Computing unevaluated journals...")
seen_ids = {e.get("journal_id", "") for e in eval_entries}
unevaluated = [(c, p) for c, p in all_files if c not in seen_ids and os.path.exists(p)]
print(f"  {len(unevaluated)} unevaluated journals")

# === STEP 4: Process unevaluated journals ===
print("\n[STEP 4] Processing journals for signals...")
new_events = []
eval_updates = []
truly_new = []  # Initialize before any conditional

for canonical, fpath in unevaluated:
    try:
        with open(fpath, 'r') as f:
            journal_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"  SKIP {canonical}: {e}")
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now_iso(),
            "action_taken": "skip_error",
            "signals_found": [],
            "reason": f"Read error: {e}"
        })
        continue
    
    signals = extract_signals_from_journal(journal_data, canonical)
    
    if not signals:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now_iso(),
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })
        continue
    
    # Deduplicate signals by type for this journal
    seen_signal_types = set()
    unique_signals = []
    for s in signals:
        key = (canonical, s["type"])
        if key not in seen_signal_types:
            seen_signal_types.add(key)
            unique_signals.append(s)
    
    # Record events for each unique signal
    event_ids_for_journal = []
    for sig in unique_signals:
        event_id = generate_event_id(canonical, sig["type"], now_iso())
        failure_phase = determine_failure_phase(sig["type"], sig["detail"])
        
        # Determine domain from canonical path
        domain = canonical.split("/")[0] if "/" in canonical else "unknown"
        
        event = {
            "event_id": event_id,
            "timestamp": now_iso(),
            "domain": domain,
            "context_summary": sig["detail"],
            "outcome_type": "failure" if sig["type"] in ("execution_error", "cron_errors", "escalation") else sig["type"],
            "outcome_summary": sig["detail"],
            "evidence": [f"canonical: {canonical}", f"signal_type: {sig['type']}"],
            "failure_phase": failure_phase,
            "user_relevance": "agent_only",
            "source_journal": canonical,
            "signal_type": sig["type"],
            "recorded_at": now_iso()
        }
        new_events.append(event)
        event_ids_for_journal.append(event_id)
    
    eval_updates.append({
        "journal_id": canonical,
        "evaluated_at": now_iso(),
        "action_taken": "event_recorded",
        "signals_found": [s["type"] for s in unique_signals],
        "event_ids": event_ids_for_journal,
        "reason": f"Recorded {len(event_ids_for_journal)} events"
    })
    print(f"  {canonical}: {len(event_ids_for_journal)} events ({', '.join(s['type'] for s in unique_signals)})")

print(f"\n  Total new events: {len(new_events)}")

# === STEP 4b: Write new events to events.jsonl ===
if new_events:
    append_jsonl(EVENTS_FILE, new_events)
    print(f"  Appended {len(new_events)} events to events.jsonl")

# === STEP 4c: Post-write dedup of events.jsonl ===
print("\n[STEP 4c] Post-write dedup of events.jsonl...")
all_events = read_jsonl(EVENTS_FILE)
deduped_events = []
seen_dedup_keys = set()
for evt in all_events:
    key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
    if key not in seen_dedup_keys:
        seen_dedup_keys.add(key)
        deduped_events.append(evt)
    # If duplicate, keep the first one (already in deduped_events)
write_jsonl(EVENTS_FILE, deduped_events)
print(f"  {len(all_events)} -> {len(deduped_events)} events after dedup")

# === STEP 4d: Write eval_updates ===
if eval_updates:
    append_jsonl(EVAL_FILE, eval_updates)
    print(f"  Appended {len(eval_updates)} entries to journals_evaluated.jsonl")

# === STEP 5: Lesson Extraction (Two-Pass) ===
print("\n[STEP 5] Lesson extraction (two-pass)...")

# Re-read events from disk
all_events = read_jsonl(EVENTS_FILE)

# Filter to meaningful events (skip unknown/?/None signal_types)
meaningful_events = [e for e in all_events if e.get("signal_type") and e.get("signal_type") not in ("unknown", "?", None, "")]

# Group by (signal_type, failure_phase)
from collections import defaultdict
groups = defaultdict(list)
for evt in meaningful_events:
    key = (evt.get("signal_type", ""), evt.get("failure_phase", ""))
    if key[0] and key[1]:
        groups[key].append(evt)

# Read existing lessons
existing_lessons = read_jsonl(LESSONS_FILE)
existing_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_groups.add(key)

# Pass 1: Extract lesson stubs for groups with 2+ events
new_lessons = []
for (sig_type, phase), events in groups.items():
    if len(events) >= 2 and (sig_type, phase) not in existing_groups:
        lesson_id = f"les_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()[:6]}"
        event_ids = [get_event_id(e) for e in events]
        
        # Build lesson text from event summaries
        summaries = [e.get("context_summary", "")[:100] for e in events[:3]]
        what_text = "; ".join(summaries)
        
        lesson = {
            "lesson_id": lesson_id,
            "event_ids": event_ids,
            "lesson_text": f"[LESSON] What: Recurring {sig_type} in {phase} phase: {what_text}",
            "confidence": "low",
            "scope": events[0].get("domain", "unknown"),
            "status": "proposed",
            "failure_phase": phase,
            "causal_grounding": "what",
            "signal_type": sig_type,
            "skills_affected": [events[0].get("domain", "unknown")],
            "created_at": now_iso(),
            "what": what_text,
            "why": "",
            "when": ""
        }
        new_lessons.append(lesson)

print(f"  Pass 1: {len(new_lessons)} new lesson stubs")

# Pass 2: Causal grounding upgrade
for lesson in new_lessons:
    events_in_group = groups.get((lesson["signal_type"], lesson["failure_phase"]), [])
    
    # Build why from evidence
    evidence_parts = []
    for e in events_in_group[:3]:
        for ev in e.get("evidence", []):
            if ev not in evidence_parts:
                evidence_parts.append(ev)
    
    why_text = "; ".join(evidence_parts[:3]) if evidence_parts else "Pattern observed across multiple events"
    when_text = f"Observed in phase={lesson['failure_phase']}, domain={lesson.get('scope', 'unknown')}"
    
    lesson["confidence"] = "high"
    lesson["causal_grounding"] = "what+why+when"
    lesson["why"] = why_text
    lesson["when"] = when_text
    lesson["lesson_text"] = f"[LESSON] What: {lesson['what']}. Why: {why_text}. When: {when_text}"

if new_lessons:
    append_jsonl(LESSONS_FILE, new_lessons)
    print(f"  Pass 2: Upgraded {len(new_lessons)} lessons to high confidence")

# === STEP 6: Shift Proposal and Activation ===
print("\n[STEP 6] Shift proposal and activation...")

# Read all lessons and shifts
all_lessons = read_jsonl(LESSONS_FILE)
all_shifts = read_jsonl(SHIFTS_FILE)

# Count active shifts
active_shifts = [s for s in all_shifts if s.get("status") == "active"]
proposed_shifts = [s for s in all_shifts if s.get("status") == "proposed"]
print(f"  Active shifts: {len(active_shifts)}, Proposed: {len(proposed_shifts)}")

# Build set of lesson IDs already covered by active/proposed shifts
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

# Propose shifts for high-confidence lessons not already covered
new_proposals = []
for lesson in all_lessons:
    lid = get_lesson_id(lesson)
    if lesson.get('confidence') == 'high' and lid not in covered_lesson_ids:
        shift_id = f"shf_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()[:6]}"
        shift = {
            "shift_id": shift_id,
            "source_lesson_ids": [lid],
            "shift_text": f"Behavioral adjustment for {lesson.get('signal_type', 'unknown')} in {lesson.get('failure_phase', 'execution')} phase: {lesson.get('what', '')[:200]}",
            "status": "proposed",
            "activation_reason": f"Proposed from {lesson.get('signal_type', 'unknown')} lesson ({len(lesson.get('event_ids', []))} events)",
            "created_at": now_iso(),
            "last_reviewed_at": now_iso(),
            "expiry_condition": "14_days without reinforcement",
            "priority": 1,
            "last_reinforced_at": now_iso(),
            "reinforcement_count": 0,
            "failure_phase": lesson.get("failure_phase", "execution"),
            "domain": lesson.get("scope", "unknown")
        }
        new_proposals.append(shift)
        covered_lesson_ids.add(lid)  # Prevent duplicate proposals in same run

print(f"  {len(new_proposals)} new shift proposals")

# Merge-overlap check and activate
CAP = 12
remaining_proposals = []  # Initialize before any loop

for proposal in new_proposals:
    # Check domain+phase overlap with active shifts
    overlap_found = False
    for active in active_shifts:
        active_domain = active.get("domain", "")
        active_phase = get_failure_phase(active)
        prop_domain = proposal.get("domain", "")
        prop_phase = proposal.get("failure_phase", "")
        
        if active_domain == prop_domain and active_phase == prop_phase:
            # Reinforce active shift instead
            active["last_reinforced_at"] = now_iso()
            active["reinforcement_count"] = active.get("reinforcement_count", 0) + 1
            active["last_reviewed_at"] = now_iso()
            overlap_found = True
            print(f"  Reinforced active shift {get_shift_id(active)} (overlap with proposal for {prop_domain}/{prop_phase})")
            break
    
    if not overlap_found:
        remaining_proposals.append(proposal)

# Activate remaining proposals if under cap
activated = 0
for proposal in remaining_proposals:
    current_active = len([s for s in all_shifts if s.get("status") == "active"])
    if current_active < CAP:
        proposal["status"] = "active"
        proposal["last_reviewed_at"] = now_iso()
        activated += 1
        print(f"  Activated shift {get_shift_id(proposal)}")
    else:
        print(f"  Cap reached — keeping proposal {get_shift_id(proposal)} as proposed")

# Rewrite shifts.jsonl with merged set
all_shifts_write = []
seen_shift_ids = set()
for s in all_shifts + new_proposals:
    sid = get_shift_id(s)
    if sid not in seen_shift_ids:
        seen_shift_ids.add(sid)
        all_shifts_write.append(s)

write_jsonl(SHIFTS_FILE, all_shifts_write)
print(f"  Total shifts: {len(all_shifts_write)} (active: {len([s for s in all_shifts_write if s.get('status') == 'active'])})")

# === STEP 7: Decision logging ===
print("\n[STEP 7] Logging decisions...")
decisions = read_jsonl(DECISIONS_FILE)

decision = {
    "decision_id": f"dec_{now.strftime('%Y%m%d_%H%M%S')}",
    "timestamp": now_iso(),
    "decision_type": "journal_ingest",
    "summary": f"Ingest run {run_id}: processed {len(unevaluated)} journals, recorded {len(new_events)} events, extracted {len(new_lessons)} lessons, proposed {len(new_proposals)} shifts, activated {activated}",
    "evidence": [
        f"journals_scanned: {len(unevaluated)}",
        f"events_recorded: {len(new_events)}",
        f"lessons_extracted: {len(new_lessons)}",
        f"shifts_proposed: {len(new_proposals)}",
        f"shifts_activated: {activated}"
    ],
    "outcome": "completed"
}
decisions.append(decision)
write_jsonl(DECISIONS_FILE, decisions)

# === STEP 8: Write Praxis journal ===
print("\n[STEP 8] Writing Praxis journal...")
journal_entry = {
    "run_id": run_id,
    "timestamp": now_iso(),
    "skill": "ocas-praxis",
    "type": "journal_ingest",
    "decision": {
        "summary": decision["summary"],
        "execution_result": {"status": "ok"},
        "payload": {
            "entities_observed": [
                {"entity": "journal_files", "count": len(unevaluated), "user_relevance": "agent_only"},
                {"entity": "new_events", "count": len(new_events), "user_relevance": "agent_only"},
                {"entity": "new_lessons", "count": len(new_lessons), "user_relevance": "agent_only"},
                {"entity": "new_shifts_activated", "count": activated, "user_relevance": "agent_only"}
            ],
            "relationships_observed": [],
            "preferences_observed": []
        },
        "action_result": {
            "booked": False,
            "changed": True,
            "error": None
        }
    },
    "actions_taken": [
        {"action": "scan_journals", "outcome": "completed", "count": len(unevaluated)},
        {"action": "record_events", "outcome": "completed", "count": len(new_events)},
        {"action": "extract_lessons", "outcome": "completed", "count": len(new_lessons)},
        {"action": "propose_shifts", "outcome": "completed", "count": len(new_proposals)},
        {"action": "activate_shifts", "outcome": "completed", "count": activated}
    ],
    "runtime": {
        "model": "openrouter/owl-alpha",
        "duration_seconds": 0
    }
}

journal_path = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_path, exist_ok=True)
journal_file = os.path.join(journal_path, f"{run_id}.json")
with open(journal_file, 'w') as f:
    json.dump(journal_entry, f, indent=2)
print(f"  Journal written to {journal_file}")

# === SUMMARY ===
print("\n" + "=" * 60)
print("INGEST COMPLETE")
print("=" * 60)
print(f"  Journals processed: {len(unevaluated)}")
print(f"  New events: {len(new_events)}")
print(f"  New lessons: {len(new_lessons)}")
print(f"  New shift proposals: {len(new_proposals)}")
print(f"  Shifts activated: {activated}")
print(f"  Total active shifts: {len([s for s in all_shifts_write if s.get('status') == 'active'])}/{CAP}")
print(f"  Total events in store: {len(deduped_events)}")
print(f"  Total lessons in store: {len(all_lessons)}")
print("=" * 60)
