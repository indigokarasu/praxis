#!/usr/bin/env python3
"""
Praxis Journal Ingest Run — 2026-06-13 cron
Scans skill journals, extracts behavioral signals, records events,
extracts lessons, proposes shifts, writes journal.
"""

import os
import json
import time
from datetime import datetime, timezone, timedelta

# --- Path constants (absolute literals, not os.path.join) ---
DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
JOURNALS_DIR = "/root/.hermes/commons/journals"
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

# --- Suppress phrases for summary keyword filtering ---
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy"
]

# --- Normalization helpers ---
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

# --- Load existing data ---
def load_jsonl(path):
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
            except:
                pass
    return records

def append_jsonl(path, records):
    with open(path, "a") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")

def rewrite_jsonl(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")

# --- Main ---
now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
now_iso = now.isoformat()
run_id = f"r_{now.strftime('%Y%m%d_%H%%M%S')}_{os.urandom(4).hex()}"

print(f"[INGEST] Run {run_id}")
print(f"[INGEST] Time: {now_iso}")
print(f"[INGEST] Scanning journals for {today} and {yesterday}")

# STEP 1: Deduplicate journals_evaluated.jsonl
eval_entries = load_jsonl(EVAL_FILE)
print(f"\n[STEP 1] Loaded {len(eval_entries)} eval entries")

# Dedup by journal_id (keep first occurrence)
seen_ids = set()
deduped_eval = []
dup_count = 0
for e in eval_entries:
    jid = e.get("journal_id", "")
    if jid not in seen_ids:
        seen_ids.add(jid)
        deduped_eval.append(e)
    else:
        dup_count += 1

if dup_count > 0:
    rewrite_jsonl(EVAL_FILE, deduped_eval)
    print(f"  Deduped: removed {dup_count} duplicate entries")
else:
    print(f"  No duplicates found")

# Step 1b: Compact if >5000 entries
if len(deduped_eval) > 5000:
    cutoff = (now - timedelta(days=30)).isoformat()
    compacted = [e for e in deduped_eval
                 if e.get("evaluated_at", "9999") > cutoff
                 or not e.get("evaluated_at")]
    removed = len(deduped_eval) - len(compacted)
    if removed > 0:
        rewrite_jsonl(EVAL_FILE, compacted)
        deduped_eval = compacted
        seen_ids = {e.get("journal_id", "") for e in deduped_eval}
        print(f"  Compacted: removed {removed} entries older than 30 days")

print(f"  Final eval count: {len(deduped_eval)}")

# STEP 2: Scan filesystem for journal files
all_files = []
for root_dir, dirs, files in os.walk(JOURNALS_DIR):
    dirs[:] = [d for d in dirs if not d.startswith(".")]
    parts = root_dir.replace(JOURNALS_DIR, "").strip("/").split("/")
    if parts and parts[0] in SKIP_DIRS:
        continue
    for fname in files:
        if fname.endswith(".json"):
            full_path = os.path.join(root_dir, fname)
            rel_path = os.path.relpath(full_path, JOURNALS_DIR)
            path_parts = rel_path.split("/")
            if len(path_parts) >= 2:
                date_dir = path_parts[1] if len(path_parts) > 1 else ""
                if date_dir in (today, yesterday):
                    skill = path_parts[0]
                    canonical = f"{skill}/{date_dir}/{fname}"
                    all_files.append((canonical, full_path))

print(f"\n[STEP 2] Found {len(all_files)} journal files")

# STEP 3: Compute unevaluated set
unevaluated = [(c, p) for c, p in all_files if c not in seen_ids and os.path.exists(p)]
print(f"[STEP 3] Unevaluated: {len(unevaluated)}")

if not unevaluated:
    print("  No new journals to process.")
    print("  Continuing to lesson extraction against existing event backlog...")

# STEP 4: Signal extraction from unevaluated journals
new_events = []
eval_updates = []
new_event_signals = []  # track (journal_id, signals) for dedup collision detection

failure_keywords = ["failed", "failure", "error", "timeout", "broken", "crash",
                    "exception", "reject", "denied", "refused", "aborted"]

auth_keywords = ["oauth", "token", "401", "unauthorized", "auth_fail", "revoked",
                 "expired_token", "credentials"]

SUPPRESS_PHRASES_LOWER = [p.lower() for p in SUPPRESS_PHRASES]

def should_suppress_summary_signals(summary_str, signals):
    """Return True if summary-derived signals should be suppressed."""
    SUMMARY_DERIVED_TYPES = {"failure_keyword", "auth_failure"}
    non_summary_signals = [s for s in signals if s["type"] not in SUMMARY_DERIVED_TYPES]
    if non_summary_signals:
        return False
    summary_lower = summary_str.lower()
    for phrase in SUPPRESS_PHRASES_LOWER:
        if phrase in summary_lower:
            return True
    return False

def extract_signals(canonical, data, skill_name):
    """Extract behavioral signals from a journal entry. Returns list of signal dicts."""
    signals = []
    summary = ""
    status = ""

    # Handle list-format journals
    if isinstance(data, list):
        signals.append({"type": "list_format", "phase": "execution"})
        return signals, summary, status

    # Get status from various locations
    status = data.get("status", "")
    if not status and "decision" in data:
        decision = data["decision"]
        if isinstance(decision, dict):
            status = decision.get("execution_result", {}).get("status", "")
            if not status:
                status = decision.get("status", "")

    # Get summary
    summary = data.get("summary", "")
    if not summary and "decision" in data:
        decision = data["decision"]
        if isinstance(decision, dict):
            summary = decision.get("summary", "")

    # Summary might be a dict
    summary_str = ""
    if isinstance(summary, str):
        summary_str = summary
    elif isinstance(summary, dict):
        summary_str = json.dumps(summary)

    # Check top-level escalation_needed
    if data.get("escalation_needed") is True:
        signals.append({"type": "escalation", "phase": "execution"})

    # Check status for failure
    failure_statuses = {"error", "partial", "completed_with_errors", "scope_failure", "auth_failure"}
    if status in failure_statuses:
        signals.append({"type": "execution_error", "phase": "execution"})

    # Check for observation type with all skips
    journal_type = data.get("type", "")
    if journal_type == "Observation":
        # Spot observation journals - check if all results are skipped
        results = data.get("results", [])
        all_skipped = False
        if results:
            skipped_statuses = {"skipped", "skipped_inactive", "skipped_unautomated", "expired", "permanently broken", "dead watch"}
            skipped_count = sum(1 for r in results if isinstance(r, dict) and 
                              any(s in r.get("status", "").lower() for s in skipped_statuses))
            if skipped_count == len(results) and len(results) > 0:
                # All skipped — no failure signal
                signals = [s for s in signals if s["type"] != "execution_error"]
                # Add observation signal
                if not signals:
                    signals.append({"type": "all_skipped_observation", "phase": "execution"})
                return signals, summary_str, status
        # Observation with no real results
        if not signals:
            signals.append({"type": "observation", "phase": "execution"})
        return signals, summary_str, status

    # Check actions_taken
    actions = data.get("actions_taken", [])
    if isinstance(actions, list):
        for action in actions:
            if isinstance(action, dict):
                outcome = action.get("outcome", "")
                if isinstance(outcome, str) and outcome.lower() in ("error", "failure", "failed"):
                    signals.append({"type": "execution_error", "phase": "execution"})

    # Check nested findings arrays
    findings = data.get("findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict):
                if finding.get("escalation_needed") is True:
                    signals.append({"type": "escalation", "phase": "execision"})
                f_status = finding.get("status", "")
                if f_status in ("error", "failed"):
                    signals.append({"type": "execution_error", "phase": "execution"})
                f_detail = finding.get("detail", "")
                if isinstance(f_detail, str):
                    for kw in failure_keywords:
                        if kw in f_detail.lower():
                            signals.append({"type": "failure_keyword", "phase": "execution"})
                            break

    # Check signals.* (finch scan journals)
    top_signals = data.get("signals", {})
    if isinstance(top_signals, dict):
        for src_name, src_data in top_signals.items():
            if isinstance(src_data, dict):
                # Check new_errors
                new_errors = src_data.get("new_errors", [])
                if isinstance(new_errors, list) and new_errors:
                    signals.append({"type": "cron_errors", "phase": "execution"})
                # Check error breakdown
                error_bd = src_data.get("error_breakdown", {})
                if isinstance(error_bd, dict):
                    for k, v in error_bd.items():
                        if isinstance(v, int) and v > 0:
                            signals.append({"type": "cron_errors", "phase": "execution"})
                            break
                # Check notes
                notes = src_data.get("notes", "")
                if isinstance(notes, str):
                    for kw in failure_keywords:
                        if kw in notes.lower():
                            signals.append({"type": "failure_keyword", "phase": "execution"})
                            break

    # Check tasks_added (finch)
    tasks_added = data.get("tasks_added", [])
    if isinstance(tasks_added, list):
        for task in tasks_added:
            if isinstance(task, str):
                task_lower = task.lower()
                if "error" in task_lower or "fail" in task_lower:
                    signals.append({"type": "failure_keyword", "phase": "execution"})

    # Check top-level summary string for keywords (only if status is not ok)
    ok_statuses = {"ok", "success", "complete", "completed"}
    if summary_str and status not in ok_statuses:
        summary_lower = summary_str.lower()
        # Only keyword-match if status indicates something went wrong
        if status in failure_statuses or not status:
            for kw in failure_keywords:
                if kw in summary_lower:
                    signals.append({"type": "failure_keyword", "phase": "execution"})
                    break
            for kw in auth_keywords:
                if kw in summary_lower:
                    signals.append({"type": "auth_failure", "phase": "execution"})
                    break

    # Apply suppress filter for summary-derived signals only
    if summary_str and signals:
        if isinstance(summary_str, str) and should_suppress_summary_signals(summary_str, signals):
            # Remove summary-derived signals
            signals = [s for s in signals if s["type"] not in ("failure_keyword", "auth_failure")]

    # Deduplicate signal types
    seen_types = set()
    unique_signals = []
    for s in signals:
        if s["type"] not in seen_types:
            seen_types.add(s["type"])
            unique_signals.append(s)

    return unique_signals, summary_str, status

# Process each unevaluated journal
print(f"\n[STEP 4] Processing {len(unevaluated)} unevaluated journals...")

for canonical, full_path in unevaluated:
    skill_name = canonical.split("/")[0]
    print(f"\n  Processing: {canonical}")

    try:
        with open(full_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"    ERROR loading: {e}")
        # Mark as evaluated with error
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now_iso,
            "action_taken": "load_error",
            "signals_found": [],
            "reason": f"Failed to load: {e}"
        })
        continue

    # Determine result status for forge/spot handling
    result_status = data.get("result", data.get("status", ""))
    decision_type = ""
    if isinstance(data.get("decision"), dict):
        decision_type = data.get("decision", {}).get("decision_type", "")

    # Forge no-op handler
    if skill_name == "ocas-forge":
        if result_status == "no_op" or (not data.get("result") and not data.get("status")):
            print(f"    Forge no-op (result={result_status}, decision_type={decision_type})")
            eval_updates.append({
                "journal_id": canonical,
                "evaluated_at": now_iso,
                "action_taken": "no_signal",
                "signals_found": [],
                "reason": "Forge routine no-op scan"
            })
            continue

    # Spot observation handler
    if skill_name == "ocas-spot" and data.get("type", "") == "observation":
        skip_signals = False
        summary_val = data.get("summary", {})
        if isinstance(summary_val, dict):
            summary_text = json.dumps(summary_val)
        else:
            summary_text = str(summary_val)

        for phrase in ["skipped", "permanently broken", "dead watch", "expired",
                       "no new availability", "skipped_inactive", "skipped_unautomated"]:
            if phrase.lower() in summary_text.lower():
                skip_signals = True
                break

        if skip_signals:
            print(f"    Spot observation no-op (all skipped/expired)")
            eval_updates.append({
                "journal_id": canonical,
                "evaluated_at": now_iso,
                "action_taken": "no_signal",
                "signals_found": [],
                "reason": "Spot observation: all watches skipped/expired"
            })
            continue

    # Extract signals
    signals, summary_str, status = extract_signals(canonical, data, skill_name)
    signal_types = [s["type"] for s in signals]

    if not signals:
        print(f"    No signals after filtering")
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now_iso,
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })
        continue

    print(f"    Signals found: {signal_types}")

    # Check for repeated_skip pattern (spot journals with all skipped results)
    if skill_name == "ocas-spot" and data.get("results"):
        results = data.get("results", [])
        skipped_count = 0
        if isinstance(results, list):
            for r in results:
                if isinstance(r, dict):
                    r_status = r.get("status", "").lower()
                    if any(s in r_status for s in ["skipped", "expired", "broken"]):
                        skipped_count += 1
            if skipped_count > 0 and len(results) > 0:
                signals.append({"type": "repeated_skip", "phase": "execution"})

    # Record events for each signal
    raw_signal_count = len(signals)
    journal_events = []
    for sig in signals:
        event_id = f"evt_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
        failure_phase = sig.get("phase", "execution")

        # Determine domain: use skill_name as domain for unknown
        domain = data.get("domain", skill_name)

        event = {
            "event_id": event_id,
            "source_journal": canonical,
            "signal_type": sig["type"],
            "failure_phase": failure_phase,
            "domain": domain,
            "recorded_at": now_iso,
            "skill": skill_name,
            "summary_excerpt": (summary_str[:200] if isinstance(summary_str, str) else "") if summary_str else "",
            "status_at_extraction": status
        }
        journal_events.append(event)
        new_events.append(event)

    new_event_signals.append((canonical, len(signals), len(journal_events)))

