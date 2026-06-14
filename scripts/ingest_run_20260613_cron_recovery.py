#!/usr/bin/env python3
"""
Praxis Journal Ingest Run — 2026-06-13 cron (recovery run)
Fixed version of the ingest script with:
- Proper forge no-op detection (result: "clean" and "no_op")
- Spot observation case-insensitive type matching + results[] all-skipped detection
- Consistent function return value signatures (3-tuple from extract_signals_from_dict, 4-tuple from extract_signals)
- No unpacking mismatches

Run this after removing error entries from journals_evaluated.jsonl.
"""

import json
import os
from datetime import datetime, timedelta, timezone

# === Constants ===
AGENT_ROOT = "/root/.hermes"
JOURNALS_DIR = f"{AGENT_ROOT}/commons/journals"
DATA_DIR = f"{AGENT_ROOT}/commons/data/ocas-praxis"
EVAL_FILE = f"{DATA_DIR}/journals_evaluated.jsonl"
EVENTS_FILE = f"{DATA_DIR}/events.jsonl"
LESSONS_FILE = f"{DATA_DIR}/lessons.jsonl"
SHIFTS_FILE = f"{DATA_DIR}/shifts.jsonl"
DECISIONS_FILE = f"{DATA_DIR}/decisions.jsonl"
JOURNAL_DIR = f"{DATA_DIR}/journal"
EVIDENCE_FILE = f"{DATA_DIR}/evidence.jsonl"

SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy"
]
MEANINGFUL_SIGNAL_TYPES = {
    "escalation", "execution_error", "auth_failure", "correction",
    "persistent_platform_failure", "cron_errors", "failure_keyword",
    "repeated_skip", "platform_failure", "scope_failure"
}
FAILURE_STATUSES = {"error", "partial", "completed_with_errors", "scope_failure", "auth_failure"}
FORGE_NO_OP_RESULTS = {"no_op", "clean"}

# === Normalization Helpers ===
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

# === Utility ===
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

# === Step 1: Deduplicate journals_evaluated.jsonl ===
print("=== Step 1: Deduplicate journals_evaluated.jsonl ===")
eval_entries = read_jsonl(EVAL_FILE)
print(f"  Read {len(eval_entries)} entries")

seen_ids = set()
deduped = []
for entry in eval_entries:
    jid = entry.get("journal_id", "")
    if jid not in seen_ids:
        seen_ids.add(jid)
        deduped.append(entry)

removed = len(eval_entries) - len(deduped)
if removed > 0:
    print(f"  Removed {removed} duplicates")
    write_jsonl(EVAL_FILE, deduped)
    eval_entries = deduped
else:
    print(f"  No duplicates found")

# === Step 1b: Compact if >5000 entries ===
if len(eval_entries) > 5000:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    compacted = [e for e in eval_entries
                 if e.get("evaluated_at", "9999") > cutoff or not e.get("evaluated_at")]
    removed = len(eval_entries) - len(compacted)
    if removed > 0:
        print(f"  Compacted: removed {removed} entries older than 30 days")
        eval_entries = compacted
        write_jsonl(EVAL_FILE, eval_entries)

# === Step 2: Scan filesystem for journal files ===
print("\n=== Step 2: Scan filesystem ===")
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

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

print(f"  Found {len(all_files)} journal files for {today} and {yesterday}")

# === Step 3: Compute unevaluated set ===
print("\n=== Step 3: Compute unevaluated set ===")
seen_ids = {e.get("journal_id", "") for e in eval_entries}
unevaluated = [(c, p) for c, p in all_files if c not in seen_ids and os.path.exists(p)]
print(f"  Unevaluated journals: {len(unevaluated)}")

# === Step 4: Signal extraction ===
print("\n=== Step 4: Signal extraction ===")

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

