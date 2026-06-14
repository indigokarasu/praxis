#!/usr/bin/env python3
"""
Praxis Supplemental Ingest — Re-scan journals that may have been under-processed.
Handles signal_sources.* schema (finch scan-0200, scan-0702 pattern).
"""

import json
import os
from datetime import datetime, timezone
from collections import defaultdict

DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
JOURNALS_DIR = "/root/.hermes/commons/journals"
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsons")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")

# Fix: correct filename
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")

SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy"
]

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

def get_event_id(evt):
    return evt.get("event_id", evt.get("id", ""))

def get_lesson_id(les):
    return les.get("lesson_id", les.get("id", ""))

def get_shift_id(s):
    return s.get("shift_id", s.get("id", "?"))

def get_failure_phase(s):
    return s.get("failure_phase", s.get("phase", "execution"))

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

def extract_signals_enhanced(journal_data, canonical):
    """Enhanced signal extraction including signal_sources.* schema."""
    signals = []
    
    if isinstance(journal_data, list):
        for entry in journal_data:
            if isinstance(entry, dict):
                signals.extend(extract_signals_enhanced(entry, canonical))
        return signals
    
    if not isinstance(journal_data, dict):
        return signals
    
    # === TOP-LEVEL FIELDS ===
    
    # escalation_needed
    if journal_data.get("escalation_needed") is True:
        signals.append({"type": "escalation", "detail": "top-level escalation_needed=true", "source": "top_level"})
    
    # decision.execution_result.status
    decision = journal_data.get("decision", {})
    if isinstance(decision, dict):
        exec_result = decision.get("execution_result", {})
        if isinstance(exec_result, dict):
            status = exec_result.get("status", "")
            if status in ("error", "partial", "completed_with_errors"):
                signals.append({"type": "execution_error", "detail": f"decision.status={status}", "source": "decision"})
    
    # Top-level status
    status = journal_data.get("status", "")
    if status in ("error", "partial", "completed_with_errors"):
        signals.append({"type": "execution_error", "detail": f"status={status}", "source": "top_level"})
    
    # Summary field
    summary = ""
    dec_summary = decision.get("summary", "") if isinstance(decision, dict) else ""
    top_summary = journal_data.get("summary", "")
    
    if isinstance(dec_summary, str) and dec_summary.strip():
        summary = dec_summary
    elif isinstance(top_summary, str) and top_summary.strip():
        summary = top_summary
    elif isinstance(top_summary, dict):
        summary = json.dumps(top_summary)
    elif isinstance(dec_summary, dict):
        summary = json.dumps(dec_summary)
    
    # actions_taken[].outcome
    actions_taken = journal_data.get("actions_taken", [])
    if isinstance(actions_taken, list):
        for action in actions_taken:
            if isinstance(action, dict):
                outcome = action.get("outcome", "")
                if outcome in ("error", "failure", "failed"):
                    signals.append({"type": "execution_error", "detail": f"action_outcome={outcome}", "source": "actions_taken"})
                elif outcome in ("corrected", "fix_applied", "fixed"):
                    signals.append({"type": "correction", "detail": f"action_outcome={outcome}", "source": "actions_taken"})
    
    # fixes_applied
    fixes = journal_data.get("fixes_applied", 0)
    if isinstance(fixes, int) and fixes > 0:
        signals.append({"type": "correction", "detail": f"fixes_applied={fixes}", "source": "top_level"})
    
    checks = journal_data.get("checks", {})
    if isinstance(checks, dict):
        checks_fixes = checks.get("fixes_applied", 0)
        if isinstance(checks_fixes, int) and checks_fixes > 0:
            signals.append({"type": "correction", "detail": f"checks.fixes_applied={checks_fixes}", "source": "checks"})
    
    # findings[] (nested)
    findings = journal_data.get("findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict):
                if finding.get("escalation_needed") is True:
                    signals.append({"type": "escalation", "detail": f"finding escalation: {finding.get('title', finding.get('id', ''))}", "source": "findings"})
                f_status = finding.get("status", "")
                if f_status in ("error", "failed"):
                    signals.append({"type": "execution_error", "detail": f"finding status={f_status}: {finding.get('title', '')}", "source": "findings"})
                action_taken = finding.get("action_taken", "")
                if isinstance(action_taken, str) and any(kw in action_taken.lower() for kw in ["fix", "correct", "update", "applied"]):
                    signals.append({"type": "correction", "detail": f"finding action: {action_taken}", "source": "findings"})
    
    # new_findings[]
    new_findings = journal_data.get("new_findings", [])
    if isinstance(new_findings, list):
        for finding in new_findings:
            if isinstance(finding, dict):
                sev = finding.get("severity", "")
                if sev in ("error", "critical", "high"):
                    signals.append({"type": "execution_error", "detail": f"new_finding: {finding.get('title', '')}", "source": "new_findings"})
    
    # === signal_sources.* SCHEMA (finch scan-0200, scan-0702) ===
    signal_sources = journal_data.get("signal_sources", {})
    if isinstance(signal_sources, dict):
        for src_name, src_data in signal_sources.items():
            if not isinstance(src_data, dict):
                continue
            
            src_status = src_data.get("status", "")
            
            # blocked/error/failed status
            if src_status in ("blocked", "error", "failed", "inactive"):
                signals.append({"type": "execution_error", "detail": f"signal_sources.{src_name}.status={src_status}", "source": "signal_sources"})
            
            # error field
            src_error = src_data.get("error", "")
            if isinstance(src_error, str) and src_error.strip() and src_error != "none":
                signals.append({"type": "execution_error", "detail": f"signal_sources.{src_name}.error={src_error[:100]}", "source": "signal_sources"})
            
            # new_issues_since_last_scan
            new_issues = src_data.get("new_issues_since_last_scan", src_data.get("new_issues", []))
            if isinstance(new_issues, list) and new_issues:
                for issue in new_issues:
                    if isinstance(issue, dict):
                        signals.append({"type": "execution_error", "detail": f"new_issue: {issue.get('title', '')} (tier {issue.get('tier', '?')})", "source": "signal_sources"})
            
            # cron_health specifics
            if src_name == "cron_health":
                error_jobs = src_data.get("error_jobs", 0)
                if isinstance(error_jobs, int) and error_jobs > 0:
                    signals.append({"type": "cron_errors", "detail": f"cron_health.error_jobs={error_jobs}", "source": "signal_sources"})
                
                unchanged_errors = src_data.get("unchanged_errors", [])
                for err in unchanged_errors[:3]:  # Limit to first 3
                    if isinstance(err, dict):
                        job = err.get("job", "")
                        error_msg = err.get("error", "")
                        if "oauth" in error_msg.lower() or "token" in error_msg.lower():
                            signals.append({"type": "auth_failure", "detail": f"cron_error: {job} — {error_msg[:80]}", "source": "signal_sources"})
    
    # === signals.* SCHEMA (older finch pattern) ===
    finch_signals = journal_data.get("signals", {})
    if isinstance(finch_signals, dict):
        cron_signals = finch_signals.get("cron", {})
        if isinstance(cron_signals, dict):
            new_errors = cron_signals.get("new_errors", [])
            if isinstance(new_errors, list):
                for err in new_errors:
                    if isinstance(err, dict):
                        signals.append({"type": "cron_errors", "detail": f"new_cron_error: {err.get('job', '')} — {err.get('error', '')[:80]}", "source": "signals"})
            
            error_breakdown = cron_signals.get("error_breakdown", {})
            if isinstance(error_breakdown, dict):
                for key, val in error_breakdown.items():
                    if isinstance(val, int) and val > 0:
                        signals.append({"type": "cron_errors", "detail": f"error_breakdown.{key}={val}", "source": "signals"})
        
        for sig_key, sig_val in finch_signals.items():
            if isinstance(sig_val, dict):
                notes = sig_val.get("notes", "")
                if isinstance(notes, str) and notes.strip():
                    notes_lower = notes.lower()
                    for kw in ["error", "fail", "escalat", "correction"]:
                        if kw in notes_lower:
                            signals.append({"type": "failure_keyword", "detail": f"signals.{sig_key}.notes: {notes}", "source": "signals"})
                            break
    
    # tasks_added[]
    tasks_added = journal_data.get("tasks_added", [])
    if isinstance(tasks_added, list):
        for task in tasks_added:
            if isinstance(task, str):
                task_lower = task.lower()
                if any(kw in task_lower for kw in ["error", "fail"]):
                    signals.append({"type": "failure_keyword", "detail": f"task_added: {task}", "source": "tasks_added"})
    
    # === SUMMARY KEYWORD SCANNING ===
    if isinstance(summary, str) and summary.strip():
        summary_lower = summary.lower()
        
        # Check for OAuth/auth failures (only if not already caught by signal_sources)
        has_auth_signal = any(s["type"] == "auth_failure" for s in signals)
        if not has_auth_signal:
            auth_keywords = ["oauth", "token expired", "token revoked", "invalid_grant", "unauthorized"]
            for kw in auth_keywords:
                if kw in summary_lower:
                    # Only flag if the summary indicates an active problem
                    if any(indicator in summary_lower for indicator in ["broken", "blocked", "expired", "revoked", "invalid"]):
                        signals.append({"type": "auth_failure", "detail": f"summary contains auth issue: '{kw}'", "source": "summary"})
                    break
        
        # Check for failure keywords (only if no other signals exist)
        failure_keywords = ["error", "failed", "failure", "timeout", "truncat", "crash", "exception"]
        for kw in failure_keywords:
            if kw in summary_lower:
                signals.append({"type": "failure_keyword", "detail": f"summary contains '{kw}'", "source": "summary"})
                break
        
        # Apply semantic suppression
        if should_suppress_summary_signals(summary, signals):
            signals = [s for s in signals if s["type"] not in ("failure_keyword", "auth_failure")]
    
    return signals

def determine_failure_phase(signal_type, detail):
    detail_lower = detail.lower() if isinstance(detail, str) else ""
    
    if any(kw in detail_lower for kw in ["should have", "before", "wrong approach", "didn't check", "missing prerequisite"]):
        return "planning"
    if any(kw in detail_lower for kw in ["too verbose", "wrong format", "just give me", "make it concise", "don't explain"]):
        return "response"
    if signal_type in ("execution_error", "cron_errors", "escalation", "correction", "auth_failure"):
        return "execution"
    return "execution"

def generate_event_id(canonical, signal_type, ts):
    import hashlib
    base = f"{canonical}_{signal_type}_{ts}"
    h = hashlib.md5(base.encode()).hexdigest()[:8]
    return f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{h}"

# === MAIN: Re-scan specific journals ===

print("=" * 60)
print("PRAXIS SUPPLEMENTAL INGEST — signal_sources schema fix")
print("=" * 60)

now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = (now - __import__('datetime').timedelta(days=1)).strftime("%Y-%m-%d")

# Load existing data
eval_entries = read_jsonl(EVAL_FILE)
existing_eval_ids = {e.get("journal_id", "") for e in eval_entries}
all_events = read_jsonl(EVENTS_FILE)
existing_lessons = read_jsonl(LESSONS_FILE)
all_shifts = read_jsonl(SHIFTS_FILE)

# Find journals that were evaluated but may have been under-processed
# Specifically: finch scan-0200 and scan-0702 which use signal_sources schema
JOURNALS_TO_RESCAN = [
    "ocas-finch/2026-06-12/scan-0200.json",
    "ocas-finch/2026-06-12/scan-0702.json",
]

# Also check elephas journals
for jid in ["ocas-elephas/2026-06-12/run_cron_20260612_063604.json",
            "ocas-elephas/2026-06-12/run_cron_20260612_065328.json"]:
    JOURNALS_TO_RESCAN.append(jid)

# And spot journals
for jid in ["ocas-spot/2026-06-11/sweep-20260611-001.json",
            "ocas-spot/2026-06-11/sweep-20260611-203018.json",
            "ocas-spot/2026-06-11/sweep-20260611-204500.json"]:
    JOURNALS_TO_RESCAN.append(jid)

print(f"\nRe-scanning {len(JOURNALS_TO_RESCAN)} journals for additional signals...")

new_events = []
additional_eval_notes = []

for canonical in JOURNALS_TO_RESCAN:
    # Find the file
    parts = canonical.split("/")
    if len(parts) == 3:
        fpath = os.path.join(JOURNALS_DIR, parts[0], parts[1], parts[2])
    else:
        continue
    
    if not os.path.exists(fpath):
        print(f"  SKIP {canonical}: file not found")
        continue
    
    with open(fpath, 'r') as f:
        try:
            journal_data = json.load(f)
        except json.JSONDecodeError:
            print(f"  SKIP {canonical}: JSON error")
            continue
    
    signals = extract_signals_enhanced(journal_data, canonical)
    
    if not signals:
        print(f"  {canonical}: no additional signals")
        continue
    
    # Dedup signals by type
    seen_types = set()
    unique_signals = []
    for s in signals:
        key = (canonical, s["type"])
        if key not in seen_types:
            seen_types.add(key)
            unique_signals.append(s)
    
    # Check which signal types are already covered by existing events
    existing_signal_types = set()
    for evt in all_events:
        if evt.get("source_journal", "") == canonical:
            existing_signal_types.add(evt.get("signal_type", ""))
    
    truly_new_signals = [s for s in unique_signals if s["type"] not in existing_signal_types]
    
    if not truly_new_signals:
        print(f"  {canonical}: all signal types already covered")
        continue
    
    domain = canonical.split("/")[0]
    event_ids = []
    for sig in truly_new_signals:
        event_id = generate_event_id(canonical, sig["type"], now_iso())
        failure_phase = determine_failure_phase(sig["type"], sig["detail"])
        
        event = {
            "event_id": event_id,
            "timestamp": now_iso(),
            "domain": domain,
            "context_summary": sig["detail"],
            "outcome_type": "failure" if sig["type"] in ("execution_error", "cron_errors", "escalation", "auth_failure") else sig["type"],
            "outcome_summary": sig["detail"],
            "evidence": [f"canonical: {canonical}", f"signal_type: {sig['type']}", f"source: {sig.get('source', 'unknown')}"],
            "failure_phase": failure_phase,
            "user_relevance": "agent_only",
            "source_journal": canonical,
            "signal_type": sig["type"],
            "recorded_at": now_iso()
        }
        new_events.append(event)
        event_ids.append(event_id)
        all_events.append(event)  # Add to the full list for lesson extraction
    
    if event_ids:
        print(f"  {canonical}: {len(event_ids)} NEW events: {[s['type'] for s in truly_new_signals]}")
        additional_eval_notes.append({
            "journal_id": canonical,
            "evaluated_at": now_iso(),
            "action_taken": "supplemental_event_recorded",
            "signals_found": [s["type"] for s in truly_new_signals],
            "event_ids": event_ids,
            "reason": f"Supplemental scan found {len(event_ids)} additional signal types"
        })

# Write new events
if new_events:
    append_jsonl(EVENTS_FILE, new_events)
    print(f"\nAppended {len(new_events)} new events to events.jsonl")
    
    # Post-write dedup
    all_events_disk = read_jsonl(EVENTS_FILE)
    deduped = []
    seen_keys = set()
    for evt in all_events_disk:
        key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(evt)
    write_jsonl(EVENTS_FILE, deduped)
    print(f"Post-dedup: {len(all_events_disk)} -> {len(deduped)} events")
else:
    print("\nNo new events found")

# Write supplemental eval notes
if additional_eval_notes:
    append_jsonl(EVAL_FILE, additional_eval_notes)

# === LESSON EXTRACTION (re-run with updated events) ===
print("\n[LESSON EXTRACTION] Re-extracting lessons with updated events...")

all_events_fresh = read_jsonl(EVENTS_FILE)
meaningful_events = [e for e in all_events_fresh if e.get("signal_type") and e.get("signal_type") not in ("unknown", "?", None, "")]

groups = defaultdict(list)
for evt in meaningful_events:
    key = (evt.get("signal_type", ""), evt.get("failure_phase", ""))
    if key[0] and key[1]:
        groups[key].append(evt)

existing_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_groups.add(key)

new_lessons = []
for (sig_type, phase), events in groups.items():
    if len(events) >= 2 and (sig_type, phase) not in existing_groups:
        lesson_id = f"les_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()[:6]}"
        event_ids = [get_event_id(e) for e in events]
        summaries = [e.get("context_summary", "")[:100] for e in events[:3]]
        what_text = "; ".join(summaries)
        
        why_parts = []
        for e in events[:3]:
            for ev in e.get("evidence", []):
                if ev not in why_parts:
                    why_parts.append(ev)
        why_text = "; ".join(why_parts[:3]) if why_parts else "Pattern observed across multiple events"
        when_text = f"Observed in phase={phase}"
        
        lesson = {
            "lesson_id": lesson_id,
            "event_ids": event_ids,
            "lesson_text": f"[LESSON] What: {what_text}. Why: {why_text}. When: {when_text}",
            "confidence": "high",
            "scope": events[0].get("domain", "unknown"),
            "status": "proposed",
            "failure_phase": phase,
            "causal_grounding": "what+why+when",
            "signal_type": sig_type,
            "skills_affected": list(set(e.get("domain", "unknown") for e in events)),
            "created_at": now_iso(),
            "what": what_text,
            "why": why_text,
            "when": when_text
        }
        new_lessons.append(lesson)
        existing_groups.add((sig_type, phase))

if new_lessons:
    append_jsonl(LESSONS_FILE, new_lessons)
    print(f"  Added {len(new_lessons)} new lessons")
    for l in new_lessons:
        print(f"    - {l['signal_type']}/{l['failure_phase']}: {l['what'][:80]}")
else:
    print("  No new lessons (all groups already covered)")

# === SHIFT PROPOSALS ===
print("\n[SHIFT PROPOSALS] Checking for new shifts...")

all_lessons_fresh = read_jsonl(LESSONS_FILE)
all_shifts_fresh = read_jsonl(SHIFTS_FILE)

active_shifts = [s for s in all_shifts_fresh if s.get("status") == "active"]
covered_lesson_ids = set()
for s in all_shifts_fresh:
    if s.get('status') in ('active', 'proposed'):
        for field in ['lesson_id', 'lesson_ref', 'source_lesson', 'source_lesson_ids']:
            val = s.get(field)
            if val:
                if isinstance(val, list):
                    covered_lesson_ids.update(val)
                elif isinstance(val, str):
                    covered_lesson_ids.add(val)

new_proposals = []
for lesson in all_lessons_fresh:
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
        covered_lesson_ids.add(lid)

# Merge-overlap check and activate
CAP = 12
activated = 0
remaining_proposals = []

for proposal in new_proposals:
    overlap_found = False
    for active in active_shifts:
        active_domain = active.get("domain", "")
        active_phase = get_failure_phase(active)
        prop_domain = proposal.get("domain", "")
        prop_phase = proposal.get("failure_phase", "")
        
        if active_domain == prop_domain and active_phase == prop_phase:
            active["last_reinforced_at"] = now_iso()
            active["reinforcement_count"] = active.get("reinforcement_count", 0) + 1
            active["last_reviewed_at"] = now_iso()
            overlap_found = True
            print(f"  Reinforced active shift {get_shift_id(active)}")
            break
    
    if not overlap_found:
        remaining_proposals.append(proposal)

for proposal in remaining_proposals:
    current_active = len([s for s in all_shifts_fresh if s.get("status") == "active"])
    if current_active < CAP:
        proposal["status"] = "active"
        activated += 1
        print(f"  Activated shift {get_shift_id(proposal)}: {proposal['shift_text'][:80]}")
    else:
        print(f"  Cap reached — keeping proposal as proposed")

# Rewrite shifts
if new_proposals:
    all_shifts_write = []
    seen_sids = set()
    for s in all_shifts_fresh + new_proposals:
        sid = get_shift_id(s)
        if sid not in seen_sids:
            seen_sids.add(sid)
            all_shifts_write.append(s)
    write_jsonl(SHIFTS_FILE, all_shifts_write)
    active_count = len([s for s in all_shifts_write if s.get("status") == "active"])
    print(f"  Total shifts: {len(all_shifts_write)} (active: {active_count}/{CAP})")

# === SUMMARY ===
print("\n" + "=" * 60)
print("SUPPLEMENTAL INGEST COMPLETE")
print("=" * 60)
print(f"  New events: {len(new_events)}")
print(f"  New lessons: {len(new_lessons)}")
print(f"  New shifts activated: {activated}")
print(f"  Total events: {len(read_jsonl(EVENTS_FILE))}")
print(f"  Total lessons: {len(read_jsonl(LESSONS_FILE))}")
print(f"  Total active shifts: {len([s for s in read_jsonl(SHIFTS_FILE) if s.get('status') == 'active'])}")
print("=" * 60)