print(f"\n  Extracted {len(new_events)} new event(s) from {len(unevaluated)} journal(s)")

# STEP 4b: Write events to disk
truly_new = []
if new_events:
    # Load existing events for dedup check
    existing_events = load_jsonl(EVENTS_FILE)
    existing_keys = set()
    for e in existing_events:
        e_src = e.get("source_journal", "")
        e_st = e.get("signal_type", "")
        existing_keys.add((e_src, e_st))

    for evt in new_events:
        key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
        if key not in existing_keys:
            existing_keys.add(key)
            truly_new.append(evt)

    if truly_new:
        append_jsonl(EVENTS_FILE, truly_new)
        print(f"  Wrote {len(truly_new)} new events ({len(new_events) - len(new_events) + len(truly_new)} dedup)")

# STEP 4c: Write eval updates
if eval_updates:
    append_jsonl(EVAL_FILE, eval_updates)
    print(f"  Wrote {len(eval_updates)} eval updates")

# STEP 5: Post-write dedup of events.jsonl
all_events = load_jsonl(EVENTS_FILE)
deduped_events = {}
if all_events:
    # Dedup by (source_journal, signal_type), keep earliest recorded_at
    deduped_events = {}
    for evt in all_events:
        key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
        if key not in deduped_events:
            deduped_events[key] = evt
        else:
            # Keep earliest
            existing_time = deduped_events[key].get("recorded_at", "9999")
            new_time = evt.get("recorded_at", "9999")
            if new_time < existing_time:
                deduped_events[key] = evt

    if len(deduped_events) != len(all_events):
        rewrite_jsonl(EVENTS_FILE, list(deduped_events.values()))
        print(f"  Post-write dedup: {len(all_events)} -> {len(deduped_events)} events")