def extract_signals_from_dict(data):
    """Extract signals from a journal dict. Returns (signals, summary, status)."""
    signals = []
    summary = ""
    status = ""
    
    if not isinstance(data, dict):
        return signals, summary, status
    
    # Get top-level status
    status = data.get("status", "")
    if isinstance(status, str):
        status = status.lower()
    
    # Get top-level summary
    raw_summary = data.get("summary", "")
    if isinstance(raw_summary, str) and raw_summary.strip():
        summary = raw_summary.strip()
    elif isinstance(raw_summary, dict):
        summary = json.dumps(raw_summary)
    
    # === Forge no-op check ===
    result = data.get("result", "")
    if isinstance(result, str) and result.lower().strip() in FORGE_NO_OP_RESULTS:
        return [], "", status
    
    # === Spot observation no-op check ===
    type_field = data.get("type", "")
    if isinstance(type_field, str) and type_field.lower() == "observation":
        # Check results array for all-skipped
        results = data.get("results", [])
        if isinstance(results, list) and results:
            all_skipped = all(
                r.get("status", "").startswith("skipped") or r.get("status", "").startswith("deactivated")
                for r in results if isinstance(r, dict)
            )
            if all_skipped:
                return [], "", status
        # Check summary string for no-op phrases
        if isinstance(raw_summary, str):
            sum_lower = raw_summary.lower()
            if any(phrase in sum_lower for phrase in ["skipped", "permanently broken", "dead watch", "expired", "no new availability", "all skipped"]):
                return [], "", status
    
    # Check top-level escalation_needed
    if data.get("escalation_needed") is True:
        signals.append({"type": "escalation", "source": "top-level"})
    
    # Check decision.execution_result.status
    decision = data.get("decision", {})
    if isinstance(decision, dict):
        exec_result = decision.get("execution_result", {})
        if isinstance(exec_result, dict):
            exec_status = exec_result.get("status", "")
            if exec_status in FAILURE_STATUSES:
                signals.append({"type": "execution_error", "source": "decision.execution_result"})
        
        dec_summary = decision.get("summary", "")
        if isinstance(dec_summary, str) and dec_summary.strip():
            if not summary:
                summary = dec_summary.strip()
            dec_lower = dec_summary.lower()
            if any(kw in dec_lower for kw in ["fail", "error", "unreachable", "broken", "missing"]):
                signals.append({"type": "failure_keyword", "source": "decision.summary"})
    
    # Check actions_taken
    actions = data.get("actions_taken", [])
    if isinstance(actions, list):
        for action in actions:
            if isinstance(action, dict):
                outcome = action.get("outcome", "")
                if isinstance(outcome, str) and outcome.lower() in ("error", "failure", "failed"):
                    signals.append({"type": "execution_error", "source": "actions_taken"})
    
    # Check fixes_applied
    fixes = data.get("fixes_applied", 0)
    if fixes and fixes > 0:
        signals.append({"type": "correction", "source": "fixes_applied"})
    
    checks = data.get("checks", {})
    if isinstance(checks, dict):
        check_fixes = checks.get("fixes_applied", 0)
        if check_fixes and check_fixes > 0:
            signals.append({"type": "correction", "source": "checks.fixes_applied"})
    
    # Check new_findings
    new_findings = data.get("new_findings", [])
    if isinstance(new_findings, list):
        for finding in new_findings:
            if isinstance(finding, dict):
                sev = finding.get("severity", "")
                if sev in ("error", "critical", "high"):
                    signals.append({"type": "escalation", "source": "new_findings"})
    
    # Check nested findings array
    findings = data.get("findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict):
                if finding.get("escalation_needed") is True:
                    signals.append({"type": "escalation", "source": "findings"})
                f_status = finding.get("status", "")
                if f_status in ("error", "failed"):
                    signals.append({"type": "execution_error", "source": "findings"})
                action_taken = finding.get("action_taken", "")
                if isinstance(action_taken, str) and any(kw in action_taken.lower() for kw in ["fix", "correct", "repair"]):
                    signals.append({"type": "correction", "source": "findings"})
    
    # Check findings as dict (finch scan variant)
    if isinstance(data.get("findings"), dict):
        for src_name, src_data in data["findings"].items():
            if isinstance(src_data, dict):
                src_status = src_data.get("status", "")
                if src_status in ("ERROR", "error", "FAILED", "failed"):
                    signals.append({"type": "execution_error", "source": f"findings.{src_name}"})
    
    # Check signals.* (finch scan)
    finch_signals = data.get("signals", {})
    if isinstance(finch_signals, dict):
        cron_data = finch_signals.get("cron", {})
        if isinstance(cron_data, dict):
            new_errors = cron_data.get("new_errors", [])
            if isinstance(new_errors, list) and new_errors:
                signals.append({"type": "cron_errors", "source": "signals.cron.new_errors"})
            error_breakdown = cron_data.get("error_breakdown", {})
            if isinstance(error_breakdown, dict):
                for err_type, count in error_breakdown.items():
                    if isinstance(count, int) and count > 0:
                        signals.append({"type": "cron_errors", "source": f"signals.cron.error_breakdown.{err_type}"})
        
        for sig_key, sig_val in finch_signals.items():
            if isinstance(sig_val, dict):
                notes = sig_val.get("notes", "")
                if isinstance(notes, str) and any(kw in notes.lower() for kw in ["escalat", "critical", "urgent"]):
                    signals.append({"type": "escalation", "source": f"signals.{sig_key}.notes"})
    
    # Check tasks_added (finch)
    tasks_added = data.get("tasks_added", [])
    if isinstance(tasks_added, list):
        for task in tasks_added:
            if isinstance(task, str) and any(kw in task.lower() for kw in ["error", "fail", "missing", "broken"]):
                signals.append({"type": "failure_keyword", "source": "tasks_added"})
    
    # Check top-level summary for failure keywords
    if isinstance(raw_summary, str) and raw_summary.strip():
        summary_lower = raw_summary.lower()
        if any(kw in summary_lower for kw in ["fail", "error", "unreachable", "broken", "missing", "dead"]):
            signals.append({"type": "failure_keyword", "source": "top-level summary"})
        if any(kw in summary_lower for kw in ["oauth", "token", "401", "auth"]):
            signals.append({"type": "auth_failure", "source": "top-level summary"})
    
    # Apply semantic suppression for summary-derived signals
    if summary and signals:
        if should_suppress_summary_signals(summary, signals):
            signals = [s for s in signals if s["type"] not in ("failure_keyword", "auth_failure")]
    
    return signals, summary, status


def extract_signals(canonical, file_path):
    """Extract behavioral signals from a journal file. Returns (signals, summary, status, raw_data)."""
    signals = []
    summary = ""
    status = ""
    raw_data = {}
    
    try:
        with open(file_path, 'r') as f:
            raw_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return signals, summary, status, raw_data
    
    # Handle list-format journals
    if isinstance(raw_data, list):
        for entry in raw_data:
            if isinstance(entry, dict):
                entry_signals, entry_summary, entry_status = extract_signals_from_dict(entry)
                signals.extend(entry_signals)
                if entry_summary:
                    summary = entry_summary
                if entry_status:
                    status = entry_status
        return signals, summary, status, raw_data
    
    # Handle dict-format journals
    if isinstance(raw_data, dict):
        sub_signals, summary, status = extract_signals_from_dict(raw_data)
        signals.extend(sub_signals)
    
    return signals, summary, status, raw_data


new_events = []
eval_updates = []
truly_new = []

for canonical, file_path in unevaluated:
    try:
        signals, summary, status, raw_data = extract_signals(canonical, file_path)
    except Exception as e:
        print(f"  ERROR processing {canonical}: {e}")
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now_iso(),
            "action_taken": "error",
            "signals_found": [],
            "reason": f"Processing error: {str(e)}"
        })
        continue
    
    if not signals:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now_iso(),
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })
        continue
    
    # Determine failure phase
    failure_phase = "execution"
    summary_lower = summary.lower() if isinstance(summary, str) else ""
    if any(kw in summary_lower for kw in ["should have", "before", "wrong approach", "didn't check", "missing prerequisite"]):
        failure_phase = "planning"
    elif any(kw in summary_lower for kw in ["too verbose", "wrong format", "just give me", "make it concise", "don't explain"]):
        failure_phase = "response"
    
    skill = canonical.split("/")[0] if "/" in canonical else "unknown"
    
    journal_events = []
    for sig in signals:
        sig_type = sig["type"]
        if sig_type not in MEANINGFUL_SIGNAL_TYPES:
            continue
        
        event_id = f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
        event = {
            "event_id": event_id,
            "source_journal": canonical,
            "signal_type": sig_type,
            "failure_phase": failure_phase,
            "domain": skill,
            "summary": summary[:500] if summary else "",
            "recorded_at": now_iso(),
            "evidence": {"summary": summary[:200], "source_file": canonical}
        }
        new_events.append(event)
        journal_events.append(sig_type)
    
    if journal_events:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now_iso(),
            "action_taken": "event_recorded",
            "signals_found": list(set(journal_events)),
            "reason": f"Extracted {len(journal_events)} signal type(s)"
        })
        truly_new.append(canonical)
    else:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now_iso(),
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No meaningful signals after filtering"
        })

