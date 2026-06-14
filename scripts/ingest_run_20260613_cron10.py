#!/usr/bin/env python3
"""
Praxis Journal Ingest Run — 2026-06-13 evening cron
Scans all skill journals for new entries, extracts behavioral signals,
runs two-pass lesson extraction, proposes/activates shifts.
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta

# === PATHS (absolute literals — never use os.path.join with /root base) ===
DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
JOURNALS_DIR = "/root/.hermes/commons/journals"
JOURNAL_DIR = os.path.join(DATA_DIR, "journal")
SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}

EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsons")
SHIFTS_FILE_CORRECT = os.path.join(DATA_DIR, "shifts.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")
EVIDENCE_FILE = os.path.join(DATA_DIR, "evidence.jsonl")

# === HELPERS (defined before any code that uses them) ===
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

def append_jsonl(path, records):
    with open(path, "a") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

def rewrite_jsonl(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

def now_str():
    return datetime.now(timezone.utc).isoformat()

# === SUPPRESS PHRASES for summary noise filter ===
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy"
]

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

# === MAIN ===
def main():
    run_start = now_str()
    print(f"[praxis_ingest] Run started at {run_start}")
    
    # Initialize accumulators BEFORE any loop/conditional
    new_events = []
    eval_updates = []
    new_lessons = []
    new_shifts = []
    decisions = []
    new_events_for_dedup = []
    
    # === STEP 1: Deduplicate journals_evaluated.jsonl ===
    eval_entries = read_jsonl(EVAL_FILE)
    deduped_eval = []
    seen_ids = set()
    for entry in eval_entries:
        jid = entry.get("journal_id", "")
        if jid not in seen_ids:
            seen_ids.add(jid)
            deduped_eval.append(entry)
    
    removed_eval = len(eval_entries) - len(deduped_eval)
    if removed_eval > 0:
        print(f"  Dedup eval: removed {removed_eval} duplicate entries ({len(eval_entries)} -> {len(deduped_eval)})")
        rewrite_jsonl(EVAL_FILE, deduped_eval)
    
    # === STEP 1b: Compact if >5000 entries ===
    if len(deduped_eval) > 5000:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        compacted = [e for e in deduped_eval
                     if e.get("evaluated_at", "9999") > cutoff
                     or not e.get("evaluated_at")]
        removed = len(deduped_eval) - len(compacted)
        if removed > 0:
            deduped_eval = compacted
            rewrite_jsonl(EVAL_FILE, deduped_eval)
            print(f"  Compacted: removed {removed} entries older than 30 days")
    
    seen_ids = {e.get("journal_id", "") for e in deduped_eval}
    
    # === STEP 2: Scan filesystem for journal files (today + yesterday) ===
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
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
    
    unevaluated = [(c, p) for c, p in all_files if c not in seen_ids and os.path.exists(p)]
    
    print(f"  Scanned {len(all_files)} journal files, {len(unevaluated)} unevaluated")
    
    # === STEP 3: Signal extraction from unevaluated journals ===
    for canonical, full_path in unevaluated:
        signals = []
        summary = ""  # Initialize before any loop
        data_list = []  # Initialize
        
        try:
            with open(full_path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  WARN: Cannot read {canonical}: {e}")
            eval_updates.append({
                "journal_id": canonical,
                "evaluated_at": now_str(),
                "action_taken": "error",
                "signals_found": [],
                "reason": f"Cannot read file: {e}"
            })
            continue
        
        # Handle list-format journals
        if isinstance(data, list):
            data_list = data
        else:
            data_list = [data]
        
        for entry in data_list:
            if not isinstance(entry, dict):
                continue
            
            status = ""
            entry_type = ""
            
            # Check top-level escalation_needed
            if entry.get("escalation_needed") is True:
                signals.append({"type": "escalation", "source": "top_level"})
            
            # Check decision.execution_result.status
            decision = entry.get("decision", {})
            if isinstance(decision, dict):
                exec_result = decision.get("execution_result", {})
                if isinstance(exec_result, dict):
                    status = exec_result.get("status", "")
            
            # Also check top-level status
            if not status:
                status = entry.get("status", "")
            
            entry_type = entry.get("type", "")
            
            # Check summary field (may be at decision level or top level)
            summary = ""
            if isinstance(decision, dict):
                summary = decision.get("summary", "")
            if not summary:
                summary = entry.get("summary", "")
            
            if not isinstance(summary, str):
                summary = json.dumps(summary) if summary else ""
            
            # Noise filter: dict-format summaries with success status
            raw_summary = entry.get("summary", decision.get("summary", ""))
            if isinstance(raw_summary, dict):
                if status in ("ok", "success", "complete", "completed") or entry_type == "observation":
                    pass  # Don't extract failure_keyword from success scan data
                else:
                    summary_str = json.dumps(raw_summary)
                    # Check for failure keywords in non-success dict summaries
                    for kw in ["fail", "error", "crash", "timeout", "unreachable", "broken"]:
                        if kw in summary_str.lower():
                            signals.append({"type": "failure_keyword", "keyword": kw, "source": "dict_summary"})
            
            # Handle "completed_with_errors" status
            if status in ("completed_with_errors", "scope_failure"):
                signals.append({"type": "execution_error", "source": "status_incomplete"})
            
            # Check error/partial status
            if status in ("error", "partial"):
                signals.append({"type": "execution_error", "source": "execution_result"})
            
            # Check summary for failure keywords (only non-empty strings)
            if summary and isinstance(summary, str) and len(summary.strip()) > 0:
                summary_lower = summary.lower()
                failure_keywords = ["fail", "error", "crash", "timeout", "unreachable", "broken", "missing", "corrupt"]
                for kw in failure_keywords:
                    if kw in summary_lower:
                        signals.append({"type": "failure_keyword", "keyword": kw, "source": "summary"})
                
                # Check for auth-related keywords
                auth_keywords = ["oauth", "401", "unauthorized", "token expired", "auth_failure"]
                for kw in auth_keywords:
                    if kw in summary_lower:
                        signals.append({"type": "auth_failure", "keyword": kw, "source": "summary"})
                
                # Skip/permanently broken signals
                skip_keywords = ["skipped", "permanently broken", "dead watch", "expired availability"]
                skip_count = 0
                for kw in skip_keywords:
                    if kw in summary_lower:
                        skip_count += 1
                if skip_count > 0:
                    signals.append({"type": "repeated_skip", "count": skip_count, "source": "summary"})
            
            # Check actions_taken
            actions = entry.get("actions_taken", [])
            if isinstance(actions, list):
                for action in actions:
                    if isinstance(action, dict):
                        outcome = action.get("outcome", "")
                        if isinstance(outcome, str) and outcome in ("error", "failure", "failed"):
                            signals.append({"type": "execution_error", "keyword": outcome, "source": "actions_taken"})
            
            # Check fixes_applied
            fixes = entry.get("fixes_applied", 0)
            if fixes and isinstance(fixes, (int, float)) and fixes > 0:
                signals.append({"type": "correction", "fixes_applied": fixes, "source": "top_level"})
            
            checks = entry.get("checks", {})
            if isinstance(checks, dict):
                check_fixes = checks.get("fixes_applied", 0)
                if check_fixes and isinstance(check_fixes, (int, float)) and check_fixes > 0:
                    signals.append({"type": "correction", "fixes_applied": check_fixes, "source": "checks"})
            
            # Check new_findings array
            new_findings = entry.get("new_findings", [])
            if isinstance(new_findings, list):
                for finding in new_findings:
                    if isinstance(finding, dict):
                        sev = finding.get("severity", "")
                        if sev in ("critical", "high"):
                            signals.append({"type": "escalation", "severity": sev, "source": "new_findings"})
            
            # Check nested findings array
            findings = entry.get("findings", [])
            if isinstance(findings, list):
                for finding in findings:
                    if isinstance(finding, dict):
                        if finding.get("escalation_needed") is True:
                            signals.append({"type": "escalation", "source": "findings"})
                        f_status = finding.get("status", "")
                        if f_status in ("error", "failed"):
                            signals.append({"type": "execution_error", "source": "findings"})
            
            # Check finch signals.* structure
            finch_signals = entry.get("signals", {})
            if isinstance(finch_signals, dict):
                cron_data = finch_signals.get("cron", {})
                if isinstance(cron_data, dict):
                    new_cron_errors = cron_data.get("new_errors", [])
                    if isinstance(new_cron_errors, list):
                        for err in new_cron_errors:
                            if isinstance(err, dict):
                                signals.append({"type": "cron_errors", "source": "finch_signals_cron"})
                    
                    error_breakdown = cron_data.get("error_breakdown", {})
                    if isinstance(error_breakdown, dict):
                        for err_type, count in error_breakdown.items():
                            if isinstance(count, (int, float)) and count > 0:
                                signals.append({"type": "cron_errors", "error_type": err_type, "count": count, "source": "finch_error_breakdown"})
                
                # Check tasks_added
                tasks_added = entry.get("tasks_added", [])
                if isinstance(tasks_added, list):
                    for task in tasks_added:
                        if isinstance(task, str) and any(kw in task.lower() for kw in ["error", "fail", "missing", "broken"]):
                            signals.append({"type": "failure_keyword", "keyword": task, "source": "tasks_added"})
            
            # Check sources.* structure (legacy finch)
            sources = entry.get("sources", {})
            if isinstance(sources, dict):
                for src_name, src_data in sources.items():
                    if isinstance(src_data, dict):
                        src_status = src_data.get("status", "")
                        if src_status in ("error", "unreachable", "failed"):
                            signals.append({"type": "execution_error", "source": f"sources_{src_name}"})
        
        # === Apply noise filters ===
        
        # Suppress summary-derived signals for routine scan summaries
        if summary and isinstance(summary, str) and signals:
            if should_suppress_summary_signals(summary, signals):
                signals = [s for s in signals if s["type"] not in ("failure_keyword", "auth_failure")]
        
        # Remove duplicate signal types from same journal (keep first occurrence per type)
        seen_signal_types = set()
        unique_signals = []
        for s in signals:
            st = s["type"]
            if st not in seen_signal_types:
                seen_signal_types.add(st)
                unique_signals.append(s)
        signals = unique_signals
        
        # === Record events or mark as no_signal ===
        if not signals:
            eval_updates.append({
                "journal_id": canonical,
                "evaluated_at": now_str(),
                "action_taken": "no_signal",
                "signals_found": [],
                "reason": "No behavioral signals after noise filtering"
            })
            continue
        
        # Determine failure_phase from signals and summary
        failure_phase = "execution"  # default for error signals
        if any(s["type"] == "escalation" for s in signals):
            failure_phase = "planning"
        
        # Create events for each unique signal type
        event_ids_for_eval = []
        for sig in signals:
            event_id = f"evt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
            event = {
                "event_id": event_id,
                "timestamp": now_str(),
                "domain": canonical.split("/")[0],
                "context_summary": summary[:200] if summary else "",
                "outcome_type": "failure" if sig["type"] in ("execution_error", "failure_keyword", "auth_failure", "cron_errors") else "observation",
                "outcome_summary": f"Signal: {sig['type']} from {canonical}",
                "evidence": [f"canonical: {canonical}", f"signal_type: {sig['type']}"],
                "failure_phase": failure_phase,
                "user_relevance": "agent_only",
                "source_journal": canonical,
                "signal_type": sig["type"],
                "recorded_at": now_str()
            }
            new_events.append(event)
            event_ids_for_eval.append(event_id)
        
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now_str(),
            "action_taken": "event_recorded",
            "signals_found": [s["type"] for s in signals],
            "event_ids": event_ids_for_eval,
            "reason": f"Recorded {len(new_events)} events"  # Will be updated
        })
    
    # === STEP 3b: Write new events to events.jsonl ===
    if new_events:
        # Post-write dedup: read all events, dedup by (source_journal, signal_type)
        existing_events = read_jsonl(EVENTS_FILE)
        all_events = existing_events + new_events
        
        # Dedup by (source_journal, signal_type) — keep earliest recorded_at
        deduped_events = []
        seen_keys = {}
        for evt in all_events:
            key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
            if key not in seen_keys:
                seen_keys[key] = evt
                deduped_events.append(evt)
            else:
                # Keep the one with earlier recorded_at
                existing = seen_keys[key]
                if evt.get("recorded_at", "") < existing.get("recorded_at", ""):
                    deduped_events = [e for e in deduped_events if get_event_id(e) != get_event_id(existing)]
                    deduped_events.append(evt)
                    seen_keys[key] = evt
        
        rewrite_jsonl(EVENTS_FILE, deduped_events)
        print(f"  Wrote {len(new_events)} new events (total after dedup: {len(deduped_events)})")
        
        # Update eval_update reasons with correct count
        for eu in eval_updates:
            if eu.get("action_taken") == "event_recorded":
                eu["reason"] = f"Recorded {len(eu.get('signals_found', []))} signal types"
    
    # === STEP 3c: Write eval_updates ===
    if eval_updates:
        append_jsonl(EVAL_FILE, eval_updates)
        print(f"  Wrote {len(eval_updates)} eval updates")
    
    # === STEP 4: Lesson extraction (two-pass) ===
    # Re-read events from disk
    all_events = read_jsonl(EVENTS_FILE)
    
    # Filter to meaningful events (skip unknown/None signal_types)
    MEANINGFUL_TYPES = {"auth_failure", "escalation", "execution_error", "correction", "failure_keyword", "cron_errors", "repeated_skip", "persistent_platform_failure"}
    meaningful_events = [e for e in all_events if e.get("signal_type") in MEANINGFUL_TYPES]
    
    # Group by (signal_type, failure_phase)
    groups = {}
    for evt in meaningful_events:
        key = (evt.get("signal_type", ""), evt.get("failure_phase", "execution"))
        if key not in groups:
            groups[key] = []
        groups[key].append(evt)
    
    # Read existing lessons for dedup
    existing_lessons = read_jsonl(LESSONS_FILE)
    existing_lesson_groups = set()
    for l in existing_lessons:
        key = (l.get("signal_type", ""), l.get("failure_phase", ""))
        if key[0] and key[1]:
            existing_lesson_groups.add(key)
    
    # Pass 1: Extract lesson stubs for groups with 2+ events
    lesson_stubs = []
    for (sig_type, phase), events in groups.items():
        if len(events) >= 2 and (sig_type, phase) not in existing_lesson_groups:
            stub = {
                "signal_type": sig_type,
                "failure_phase": phase,
                "event_count": len(events),
                "events_referenced": [get_event_id(e) for e in events[:5]],
                "domains_affected": list(set(e.get("domain", "unknown") for e in events))
            }
            lesson_stubs.append(stub)
    
    # Pass 2: Causal grounding upgrade
    for stub in lesson_stubs:
        sig_type = stub["signal_type"]
        phase = stub["failure_phase"]
        count = stub["event_count"]
        domains = stub["domains_affected"]
        
        # Build causal grounding
        what = f"{count} event(s) of type '{sig_type}' in {phase} phase"
        why = f"Repeated pattern across {count} occurrence(s) in {', '.join(domains)}"
        when = f"During {phase} phase of operations"
        
        lesson_id = f"les_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
        lesson_text = f"[LESSON] What: {what}. Why: {why}. When: {when}"
        
        lesson = {
            "lesson_id": lesson_id,
            "signal_type": sig_type,
            "failure_phase": phase,
            "lesson_text": lesson_text,
            "confidence": "high",
            "event_count": count,
            "events_referenced": stub["events_referenced"],
            "causal_grounding": {"what": what, "why": why, "when": when},
            "domains_affected": domains,
            "recorded_at": now_str()
        }
        new_lessons.append(lesson)
    
    if new_lessons:
        append_jsonl(LESSONS_FILE, new_lessons)
        print(f"  Extracted {len(new_lessons)} new lessons (high confidence)")
    
    # === STEP 5: Shift proposal and activation ===
    # Read all shifts
    all_shifts = read_jsonl(SHIFTS_FILE_CORRECT)
    
    # Build set of lesson IDs already covered by active/proposed shifts
    covered_lesson_ids = set()
    for s in all_shifts:
        if s.get("status") in ("active", "proposed"):
            for field in ["lesson_id", "lesson_ref", "source_lesson", "source_lesson_ids"]:
                val = s.get(field)
                if val:
                    if isinstance(val, list):
                        covered_lesson_ids.update(val)
                    elif isinstance(val, str):
                        covered_lesson_ids.add(val)
    
    # Read all lessons (including newly written)
    all_lessons = read_jsonl(LESSONS_FILE)
    
    # Active shift count
    active_count = sum(1 for s in all_shifts if s.get("status") == "active")
    ACTIVE_CAP = 12
    
    # Propose shifts for uncovered high-confidence lessons
    proposals = []
    for lesson in all_lessons:
        lid = get_lesson_id(lesson)
        if lesson.get("confidence") == "high" and lid not in covered_lesson_ids:
            cg = get_lesson_causal_grounding(lesson)
            shift_text = f"When {lesson.get('signal_type', 'unknown')} occurs in {lesson.get('failure_phase', 'execution')} phase, apply lesson: {lesson.get('lesson_text', '')}"
            
            shift_id = f"shf_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
            proposal = {
                "shift_id": shift_id,
                "status": "proposed",
                "shift_text": shift_text,
                "lesson_id": lid,
                "signal_type": lesson.get("signal_type", ""),
                "failure_phase": lesson.get("failure_phase", "execution"),
                "domain": lesson.get("domains_affected", ["unknown"])[0] if lesson.get("domains_affected") else "unknown",
                "confidence": "high",
                "reinforcement_count": 0,
                "proposed_at": now_str()
            }
            proposals.append(proposal)
    
    # Merge-overlap check and activate
    activated_count = 0
    for proposal in proposals:
        # Check domain+phase overlap with active shifts
        overlap = False
        for active in all_shifts:
            if active.get("status") != "active":
                continue
            active_domain = active.get("domain", "")
            active_phase = get_failure_phase(active)
            if (active_domain == proposal.get("domain", "") and 
                active_phase == proposal.get("failure_phase", "")):
                # Reinforce existing shift
                active["reinforcement_count"] = active.get("reinforcement_count", 0) + 1
                active["last_reinforced_at"] = now_str()
                overlap = True
                break
        
        if not overlap and active_count < ACTIVE_CAP:
            proposal["status"] = "active"
            proposal["activated_at"] = now_str()
            all_shifts.append(proposal)
            active_count += 1
            activated_count += 1
        elif not overlap:
            # At cap — leave as proposed
            all_shifts.append(proposal)
    
    # Rewrite shifts file with merged set
    rewrite_jsonl(SHIFTS_FILE_CORRECT, all_shifts)
    
    if proposals:
        print(f"  Proposed {len(proposals)} shifts, activated {activated_count} (active: {active_count}/{ACTIVE_CAP})")
    
    # === STEP 6: Write decisions log ===
    decision = {
        "decision_id": f"dec_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp": now_str(),
        "decision": "journal_ingest",
        "reasoning": f"Scanned {len(all_files)} journals, {len(unevaluated)} new. Extracted {len(new_events)} events, {len(new_lessons)} lessons, proposed {len(proposals)} shifts.",
        "outcome": "completed",
        "journals_scanned": len(unevaluated),
        "events_recorded": len(new_events),
        "lessons_extracted": len(new_lessons),
        "shifts_proposed": len(proposals),
        "shifts_activated": activated_count
    }
    decisions.append(decision)
    append_jsonl(DECISIONS_FILE, decisions)
    
    # === STEP 7: Write Praxis journal for this run ===
    run_id = f"r_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
    journal_path = os.path.join(JOURNAL_DIR, today)
    os.makedirs(journal_path, exist_ok=True)
    
    journal_entry = {
        "run_id": run_id,
        "timestamp": now_str(),
        "type": "journal_ingest",
        "decision": {
            "execution_result": {"status": "ok"},
            "summary": f"Praxis ingest: {len(unevaluated)} journals scanned, {len(new_events)} events, {len(new_lessons)} lessons, {len(proposals)} shifts proposed",
            "payload": {
                "entities_observed": [],
                "relationships_observed": [],
                "preferences_observed": []
            }
        },
        "actions_taken": [
            {"action": "scan_journals", "outcome": "completed", "count": len(unevaluated)},
            {"action": "extract_events", "outcome": "completed", "count": len(new_events)},
            {"action": "extract_lessons", "outcome": "completed", "count": len(new_lessons)},
            {"action": "propose_shifts", "outcome": "completed", "count": len(proposals)}
        ],
        "runtime": {
            "model": "openrouter/owl-alpha",
            "duration_seconds": 0
        }
    }
    
    with open(os.path.join(journal_path, f"{run_id}.json"), "w") as f:
        json.dump(journal_entry, f, indent=2)
    
    # === SUMMARY ===
    print(f"\n{'='*60}")
    print(f"PRAXIS INGEST COMPLETE — {now_str()}")
    print(f"  Journals scanned:    {len(unevaluated)} new / {len(all_files)} total")
    print(f"  Events recorded:     {len(new_events)}")
    print(f"  Lessons extracted:   {len(new_lessons)}")
    print(f"  Shifts proposed:     {len(proposals)}")
    print(f"  Shifts activated:    {activated_count}")
    print(f"  Active shifts:       {active_count}/{ACTIVE_CAP}")
    print(f"  Total events:        {len(all_events)}")
    print(f"  Total lessons:       {len(all_lessons)}")
    print(f"  Total shifts:        {len(all_shifts)}")
    print(f"{'='*60}")
    
    return {
        "journals_scanned": len(unevaluated),
        "events_recorded": len(new_events),
        "lessons_extracted": len(new_lessons),
        "shifts_proposed": len(proposals),
        "shifts_activated": activated_count,
        "active_shifts": active_count,
        "total_events": len(all_events),
        "total_lessons": len(all_lessons),
        "total_shifts": len(all_shifts)
    }

if __name__ == "__main__":
    result = main()
    print(f"\nResult: {json.dumps(result, indent=2)}")