total_events = len(deduped_events) if deduped_events else 0
print(f"\n[STEP 5] Total events in backlog: {total_events}")

# STEP 6: Lesson extraction (two-pass)
print(f"\n[STEP 6] Lesson extraction (two-pass)")

# Re-read events from disk
all_events = load_jsonl(EVENTS_FILE)

# Load existing lessons
existing_lessons = load_jsonl(LESSONS_FILE)
existing_lesson_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_lesson_groups.add(key)

# Filter to meaningful events (skip unknown/None/empty signal_types)
MEANINGFUL_SIGNALS = {
    "execution_error", "escalation", "failure_keyword", "auth_failure",
    "cron_errors", "repeated_skip", "persistent_platform_failure",
    "list_format", "correction", "update_completed"
}
meaningful_events = [e for e in all_events
                     if e.get("signal_type", "") in MEANINGFUL_SIGNALS
                     and e.get("signal_type", "") not in ("unknown", "?", None, "")]

print(f"  Meaningful events: {len(meaningful_events)}")

# Group by (signal_type, failure_phase)
groups = {}
for e in meaningful_events:
    key = (e.get("signal_type", ""), e.get("failure_phase", ""))
    if key not in groups:
        groups[key] = []
    groups[key].append(e)

print(f"  Groups: {len(groups)}")
for key, evts in groups.items():
    print(f"    {key}: {len(evts)} events")

