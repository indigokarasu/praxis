#!/usr/bin/env python3
"""
Praxis Journal Ingest Run — 2026-06-13 cron
Scans skill journals, extracts behavioral signals, records events,
extracts lessons (two-pass), proposes/activates shifts.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

# === PATHS (absolute literals — os.path.join strips leading dot) ===
AGENT_ROOT = "/root/.hermes"
JOURNALS_DIR = os.path.join(AGENT_ROOT, "commons/journals")
DATA_DIR = os.path.join(AGENT_ROOT, "commons/data/ocas-praxis")
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")
JOURNAL_DIR = os.path.join(DATA_DIR, "journal")
EVIDENCE_FILE = os.path.join(DATA_DIR, "evidence.jsonl")

SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
ACTIVE_SHIFT_CAP = 12
SHIFT_DECAY_DAYS = 14

now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
run_id = f"r_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"

# === NORMALIZATION HELPERS ===
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

# === LOAD EXISTING DATA ===
def load_jsonl(path):
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

eval_entries = load_jsonl(EVAL_FILE)
events = load_jsonl(EVENTS_FILE)
lessons = load_jsonl(LESSONS_FILE)
shifts = load_jsonl(SHIFTS_FILE)

print(f"Loaded: {len(eval_entries)} evals, {len(events)} events, {len(lessons)} lessons, {len(shifts)} shifts")

# === STEP 1: DEDUP journals_evaluated.jsonl ===
seen_ids = set()
deduped_evals = []
for entry in eval_entries:
    jid = entry.get("journal_id", "")
    if jid not in seen_ids:
        seen_ids.add(jid)
        deduped_evals.append(entry)

if len(deduped_evals) < len(eval_entries):
    print(f"  Dedup evals: {len(eval_entries)} -> {len(deduped_evals)}")
    eval_entries = deduped_evals
    with open(EVAL_FILE, 'w') as f:
        for e in eval_entries:
            f.write(json.dumps(e) + "\n")

# === STEP 1b: COMPACT if >5000 entries ===
if len(eval_entries) > 5000:
    cutoff = (now - timedelta(days=30)).isoformat()
    compacted = [e for e in eval_entries
                 if e.get("evaluated_at", "9999") > cutoff or not e.get("evaluated_at")]
    removed = len(eval_entries) - len(compacted)
    if removed > 0:
        eval_entries = compacted
        with open(EVAL_FILE, 'w') as f:
            for e in eval_entries:
                f.write(json.dumps(e) + "\n")
        print(f"  Compacted: removed {removed} entries older than 30 days")

# === STEP 2: SCAN FILESYSTEM ===
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

print(f"  Found {len(all_files)} journal files for {today} + {yesterday}")

# === STEP 3: COMPUTE UNEVALUATED ===
seen_eval_ids = {e.get("journal_id", "") for e in eval_entries}
unevaluated = [(c, p) for c, p in all_files if c not in seen_eval_ids and os.path.exists(p)]
print(f"  Unevaluated journals: {len(unevaluated)}")

# === SUPPRESS PHRASES for summary noise filter ===
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy"
]

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

# === SIGNAL EXTRACTION ===
FAILURE_KEYWORDS = ["error", "failed", "failure", "timeout", "crash", "exception",
                    "broken", "unavailable", "denied", "rejected", "corrupt"]
AUTH_KEYWORDS = ["oauth", "token", "401", "unauthorized", "auth", "credential", "expired"]

def extract_signals(journal_data, canonical):
    signals = []
    summary = ""
    status = ""

    # Handle list-format journals
    if isinstance(journal_data, list):
        for entry in journal_data:
            entry_signals, entry_summary, entry_status = extract_signals_from_entry(entry)
            signals.extend(entry_signals)
            if entry_summary:
                summary = entry_summary
            if entry_status:
                status = entry_status
        return signals, summary, status

    # Handle dict-format journals
    return extract_signals_from_entry(journal_data)

def extract_signals_from_entry(data):
    signals = []
    summary = ""
    status = ""

    if not isinstance(data, dict):
        return signals, summary, status

    # Top-level escalation_needed
    if data.get("escalation_needed") is True:
        signals.append({"type": "escalation", "detail": "Top-level escalation_needed: true"})

    # Status checks
    exec_result = data.get("execution_result", {})
    if isinstance(exec_result, dict):
        status = exec_result.get("status", "")
    if not status:
        status = data.get("status", "")

    # Check for completed_with_errors
    if status in ("completed_with_errors", "scope_failure", "auth_failure"):
        signals.append({"type": "execution_error", "detail": f"Status: {status}"})

    # Decision summary
    decision = data.get("decision", {})
    if isinstance(decision, dict):
        dec_summary = decision.get("summary", "")
        if isinstance(dec_summary, str) and dec_summary.strip():
            summary = dec_summary
            dec_status = decision.get("status", "")
            if dec_status in ("error", "partial"):
                signals.append({"type": "execution_error", "detail": f"Decision status: {dec_status}"})
        elif isinstance(dec_summary, dict):
            # Dict-format summary with success status = noise filter
            pass

    # Top-level summary
    if not summary:
        top_summary = data.get("summary", "")
        if isinstance(top_summary, str) and top_summary.strip():
            summary = top_summary
        elif isinstance(top_summary, dict):
            # Dict-format summary — don't keyword match if status is ok
            if status not in ("ok", "success", "complete", "completed", ""):
                summary = json.dumps(top_summary)

    # Actions taken
    actions_taken = data.get("actions_taken", [])
    if isinstance(actions_taken, list):
        for action in actions_taken:
            if isinstance(action, dict):
                outcome = action.get("outcome", "")
                if isinstance(outcome, str) and outcome.lower() in ("error", "failure", "failed", "correction"):
                    signals.append({"type": "execution_error", "detail": f"Action outcome: {outcome}"})

    # Fixes applied
    checks = data.get("checks", {})
    if isinstance(checks, dict) and checks.get("fixes_applied", 0) > 0:
        signals.append({"type": "correction", "detail": f"Fixes applied: {checks['fixes_applied']}"})

    # New findings
    new_findings = data.get("new_findings", [])
    if isinstance(new_findings, list):
        for finding in new_findings:
            if isinstance(finding, dict):
                sev = finding.get("severity", "")
                if sev in ("error", "critical", "high"):
                    signals.append({"type": "execution_error", "detail": f"Finding: {finding.get('title', '')}"})

    # Nested findings array
    findings = data.get("findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict):
                if finding.get("escalation_needed") is True:
                    signals.append({"type": "escalation", "detail": f"Finding escalation: {finding.get('title', finding.get('id', ''))}"})
                f_status = finding.get("status", "")
                if f_status in ("error", "failed"):
                    signals.append({"type": "execution_error", "detail": f"Finding status: {f_status}"})
                action_taken = finding.get("action_taken", "")
                if isinstance(action_taken, str) and any(kw in action_taken.lower() for kw in ["fix", "correct", "repair"]):
                    signals.append({"type": "correction", "detail": f"Fix action: {action_taken}"})

    # Finch signals.* (not sources.*)
    finch_signals = data.get("signals", {})
    if isinstance(finch_signals, dict):
        cron_data = finch_signals.get("cron", {})
        if isinstance(cron_data, dict):
            new_errors = cron_data.get("new_errors", [])
            if isinstance(new_errors, list) and new_errors:
                for err in new_errors:
                    signals.append({"type": "cron_errors", "detail": str(err)})
            error_breakdown = cron_data.get("error_breakdown", {})
            if isinstance(error_breakdown, dict):
                for key, val in error_breakdown.items():
                    if isinstance(val, (int, float)) and val > 0:
                        signals.append({"type": "cron_errors", "detail": f"{key}: {val}"})
        # Check all signal sources for notes
        for src_name, src_data in finch_signals.items():
            if isinstance(src_data, dict):
                notes = src_data.get("notes", "")
                if isinstance(notes, str) and any(kw in notes.lower() for kw in ["escalat", "critical", "new error"]):
                    signals.append({"type": "escalation", "detail": f"Finch {src_name} notes: {notes}"})

    # Finch tasks_added
    tasks_added = data.get("tasks_added", [])
    if isinstance(tasks_added, list):
        for task in tasks_added:
            if isinstance(task, str) and any(kw in task.lower() for kw in ["error", "fail", "broken"]):
                signals.append({"type": "failure_keyword", "detail": f"Task: {task}"})

    # Keyword extraction from summary (only if non-empty string)
    if isinstance(summary, str) and summary.strip():
        summary_lower = summary.lower()
        # Only extract keywords if status indicates failure
        if status in ("error", "partial", "failed", "completed_with_errors", "scope_failure", "auth_failure"):
            for kw in FAILURE_KEYWORDS:
                if kw in summary_lower:
                    signals.append({"type": "failure_keyword", "detail": f"Keyword '{kw}' in summary"})
                    break
            for kw in AUTH_KEYWORDS:
                if kw in summary_lower:
                    signals.append({"type": "auth_failure", "detail": f"Auth keyword '{kw}' in summary"})
                    break

    # Apply semantic suppression for summary-derived signals
    if isinstance(summary, str) and summary.strip() and signals:
        if should_suppress_summary_signals(summary, signals):
            signals = [s for s in signals if s["type"] not in ("failure_keyword", "auth_failure")]

    return signals, summary, status

# === STEP 4: PROCESS UNEVALUATED JOURNALS ===
new_events = []
eval_updates = []
journals_with_no_signal = 0
journals_with_signals = 0

for canonical, full_path in unevaluated:
    try:
        with open(full_path, 'r') as f:
            journal_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": f"Failed to read: {e}"
        })
        continue

    signals, summary, status = extract_signals(journal_data, canonical)

    # Determine failure phase
    def get_failure_phase_from_signals(signals, summary, status):
        if status in ("error", "partial", "failed", "completed_with_errors"):
            return "execution"
        if isinstance(summary, str):
            sl = summary.lower()
            if any(kw in sl for kw in ["should have", "before", "wrong approach", "didn't check", "missing prerequisite"]):
                return "planning"
            if any(kw in sl for kw in ["too verbose", "wrong format", "just give me", "make it concise", "don't explain"]):
                return "response"
            if any(kw in sl for kw in ["failed", "timeout", "wrong parameter", "error"]):
                return "execution"
        return "execution" if signals else "null"

    if not signals:
        # No signals — mark as no_signal
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })
        journals_with_no_signal += 1
        continue

    journals_with_signals += 1

    # Record events for each signal
    for sig in signals:
        phase = get_failure_phase_from_signals(signals, summary, status)
        event_id = f"evt_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"
        skill_name = canonical.split("/")[0] if "/" in canonical else "unknown"

        event = {
            "event_id": event_id,
            "source_journal": canonical,
            "signal_type": sig["type"],
            "failure_phase": phase,
            "domain": skill_name,
            "detail": sig["detail"],
            "summary": summary if isinstance(summary, str) else json.dumps(summary) if isinstance(summary, dict) else "",
            "status": status,
            "recorded_at": now.isoformat(),
            "evidence": {"journal_path": canonical, "signal": sig}
        }
        new_events.append(event)

    eval_updates.append({
        "journal_id": canonical,
        "evaluated_at": now.isoformat(),
        "action_taken": "event_recorded",
        "signals_found": [s["type"] for s in signals],
        "reason": f"Extracted {len(signals)} signal(s)"
    })

print(f"  Journals with signals: {journals_with_signals}, no signal: {journals_with_no_signal}")
print(f"  New events to record: {len(new_events)}")

# === STEP 4b: WRITE NEW EVENTS ===
if new_events:
    with open(EVENTS_FILE, 'a') as f:
        for evt in new_events:
            f.write(json.dumps(evt) + "\n")
    print(f"  Wrote {len(new_events)} new events")

    # Post-write dedup by (source_journal, signal_type)
    all_events = load_jsonl(EVENTS_FILE)
    deduped_events = []
    seen_event_keys = set()
    for evt in all_events:
        key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
        if key not in seen_event_keys:
            seen_event_keys.add(key)
            deduped_events.append(evt)
        # else: skip duplicate (source_journal, signal_type)

    if len(deduped_events) < len(all_events):
        print(f"  Post-write dedup: {len(all_events)} -> {len(deduped_events)} events")
        with open(EVENTS_FILE, 'w') as f:
            for evt in deduped_events:
                f.write(json.dumps(evt) + "\n")
        events = deduped_events
    else:
        events = all_events
else:
    print("  No new events to write")

# === WRITE EVAL UPDATES ===
if eval_updates:
    with open(EVAL_FILE, 'a') as f:
        for eu in eval_updates:
            f.write(json.dumps(eu) + "\n")
    print(f"  Wrote {len(eval_updates)} eval updates")

# === STEP 5: LESSON EXTRACTION (TWO-PASS) ===
# Re-read events from disk to ensure freshness
all_events = load_jsonl(EVENTS_FILE)

# Filter to meaningful events
MEANINGFUL_SIGNAL_TYPES = {"auth_failure", "escalation", "execution_error", "correction",
                           "cron_errors", "failure_keyword"}
meaningful_events = [e for e in all_events
                     if e.get("signal_type", "") in MEANINGFUL_SIGNAL_TYPES
                     and e.get("failure_phase", "null") != "null"]

# Group by (signal_type, failure_phase)
from collections import defaultdict
groups = defaultdict(list)
for evt in meaningful_events:
    key = (evt.get("signal_type", ""), evt.get("failure_phase", "null"))
    groups[key].append(evt)

# Load existing lessons for dedup
existing_lessons = load_jsonl(LESSONS_FILE)
existing_lesson_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_lesson_groups.add(key)

# Pass 1: Extract lesson stubs for groups with 2+ events
new_lessons_pass1 = []
for (sig_type, phase), group_events in groups.items():
    if len(group_events) < 2:
        continue
    if (sig_type, phase) in existing_lesson_groups:
        continue

    lesson_id = f"les_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"
    domains = list(set(e.get("domain", "unknown") for e in group_events))

    lesson_stub = {
        "lesson_id": lesson_id,
        "signal_type": sig_type,
        "failure_phase": phase,
        "event_count": len(group_events),
        "domains": domains,
        "lesson_text": f"Recurring {sig_type} in {phase} phase ({len(group_events)} events)",
        "confidence": "low",
        "causal_grounding": {},
        "created_at": now.isoformat()
    }
    new_lessons_pass1.append(lesson_stub)

print(f"  Pass 1: {len(new_lessons_pass1)} new lesson stubs")

# Pass 2: Causal grounding upgrade
new_lessons_final = []
for lesson_stub in new_lessons_pass1:
    sig_type = lesson_stub["signal_type"]
    phase = lesson_stub["failure_phase"]
    group_events = groups.get((sig_type, phase), [])

    # Build causal grounding
    what = f"Recurring {sig_type} pattern detected in {phase} phase across {len(group_events)} events"
    why = f"Multiple instances of {sig_type} in {phase} phase suggest systemic issue"
    when = f"Applies to {', '.join(lesson_stub['domains'])} skill(s) during {phase} phase"

    # Try to extract better "why" from event details
    details = [e.get("detail", "") for e in group_events if e.get("detail")]
    if details:
        why = f"Pattern: {'; '.join(details[:3])}"

    lesson_stub["confidence"] = "high"
    lesson_stub["causal_grounding"] = {
        "what": what,
        "why": why,
        "when": when
    }
    lesson_stub["lesson_text"] = f"[LESSON] What: {what}. Why: {why}. When: {when}"
    new_lessons_final.append(lesson_stub)

print(f"  Pass 2: {len(new_lessons_final)} lessons with causal grounding")

# Write new lessons
if new_lessons_final:
    with open(LESSONS_FILE, 'a') as f:
        for les in new_lessons_final:
            f.write(json.dumps(les) + "\n")
    print(f"  Wrote {len(new_lessons_final)} new lessons")

    # Update in-memory
    lessons = load_jsonl(LESSONS_FILE)
else:
    print("  No new lessons to write")

# === STEP 6: SHIFT PROPOSAL ===
# Build set of lesson IDs already covered by active/proposed shifts
covered_lesson_ids = set()
all_shifts = load_jsonl(SHIFTS_FILE)
for s in all_shifts:
    if s.get("status") in ("active", "proposed"):
        for field in ["lesson_id", "lesson_ref", "source_lesson", "source_lesson_ids"]:
            val = s.get(field)
            if val:
                if isinstance(val, list):
                    covered_lesson_ids.update(val)
                elif isinstance(val, str):
                    covered_lesson_ids.add(val)

# Count active shifts
active_shifts = [s for s in all_shifts if s.get("status") == "active"]
proposed_shifts = [s for s in all_shifts if s.get("status") == "proposed"]
print(f"  Active shifts: {len(active_shifts)}, Proposed: {len(proposed_shifts)}, Cap: {ACTIVE_SHIFT_CAP}")

# Propose shifts for high-confidence lessons not already covered
new_proposals = []
all_lessons = load_jsonl(LESSONS_FILE)
for les in all_lessons:
    lid = get_lesson_id(les)
    if les.get("confidence") == "high" and lid and lid not in covered_lesson_ids:
        cg = get_lesson_causal_grounding(les)
        shift_text = f"Address {les.get('signal_type', 'unknown')} in {les.get('failure_phase', 'execution')} phase: {cg.get('why', les.get('lesson_text', ''))}"
        shift_id = f"shf_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"

        proposal = {
            "shift_id": shift_id,
            "status": "proposed",
            "lesson_id": lid,
            "signal_type": les.get("signal_type", ""),
            "failure_phase": les.get("failure_phase", "execution"),
            "domain": les.get("domains", ["general"])[0] if les.get("domains") else "general",
            "shift_text": shift_text[:500],
            "reinforced_count": 0,
            "created_at": now.isoformat()
        }
        new_proposals.append(proposal)

print(f"  New shift proposals: {len(new_proposals)}")

# === STEP 7: SHIFT ACTIVATION (merge-before-cap) ===
remaining_proposals = []
activated_count = 0
merged_count = 0

for proposal in new_proposals:
    # Check domain+phase overlap with active shifts
    overlap_found = False
    for active in active_shifts:
        active_domain = active.get("domain", "")
        active_phase = get_failure_phase(active)
        prop_domain = proposal.get("domain", "")
        prop_phase = proposal.get("failure_phase", "")

        if active_domain == prop_domain and active_phase == prop_phase:
            # Merge: reinforce active shift
            active["reinforced_count"] = active.get("reinforced_count", 0) + 1
            active["last_reinforced_at"] = now.isoformat()
            overlap_found = True
            merged_count += 1
            break

        # Text similarity check
        active_text = active.get("shift_text", "").lower()
        prop_text = proposal.get("shift_text", "").lower()
        if active_text and prop_text:
            # Simple overlap: shared keywords
            active_words = set(active_text.split())
            prop_words = set(prop_text.split())
            if len(active_words & prop_words) > min(len(active_words), len(prop_words)) * 0.5:
                active["reinforced_count"] = active.get("reinforced_count", 0) + 1
                active["last_reinforced_at"] = now.isoformat()
                overlap_found = True
                merged_count += 1
                break

    if not overlap_found:
        remaining_proposals.append(proposal)

print(f"  Merged: {merged_count}, Remaining proposals: {len(remaining_proposals)}")

# Activate remaining proposals if under cap
for proposal in remaining_proposals:
    if len(active_shifts) < ACTIVE_SHIFT_CAP:
        proposal["status"] = "active"
        proposal["activated_at"] = now.isoformat()
        active_shifts.append(proposal)
        activated_count += 1
    else:
        # At cap — leave as proposed
        pass

print(f"  Activated: {activated_count}, Still proposed: {len(remaining_proposals) - activated_count}")

# === STEP 8: REWRITE shifts.jsonl ===
all_shifts_final = []
# Add all non-active, non-proposed shifts (expired, rejected, etc.)
for s in all_shifts:
    if s.get("status") not in ("active", "proposed"):
        all_shifts_final.append(s)

# Add active shifts (with updated reinforcement counts)
active_ids = set()
for s in active_shifts:
    sid = get_shift_id(s)
    if sid not in active_ids:
        active_ids.add(sid)
        all_shifts_final.append(s)

# Add proposed shifts (old + new that weren't activated)
proposed_ids = set()
for s in all_shifts:
    if s.get("status") == "proposed":
        sid = get_shift_id(s)
        if sid not in proposed_ids:
            proposed_ids.add(sid)
            all_shifts_final.append(s)

# Add newly activated proposals
for p in remaining_proposals:
    sid = get_shift_id(p)
    if sid not in active_ids and sid not in proposed_ids:
        all_shifts_final.append(p)

with open(SHIFTS_FILE, 'w') as f:
    for s in all_shifts_final:
        f.write(json.dumps(s) + "\n")

final_active = len([s for s in all_shifts_final if s.get("status") == "active"])
final_proposed = len([s for s in all_shifts_final if s.get("status") == "proposed"])
print(f"  Shifts file rewritten: {len(all_shifts_final)} total ({final_active} active, {final_proposed} proposed)")

# === STEP 9: DECISION LOG ===
decision = {
    "decision_id": f"dec_{now.strftime('%Y%m%d%H%M%S')}",
    "timestamp": now.isoformat(),
    "run_id": run_id,
    "action": "journal_ingest",
    "summary": f"Ingest complete: {len(unevaluated)} journals scanned, {len(new_events)} events, {len(new_lessons_final)} lessons, {activated_count} shifts activated",
    "details": {
        "journals_scanned": len(unevaluated),
        "journals_with_signals": journals_with_signals,
        "journals_no_signal": journals_with_no_signal,
        "new_events": len(new_events),
        "new_lessons": len(new_lessons_final),
        "new_proposals": len(new_proposals),
        "merged": merged_count,
        "activated": activated_count,
        "active_shifts": final_active,
        "proposed_shifts": final_proposed
    }
}

with open(DECISIONS_FILE, 'a') as f:
    f.write(json.dumps(decision) + "\n")
print(f"  Decision logged")

# === STEP 10: PRAXIS JOURNAL ===
journal_entry = {
    "run_id": run_id,
    "timestamp": now.isoformat(),
    "type": "ingest",
    "decision": {
        "summary": decision["summary"],
        "execution_result": {"status": "ok"},
        "payload": {
            "entities_observed": [
                {"name": "journals_scanned", "value": len(unevaluated), "user_relevance": "system"},
                {"name": "new_events", "value": len(new_events), "user_relevance": "system"},
                {"name": "new_lessons", "value": len(new_lessons_final), "user_relevance": "system"},
                {"name": "shifts_activated", "value": activated_count, "user_relevance": "system"}
            ],
            "relationships_observed": [],
            "preferences_observed": []
        }
    },
    "actions_taken": [
        {"action": "scan_journals", "outcome": "completed"},
        {"action": "extract_signals", "outcome": "completed"},
        {"action": "record_events", "outcome": "completed"},
        {"action": "extract_lessons", "outcome": "completed"},
        {"action": "propose_shifts", "outcome": "completed"}
    ]
}

journal_path = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_path, exist_ok=True)
with open(os.path.join(journal_path, f"{run_id}.json"), 'w') as f:
    json.dump(journal_entry, f, indent=2)
print(f"  Journal written: {run_id}.json")

# === SUMMARY ===
print(f"\n{'='*60}")
print(f"PRAXIS INGEST COMPLETE — {now.isoformat()}")
print(f"{'='*60}")
print(f"  Journals scanned:     {len(unevaluated)}")
print(f"  With signals:         {journals_with_signals}")
print(f"  No signal:            {journals_with_no_signal}")
print(f"  New events:           {len(new_events)}")
print(f"  New lessons:          {len(new_lessons_final)}")
print(f"  Shift proposals:      {len(new_proposals)}")
print(f"  Merged (reinforced):  {merged_count}")
print(f"  Activated:            {activated_count}")
print(f"  Active shifts:        {final_active}/{ACTIVE_SHIFT_CAP}")
print(f"  Proposed shifts:      {final_proposed}")
print(f"  Total events:         {len(all_events)}")
print(f"  Total lessons:        {len(all_lessons)}")
print(f"{'='*60}")