print(f"  New events: {len(new_events)}")
print(f"  Journals with signals: {len(truly_new)}")

# === Step 4b: Write events and eval_updates ===
if new_events:
    append_jsonl(EVENTS_FILE, new_events)
    print(f"  Appended {len(new_events)} events to {EVENTS_FILE}")

append_jsonl(EVAL_FILE, eval_updates)
print(f"  Appended {len(eval_updates)} entries to {EVAL_FILE}")

# === Step 4c: Post-write dedup of events ===
print("\n=== Step 4c: Post-write dedup ===")
all_events = read_jsonl(EVENTS_FILE)
print(f"  Total events on disk: {len(all_events)}")

event_map = {}
for evt in all_events:
    key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
    if key not in event_map:
        event_map[key] = evt
    else:
        existing = event_map[key]
        if evt.get("recorded_at", "") < existing.get("recorded_at", ""):
            event_map[key] = evt

deduped_events = list(event_map.values())
dupes_removed = len(all_events) - len(deduped_events)
if dupes_removed > 0:
    print(f"  Removed {dupes_removed} duplicate events")
    write_jsonl(EVENTS_FILE, deduped_events)
else:
    print(f"  No duplicates found")

# === Step 5: Lesson Extraction (Two-Pass) ===
print("\n=== Step 5: Lesson Extraction ===")
all_events = read_jsonl(EVENTS_FILE)
meaningful_events = [e for e in all_events if e.get("signal_type") in MEANINGFUL_SIGNAL_TYPES]
print(f"  Meaningful events: {len(meaningful_events)}")