# Filter to groups with 2+ events
pattern_groups = {k: v for k, v in groups.items() if len(v) >= 2}
print(f"  Pattern groups (2+ events): {len(pattern_groups)}")

# Check which pattern groups don't have lessons yet
new_pattern_groups = {}
for key, evts in pattern_groups.items():
    if key not in existing_lesson_groups:
        new_pattern_groups[key] = evts
        print(f"    NEW pattern group: {key} ({len(evts)} events)")
    else:
        print(f"    Already has lesson: {key}")

new_lessons = []
if new_pattern_groups:
    # Pass 1: Create lesson stubs
    print(f"\n  Pass 1: Creating lesson stubs for {len(new_pattern_groups)} groups")
    lesson_stubs = []
    for (sig_type, phase), evts in new_pattern_groups.items():
        lesson_id = f"les_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
        domains = list(set(get_event_domain(e) for e in evts))
        domains = [d for d in domains if d and d != "unknown"]
        primary_domain = domains[0] if domains else evts[0].get("skill", "unknown")

        stub = {
            "lesson_id": lesson_id,
            "signal_type": sig_type,
            "failure_phase": phase,
            "confidence": "low",
            "event_count": len(evts),
            "domains_affected": domains if domains else [primary_domain],
            "skills_affected": list(set(e.get("skill", "") for e in evts if e.get("skill"))),
            "lesson_text": "",
            "created_at": now_iso,
            "source_events": [get_event_id(e) for e in evts]
        }
        lesson_stubs.append(stub)

    # Pass 2: Causal grounding upgrade
    print(f"  Pass 2: Adding causal grounding to {len(lesson_stubs)} lessons")
    for stub in lesson_stubs:
        sig_type = stub["signal_type"]
        phase = stub["failure_phase"]
        count = stub["event_count"]
        domains = stub["skills_affected"] if stub["skills_affected"] else stub["domains_affected"]
        domain_str = ", ".join(domains[:3])

        what = f"{count} events of type '{sig_type}' in {phase} phase across {domain_str}"
        why = f"Repeated pattern: {sig_type} consistently occurs during {phase} in {domain_str}"
        when = f"When {domain_str} tasks enter {phase} phase with {sig_type} conditions"

        stub["lesson_text"] = f"[LESSON] What: {what}. Why: {why}. When: {when}"
        stub["confidence"] = "high"
        stub["causal_grounding"] = {
            "what": what,
            "why": why,
            "when": when
        }
        new_lessons.append(stub)
        existing_lesson_groups.add((sig_type, phase))

    # Write new lessons
    if new_lessons:
        append_jsonl(LESSONS_FILE, new_lessons)
        print(f"  Wrote {len(new_lessons)} new lessons with causal grounding")

all_lessons = load_jsonl(LESSONS_FILE)
high_conf_lessons = [l for l in all_lessons if l.get("confidence") == "high"]
print(f"  Total lessons: {len(all_lessons)}, high confidence: {len(high_conf_lessons)}")

# STEP 7: Shift proposal and activation
print(f"\n[STEP 7] Shift proposal and activation")

all_shifts = load_jsonl(SHIFTS_FILE)
active_shifts = [s for s in all_shifts if s.get("status") == "active"]
proposed_shifts = [s for s in all_shifts if s.get("status") == "proposed"]

print(f"  Active shifts: {len(active_shifts)}/{ACTIVE_SHIFT_CAP}")
print(f"  Proposed shifts: {len(proposed_shifts)}")

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

# Find high-confidence lessons not already covered by shifts
remaining_proposals = []
for lesson in high_conf_lessons:
    lid = get_lesson_id(lesson)
    if lid and lid not in covered_lesson_ids:
        remaining_proposals.append(lesson)

print(f"  Lessons not covered by shifts: {len(remaining_proposals)}")

new_proposals = []
newly_activated = []
reinforced = []

for lesson in remaining_proposals:
    lid = get_lesson_id(lesson)
    sig_type = lesson.get("signal_type", "")
    phase = lesson.get("failure_phase", "execution")
    domain = lesson.get("skills_affected", [lesson.get("domains_affected", ["general"])[0]]) if lesson.get("skills_affected") else (lesson.get("domains_affected", ["general"]) if lesson.get("domains_affected") else ["general"])
    primary_domain = domain[0] if isinstance(domain, list) and domain else domain

    # Build shift text
    lesson_text = lesson.get("lesson_text", "")
    shift_text = f"When {sig_type} occurs in {phase} phase ({primary_domain}), apply lesson: {lesson_text[:200]}"

    # Check for domain+phase overlap with active shifts
    overlap_found = False
    for active in active_shifts:
        a_domain = active.get("domain", "")
        a_phase = get_failure_phase(active)
        a_shift_text = active.get("shift_text", "")

        if a_domain == primary_domain and a_phase == phase and sig_type in a_shift_text:
            # Reinforce existing shift instead of proposing new one
            active["reinforcement_count"] = active.get("reinforcement_count", 0) + 1
            active["last_reinforced_at"] = now_iso
            reinforced.append(active["shift_id"])
            overlap_found = True
            print(f"    Reinforced active shift: {get_shift_id(active)} ({a_domain}/{a_phase})")
            break

    if not overlap_found:
        # Propose new shift
        shift_id = f"shf_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
        proposal = {
            "shift_id": shift_id,
            "status": "proposed",
            "lesson_id": lid,
            "source_lesson": lid,
            "domain": primary_domain,
            "failure_phase": phase,
            "shift_text": shift_text,
            "created_at": now_iso,
            "reinforcement_count": 0
        }
        new_proposals.append(proposal)
        print(f"    Proposed shift: {shift_id} ({primary_domain}/{phase})")