groups = {}
for evt in meaningful_events:
    key = (evt.get("signal_type", ""), evt.get("failure_phase", ""))
    if key not in groups:
        groups[key] = []
    groups[key].append(evt)

print(f"  Event groups: {len(groups)}")
for key, evts in groups.items():
    print(f"    {key}: {len(evts)} events")

existing_lessons = read_jsonl(LESSONS_FILE)
existing_lesson_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_lesson_groups.add(key)

print(f"  Existing lesson groups: {existing_lesson_groups}")

new_lessons = []
for (sig_type, phase), evts in groups.items():
    if len(evts) < 2:
        continue
    if (sig_type, phase) in existing_lesson_groups:
        print(f"  Skipping duplicate lesson: signal_type={sig_type}, phase={phase}")
        continue
    
    domains = list(set(get_event_domain(e) for e in evts))
    event_ids = [get_event_id(e) for e in evts]
    
    what = f"{len(evts)} events of type '{sig_type}' in {phase} phase"
    why = f"Repeated pattern across {len(evts)} occurrences"
    when = f"During {phase} phase of operations"
    
    summaries = [e.get("summary", "") for e in evts if e.get("summary")]
    if summaries:
        why = f"Repeated pattern: {'; '.join(summaries[:3])}"
    
    lesson_id = f"les_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
    lesson = {
        "lesson_id": lesson_id,
        "signal_type": sig_type,
        "failure_phase": phase,
        "lesson_text": f"[LESSON] What: {what}. Why: {why[:200]}. When: {when}",
        "confidence": "high",
        "event_count": len(evts),
        "events_referenced": event_ids,
        "causal_grounding": {"what": what, "why": why[:200], "when": when},
        "domains_affected": domains,
        "recorded_at": now_iso()
    }
    new_lessons.append(lesson)

print(f"  New lessons: {len(new_lessons)}")

if new_lessons:
    append_jsonl(LESSONS_FILE, new_lessons)
    print(f"  Appended {len(new_lessons)} lessons to {LESSONS_FILE}")

# === Step 6: Shift Proposal ===
print("\n=== Step 6: Shift Proposal ===")
all_lessons = read_jsonl(LESSONS_FILE)
all_shifts = read_jsonl(SHIFTS_FILE)

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

print(f"  Active shifts: {sum(1 for s in all_shifts if s.get('status') == 'active')}")
print(f"  Covered lesson IDs: {len(covered_lesson_ids)}")

active_count = sum(1 for s in all_shifts if s.get('status') == 'active')
remaining_proposals = []

for lesson in all_lessons:
    lid = get_lesson_id(lesson)
    if lesson.get('confidence') == 'high' and lid not in covered_lesson_ids:
        remaining_proposals.append(lesson)

print(f"  Lessons eligible for shift proposal: {len(remaining_proposals)}")