# Check cap and activate if possible
remaining_proposals_list =	list(new_proposals)  # copy

active_count = len(active_shifts)
available_slots = ACTIVE_SHIFT_CAP - active_count

if remaining_proposals_list and available_slots > 0:
    to_activate = remaining_proposals_list[:available_slots]
    for prop in to_activate:
        prop["status"] = "active"
        prop["activated_at"] = now_iso
        newly_activated.append(prop["shift_id"])
        print(f"    Activated: {prop['shift_id']} ({prop['domain']}/{prop['failure_phase']})")

    remaining = remaining_proposals_list[available_slots:]
    if remaining:
        print(f"    Left as proposed (at cap): {len(remaining)}")

# Write shifts back (rewrite entire file)
all_active = {get_shift_id(s): s for s in active_shifts}
all_proposed = {get_shift_id(s): s for s in all_shifts if s.get("status") == "proposed"}

# Merge newly activated into active set
for prop in new_proposals:
    sid = get_shift_id(prop)
    if prop["status"] == "active":
        all_active[sid] = prop
    else:
        all_proposed[sid] = prop

# Reinforce active shifts
for r in reinforced:
    if r in all_active:
        pass  # already updated

combined_shifts = list(all_active.values()) + list(all_proposed.values())
# Also keep expired/rejected shifts
other_shifts = [s for s in all_shifts if s.get("status") in ("expired", "rejected")]
all_shift_ids = {get_shift_id(s) for s in combined_shifts}
for s in other_shifts:
    if get_shift_id(s) not in all_shift_ids:
        combined_shifts.append(s)

rewrite_jsonl(SHIFTS_FILE, combined_shifts)

print(f"\n  Shift summary:")
print(f"    Active: {len(all_active)}/{ACTIVE_SHIFT_CAP}")
print(f"    Proposed: {len(all_proposed)}")
print(f"    Newly activated: {len(newly_activated)}")
print(f"    Reinforced: {len(reinforced)}")
print(f"    Total shifts: {len(combined_shifts)}")

# STEP 8: Write decisions log
decision_entry = {
    "decision_id": f"dec_{now.strftime('%Y%m%d_%H%M%S')}",
    "timestamp": now_iso,
    "decision_type": "journal_ingest",
    "journals_scanned": len(all_files),
    "unevaluated": len(unevaluated),
    "evaluated_ok": len([e for e in eval_updates if e.get("action_taken") == "no_signal"]),
    "events_extracted": len(truly_new),
    "lessons_extracted": len(new_lessons),
    "shifts_proposed": len(new_proposals),
    "shifts_activated": len(newly_activated),
    "shifts_reinforced": len(reinforced),
    "active_shift_count": len(all_active),
    "total_events": len(all_events),
    "total_lessons": len(all_lessons),
    "notes": f"Ingest run {run_id}"
}
append_jsonl(DECISIONS_FILE, [decision_entry])

# STEP 9: Write Praxis journal entry
journal_today_dir = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_today_dir, exist_ok=True)

journal_entry = {
    "run_identity": {
        "run_id": run_id,
        "skill_name": "ocas-praxis",
        "skill_version": "3.2.0",
        "timestamp_start": now_iso,
        "timestamp_end": datetime.now(timezone.utc).isoformat(),
        "journal_type": "action",
        "journal_spec_version": "1.3"
    },
    "runtime": {
        "model": "openrouter/owl-alpha",
        "provider": "openrouter"
    },
    "input": {
        "command": "praxis:journal_ingest",
        "mode": "cron"
    },
    "decision": {
        "execution_result": {
            "status": "ok"
        },
        "summary": {
            "journals_scanned": len(all_files),
            "unevaluated": len(unevaluated),
            "evaluated_ok": len([e for e in eval_updates if e.get("action_taken") == "no_signal"]),
            "events_extracted": len(truly_new),
            "lessons_extracted": len(new_lessons),
            "shifts_proposed": len(new_proposals),
            "shifts_activated": len(newly_activated),
            "shifts_reinforced": len(reinforced),
            "active_shift_count": len(all_active),
            "total_events": len(all_events),
            "total_lessons": len(all_lessons),
            "cap_usage": f"{len(all_active)}/{ACTIVE_SHIFT_CAP}"
        }
    },
    "actions_taken": [
        {"action": "scan_journals", "outcome": "completed", "count": len(all_files)},
        {"action": "extract_signals", "outcome": "completed", "count": len(unevaluated)},
        {"action": "record_events", "outcome": "completed" if truly_new else "no_new"},
        {"action": "extract_lessons", "outcome": "completed", "count": len(new_lessons)},
        {"action": "propose_shifts", "outcome": "completed", "count": len(new_proposals)},
    ],
    "entities_observed": [
        {"name": skill, "type": "skill", "user_relevance": "system"}
        for skill in set(e.get("skill", "") for e in all_events if e.get("skill"))
    ]
}

journal_path = os.path.join(journal_today_dir, f"{run_id}.json")
with open(journal_path, "w") as f:
    json.dump(journal_entry, f, indent=2, default=str)

# STEP 10: Write evidence record
evidence_entry = {
    "run_id": run_id,
    "timestamp": now_iso,
    "evidence_type": "ingest_run",
    "journals_scanned": len(all_files),
    "unevaluated_found": len(unevaluated),
    "events_recorded": len(truly_new),
    "lessons_extracted": len(new_lessons),
    "shifts_activated": len(newly_activated),
    "active_shifts": len(all_active),
    "cap_usage": f"{len(all_active)}/{ACTIVE_SHIFT_CAP}",
    "not_activity_reason": None
}
append_jsonl(EVIDENCE_FILE, [evidence_entry])

print(f"\n[COMPLETE] Ingest run {run_id} finished")
print(f"  Journals scanned: {len(all_files)}")
print(f"  Unevaluated: {len(unevaluated)}")
print(f"  New events: {len(truly_new)}")
print(f"  New lessons: {len(new_lessons)}")
print(f"  Shifts proposed: {len(new_proposals)}")
print(f"  Shifts activated: {len(newly_activated)}")
print(f"  Shifts reinforced: {len(reinforced)}")
print(f"  Active shifts: {len(all_active)}/{ACTIVE_SHIFT_CAP}")
print(f"  Total events: {len(all_events)}")
print(f"  Total lessons: {len(all_lessons)}")