CAP = 12
new_shifts = []
for lesson in remaining_proposals:
    if active_count >= CAP:
        print(f"  Cap reached ({active_count}/{CAP}), stopping proposals")
        break
    
    lid = get_lesson_id(lesson)
    sig_type = lesson.get("signal_type", "")
    phase = lesson.get("failure_phase", "execution")
    domains = lesson.get("domains_affected", [])
    domain = domains[0] if domains else "general"
    
    overlap = False
    for s in all_shifts:
        if s.get('status') != 'active':
            continue
        s_domain = s.get('domain', '')
        s_phase = get_failure_phase(s)
        if s_domain == domain and s_phase == phase:
            s['reinforcement_count'] = s.get('reinforcement_count', 0) + 1
            s['last_reinforced_at'] = now_iso()
            overlap = True
            print(f"  Reinforced existing shift: {get_shift_id(s)} ({domain}/{phase})")
            break
    
    if not overlap:
        shift_id = f"shf_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
        shift = {
            "shift_id": shift_id,
            "status": "active",
            "shift_text": f"When {sig_type} occurs in {phase} phase ({domain}), apply lesson: {lesson.get('lesson_text', '')[:100]}",
            "lesson_id": lid,
            "signal_type": sig_type,
            "failure_phase": phase,
            "domain": domain,
            "confidence": "high",
            "reinforcement_count": 0,
            "proposed_at": now_iso(),
            "activated_at": now_iso()
        }
        new_shifts.append(shift)
        active_count += 1
        print(f"  Proposed new shift: {shift_id} ({domain}/{phase})")

if new_shifts:
    updated_shifts = all_shifts + new_shifts
    write_jsonl(SHIFTS_FILE, updated_shifts)
    print(f"  Wrote {len(updated_shifts)} total shifts to {SHIFTS_FILE}")
else:
    if any(s.get('last_reinforced_at') == now_iso() for s in all_shifts):
        write_jsonl(SHIFTS_FILE, all_shifts)
        print(f"  Wrote reinforced shifts back to {SHIFTS_FILE}")

# === Step 7: Write journal entry ===
print("\n=== Step 7: Write journal entry ===")
run_id = f"r_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
journal_path = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_path, exist_ok=True)

journal_entry = {
    "run_id": run_id,
    "timestamp": now_iso(),
    "type": "ingest",
    "summary": f"Praxis journal ingest: {len(unevaluated)} journals scanned, {len(new_events)} events recorded, {len(new_lessons)} lessons extracted, {len(new_shifts)} shifts proposed",
    "data": {
        "journals_scanned": len(unevaluated),
        "new_events": len(new_events),
        "new_lessons": len(new_lessons),
        "new_shifts": len(new_shifts),
        "total_events": len(read_jsonl(EVENTS_FILE)),
        "total_lessons": len(read_jsonl(LESSONS_FILE)),
        "total_shifts": len(read_jsonl(SHIFTS_FILE)),
        "active_shifts": sum(1 for s in read_jsonl(SHIFTS_FILE) if s.get('status') == 'active'),
        "journals_with_signals": truly_new
    }
}

with open(os.path.join(journal_path, f"{run_id}.json"), 'w') as f:
    json.dump(journal_entry, f, indent=2)

print(f"  Journal written: {run_id}")

# === Step 8: Write evidence record ===
print("\n=== Step 8: Write evidence record ===")
evidence_record = {
    "run_id": run_id,
    "timestamp": now_iso(),
    "activity": "journal_ingest",
    "journals_scanned": len(unevaluated),
    "events_recorded": len(new_events),
    "lessons_extracted": len(new_lessons),
    "shifts_proposed": len(new_shifts),
    "not_activity_reason": None if unevaluated else "No new journals to process"
}
append_jsonl(EVIDENCE_FILE, [evidence_record])

# === Step 9: Write decision log ===
print("\n=== Step 9: Write decision log ===")
decision = {
    "timestamp": now_iso(),
    "decision": "praxis:journal_ingest",
    "reasoning": f"Scanned {len(unevaluated)} new journals, recorded {len(new_events)} events, extracted {len(new_lessons)} lessons, proposed {len(new_shifts)} shifts",
    "outcome": "completed",
    "entities_observed": [canonical for canonical, _ in unevaluated],
    "relationships_observed": [f"event:{e.get('event_id','')} -> journal:{e.get('source_journal','')}" for e in new_events],
    "preferences_observed": []
}
append_jsonl(DECISIONS_FILE, [decision])

# === Summary ===
print("\n" + "="*60)
print("PRAXIS JOURNAL INGEST — SUMMARY")
print("="*60)
print(f"  Journals scanned:      {len(unevaluated)}")
print(f"  New events recorded:   {len(new_events)}")
print(f"  New lessons extracted: {len(new_lessons)}")
print(f"  New shifts proposed:   {len(new_shifts)}")
print(f"  Total events:          {len(read_jsonl(EVENTS_FILE))}")
print(f"  Total lessons:         {len(read_jsonl(LESSONS_FILE))}")
print(f"  Total shifts:          {len(read_jsonl(SHIFTS_FILE))}")
print(f"  Active shifts:         {sum(1 for s in read_jsonl(SHIFTS_FILE) if s.get('status') == 'active')}/12")
print("="*60)
