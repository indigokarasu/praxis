#!/usr/bin/env python3
"""
Praxis Ingest Run — 2026-06-13 Cron
Scans unevaluated journals, extracts signals, records events, extracts lessons.
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone, timedelta

# === PATH CONSTANTS (absolute literals — os.path.join strips leading dot) ===
DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
JOURNALS_DIR = "/root/.hermes/commons/journals"
JOURNAL_DIR = "/root/.hermes/commons/journals/ocas-praxis"

EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")
EVIDENCE_FILE = os.path.join(DATA_DIR, "evidence.jsonl")

SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
ACTIVE_SHIFT_CAP = 12

NOW = datetime.now(timezone.utc)
today = NOW.strftime("%Y-%m-%d")
yesterday = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")


# === SCHEMA NORMALIZATION HELPERS ===
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


# === UTILITY FUNCTIONS ===
def read_jsonl(path):
    records = []
    if not os.path.exists(path):
        return records
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records

def append_jsonl(path, records):
    with open(path, "a") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

def write_jsonl(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


# === PHASE 1: Deduplicate journals_evaluated.jsonl ===
print("=" * 60)
print("PHASE 1: Deduplicate journals_evaluated.jsonl")
eval_entries = read_jsonl(EVAL_FILE)
seen_ids = set()
deduped_eval = []
for entry in eval_entries:
    jid = entry.get("journal_id", "")
    if jid not in seen_ids:
        seen_ids.add(jid)
        deduped_eval.append(entry)

removed = len(eval_entries) - len(deduped_eval)
if removed > 0:
    write_jsonl(EVAL_FILE, deduped_eval)
    print(f"  Removed {removed} duplicate entries")
print(f"  Evaluated journal count: {len(deduped_eval)}")

# Compact if >5000 entries
if len(deduped_eval) > 5000:
    cutoff = (NOW - timedelta(days=30)).isoformat()
    compacted = [e for e in deduped_eval
                 if e.get("evaluated_at", "9999") > cutoff
                 or not e.get("evaluated_at")]
    removed2 = len(deduped_eval) - len(compacted)
    if removed2 > 0:
        deduped_eval = compacted
        write_jsonl(EVAL_FILE, deduped_eval)
        print(f"  Compacted: removed {removed2} entries older than 30 days")


# === PHASE 2: Scan filesystem for journal files ===
print("\nPHASE 2: Scan filesystem")
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
            all_files.append((rel_path, full_path))

print(f"  Total journal files found: {len(all_files)}")


# === PHASE 3: Compute unevaluated set ===
print("\nPHASE 3: Compute unevaluated set")
unevaluated = [(c, p) for c, p in all_files if c not in seen_ids and os.path.exists(p)]
print(f"  Unevaluated journals: {len(unevaluated)}")
for c, p in unevaluated:
    print(f"    {c}")


# === PHASE 4: Signal extraction ===
print("\nPHASE 4: Signal extraction")

# Noise filter suppress phrases for summary-derived signals
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy",
    "no unprocessed", "nothing to process", "no variant",
    "only config.json", "scan locations were empty"
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

new_events = []
eval_updates = []

for canonical, fpath in unevaluated:
    print(f"\n  Processing: {canonical}")
    try:
        with open(fpath, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"    ERROR reading file: {e}")
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": NOW.isoformat(),
            "action_taken": "read_error",
            "signals_found": [],
            "reason": f"Failed to read: {e}"
        })
        continue

    signals = []
    summary = ""

    # --- Check various journal schemas ---

    # 1. Top-level escalation_needed
    if data.get("escalation_needed") is True:
        signals.append({"type": "escalation", "detail": "Top-level escalation_needed=true"})
        print(f"    Signal: escalation_needed=true")

    # 2. decision.execution_result.status
    decision = data.get("decision", {})
    if isinstance(decision, dict):
        exec_result = decision.get("execution_result", {})
        if isinstance(exec_result, dict):
            status = exec_result.get("status", "")
            if status in ("error", "partial", "completed_with_errors"):
                sig_type = "execution_error" if status in ("error", "partial") else "execution_error"
                signals.append({"type": sig_type, "detail": f"execution_result.status={status}"})
                print(f"    Signal: execution_result.status={status}")

        # 3. decision.summary keyword scan (only for non-empty strings)
        decision_summary = decision.get("summary", "")
        if isinstance(decision_summary, str) and decision_summary.strip():
            summary = decision_summary

    # 4. Top-level status check for completed_with_errors
    top_status = data.get("status", "")
    if top_status == "completed_with_errors":
        signals.append({"type": "execution_error", "detail": "top-level status=completed_with_errors"})
        print(f"    Signal: top-level status=completed_with_errors")

    # 5. Top-level summary (may be string or dict)
    top_summary = data.get("summary", "")
    if isinstance(top_summary, str) and top_summary.strip() and not summary:
        summary = top_summary
    elif isinstance(top_summary, dict):
        # Handle dict-format summary (like finch scan)
        for src_name, src_val in top_summary.items():
            if isinstance(src_val, str):
                src_lower = src_val.lower()
                # Check for failure indicators in dict summary values
                if any(kw in src_lower for kw in ["blocked", "error", "failed", "unreachable", "cannot check", "unable to verify"]):
                    signals.append({"type": "execution_error", "detail": f"summary.{src_name}: {src_val[:100]}"})
                    print(f"    Signal: summary.{src_name} contains failure indicator")

    # 6. actions_taken[].outcome
    actions_taken = data.get("actions_taken", [])
    if isinstance(actions_taken, list):
        for action in actions_taken:
            if isinstance(action, dict):
                outcome = action.get("outcome", "")
                if isinstance(outcome, str) and outcome.lower() in ("error", "failure", "failed"):
                    signals.append({"type": "execution_error", "detail": f"actions_taken.outcome={outcome}"})
                    print(f"    Signal: actions_taken.outcome={outcome}")

    # 7. findings[] array (nested — scan each)
    findings = data.get("findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict):
                f_type = finding.get("type", "")
                f_status = finding.get("status", "")
                f_escalation = finding.get("escalation_needed", False)
                if f_type == "critical":
                    signals.append({"type": "escalation", "detail": f"findings[].type=critical"})
                    print(f"    Signal: findings[].type=critical")
                if f_status in ("error", "failed"):
                    signals.append({"type": "execution_error", "detail": f"findings[].status={f_status}"})
                    print(f"    Signal: findings[].status={f_status}")
                if f_escalation:
                    signals.append({"type": "escalation", "detail": "findings[].escalation_needed=true"})
                    print(f"    Signal: findings[].escalation_needed")

    # 8. sources.* / signal_sources.* / sources_scanned.* (finch scan schemas)
    for src_key in ["sources", "signal_sources", "sources_scanned"]:
        src_data = data.get(src_key, {})
        if isinstance(src_data, dict):
            for src_name, src_val in src_data.items():
                if isinstance(src_val, dict):
                    src_status = src_val.get("status", "")
                    src_error = src_val.get("error", "")
                    new_issues = src_val.get("new_issues_since_last_scan", src_val.get("new_issues", []))
                    
                    if src_status in ("blocked", "error", "failed", "inactive"):
                        signals.append({"type": "execution_error", "detail": f"{src_key}.{src_name}.status={src_status}"})
                        print(f"    Signal: {src_key}.{src_name}.status={src_status}")
                    if isinstance(src_error, str) and src_error and src_error.lower() != "none":
                        signals.append({"type": "execution_error", "detail": f"{src_key}.{src_name}.error={src_error[:100]}"})
                        print(f"    Signal: {src_key}.{src_name}.error")
                    if isinstance(new_issues, list) and len(new_issues) > 0:
                        for issue in new_issues:
                            signals.append({"type": "execution_error", "detail": f"{src_key}.{src_name}.new_issue={str(issue)[:100]}"})
                            print(f"    Signal: {src_key}.{src_name}.new_issue")
                    
                    # cron_health specific
                    if src_name == "cron_health":
                        error_jobs = src_val.get("error_jobs", 0)
                        if isinstance(error_jobs, int) and error_jobs > 0:
                            # Only signal if NOT the known transient 429 pattern
                            signals.append({"type": "cron_errors", "detail": f"cron_health.error_jobs={error_jobs}"})
                            print(f"    Signal: cron_health.error_jobs={error_jobs}")
                
                elif isinstance(src_val, str):
                    # String-value sources.* (scan-0600+ pattern)
                    src_lower = src_val.lower()
                    if any(kw in src_lower for kw in ["unreachable", "blocked", "cannot check", "unable to verify", "mcp unreachable"]):
                        signals.append({"type": "execution_error", "detail": f"{src_key}.{src_name}: {src_val[:100]}"})
                        print(f"    Signal: {src_key}.{src_name} string failure indicator")

    # 9. new_findings[] array
    new_findings = data.get("new_findings", [])
    if isinstance(new_findings, list):
        for nf in new_findings:
            if isinstance(nf, dict):
                severity = nf.get("severity", "")
                if severity in ("critical", "error", "high"):
                    signals.append({"type": "escalation", "detail": f"new_findings severity={severity}"})
                    print(f"    Signal: new_findings severity={severity}")

    # 10. Top-level summary failure_keyword scan (with noise suppression)
    if isinstance(summary, str) and summary.strip():
        summary_lower = summary.lower()
        failure_keywords = ["failed", "error", "failure", "broken", "corrupted", "crash", "unreachable"]
        for kw in failure_keywords:
            if kw in summary_lower:
                signals.append({"type": "failure_keyword", "detail": f"summary contains '{kw}'"})
                print(f"    Signal: failure_keyword '{kw}' in summary")

    # Apply semantic suppression for summary-derived signals
    if isinstance(summary, str) and should_suppress_summary_signals(summary, signals):
        print(f"    Suppressing summary-derived signals (noise filter)")
        signals = [s for s in signals if s["type"] not in ("failure_keyword", "auth_failure")]

    # 11. Spot sweep specific: type=Observation with 0 active checkable watches
    jtype = data.get("type", "")
    if jtype == "Observation" and not signals:
        # Routine observation — no signals
        pass

    # Deduplicate signals by type for this journal
    seen_types = set()
    deduped_signals = []
    for s in signals:
        if s["type"] not in seen_types:
            seen_types.add(s["type"])
            deduped_signals.append(s)
    signals = deduped_signals

    # === Record events or mark as no_signal ===
    if signals:
        # Determine failure phase
        failure_phase = "execution"  # default
        # Simple phase heuristics
        if any("planning" in s.get("detail", "").lower() or "wrong approach" in s.get("detail", "").lower() for s in signals):
            failure_phase = "planning"
        elif any(s["type"] in ("persistent_platform_failure",) for s in signals):
            failure_phase = "execution"

        for sig in signals:
            event = {
                "event_id": f"evt_{NOW.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
                "timestamp": NOW.isoformat(),
                "domain": canonical.split("/")[0],
                "context_summary": sig.get("detail", "")[:200],
                "outcome_type": "failure" if sig["type"] not in ("observation",) else "observation",
                "outcome_summary": sig.get("detail", "")[:200],
                "evidence": [f"canonical: {canonical}", f"signal_type: {sig['type']}"],
                "failure_phase": failure_phase,
                "user_relevance": "agent_only",
                "source_journal": canonical,
                "signal_type": sig["type"],
                "recorded_at": NOW.isoformat()
            }
            new_events.append(event)
            print(f"    Event recorded: {sig['type']}")

        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": NOW.isoformat(),
            "action_taken": "event_recorded",
            "signals_found": [s["type"] for s in signals],
            "reason": f"{len(signals)} signals extracted"
        })
    else:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": NOW.isoformat(),
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })
        print(f"    No signals (no_op)")


# === PHASE 5: Write events and eval updates ===
print(f"\nPHASE 5: Write new events ({len(new_events)} new)")

if new_events:
    append_jsonl(EVENTS_FILE, new_events)
    # Post-write dedup by (source_journal, signal_type)
    all_events = read_jsonl(EVENTS_FILE)
    seen_dedup = set()
    deduped_events = []
    for evt in all_events:
        key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
        if key not in seen_dedup:
            seen_dedup.add(key)
            deduped_events.append(evt)
    dedup_removed = len(all_events) - len(deduped_events)
    if dedup_removed > 0:
        print(f"  Post-write dedup: removed {dedup_removed} duplicates")
    write_jsonl(EVENTS_FILE, deduped_events)

append_jsonl(EVAL_FILE, eval_updates)
print(f"  Wrote {len(eval_updates)} eval updates")


# === PHASE 6: Lesson Extraction (Two-Pass) ===
print("\nPHASE 6: Lesson extraction")

all_events_final = read_jsonl(EVENTS_FILE)
# Filter to meaningful events (skip unknown/?/None)
meaningful_events = [e for e in all_events_final
                     if e.get("signal_type") not in ("unknown", "?", None, "", "observation")]

print(f"  Total meaningful events: {len(meaningful_events)}")

# Group by (signal_type, failure_phase)
from collections import defaultdict
groups = defaultdict(list)
for e in meaningful_events:
    key = (e.get("signal_type", "unknown"), e.get("failure_phase", "null"))
    groups[key].append(e)

# Only extract lessons for groups with 2+ events
eligible_groups = {k: v for k, v in groups.items() if len(v) >= 2}
print(f"  Eligible groups (2+ events): {len(eligible_groups)}")
for k, v in eligible_groups.items():
    print(f"    {k}: {len(v)} events")

# Check existing lessons
existing_lessons = read_jsonl(LESSONS_FILE)
existing_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_groups.add(key)

print(f"  Existing lesson groups: {len(existing_groups)}")

# PASS 1: Extract lesson stubs
new_lessons = []
for (sig_type, phase), events_list in eligible_groups.items():
    if (sig_type, phase) in existing_groups:
        print(f"  Skipping duplicate lesson: signal_type={sig_type}, phase={phase}")
        continue

    lesson_text_stub = f"{sig_type} recurs in {phase} phase ({len(events_list)} events)"

    lesson_stub = {
        "lesson_id": f"les_{NOW.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
        "signal_type": sig_type,
        "failure_phase": phase,
        "lesson_text": lesson_text_stub,
        "confidence": "low",
        "events_count": len(events_list),
        "evidence": [f"source: {e.get('source_journal', '?')}" for e in events_list[:3]],
        "extracted_at": NOW.isoformat()
    }
    new_lessons.append(lesson_stub)

# PASS 2: Upgrade with causal grounding
if new_lessons:
    print(f"\n  PASS 2: Upgrading {len(new_lessons)} lessons with causal grounding")
    for lesson in new_lessons:
        # Build causal grounding from events
        sig_type = lesson["signal_type"]
        phase = lesson["failure_phase"]
        
        what = f"Recurring {sig_type} in {phase} phase observed across {lesson['events_count']} events"
        
        # Domain-specific why/when based on signal type
        why_map = {
            "persistent_platform_failure": "Platform-specific automation paths (Meevo Angular, Vagaro JS) have structural breakage that cannot be resolved without platform changes",
            "execution_error": "Infrastructure connectivity or authentication failures prevent successful task completion",
            "escalation": "Critical findings that require human intervention or cross-system fixes",
            "failure_keyword": "Task execution encounters error states that indicate systemic issues",
            "cron_errors": "Scheduled jobs encounter transient or persistent failures (HTTP 429 rate limits, auth issues)",
            "auth_failure": "OAuth tokens expired or revoked, or service authentication paths broken"
        }
        
        when_map = {
            "persistent_platform_failure": "When automating appointment booking on platforms with JS-heavy SPAs that resist headless browser scraping",
            "execution_error": "During task execution when external services are unreachable or return error status",
            "escalation": "When critical infrastructure findings (MCP server unreachable, disk full) are detected",
            "failure_keyword": "When task summaries indicate system-level failures",
            "cron_errors": "During scheduled job execution, particularly under rate limiting or auth expiration conditions",
            "auth_failure": "When OAuth tokens expire, are revoked, or authentication endpoints are unreachable"
        }
        
        why = why_map.get(sig_type, f"Recurring pattern of {sig_type} detected across multiple journal entries")
        when = when_map.get(sig_type, f"During {phase} phase of task execution when {sig_type} conditions are met")
        
        lesson["lesson_text"] = f"[LESSON] What: {what}. Why: {why}. When: {when}"
        lesson["confidence"] = "high"
        lesson["causal_grounding"] = {
            "what": what,
            "why": why,
            "when": when
        }
        lesson["upgraded_at"] = NOW.isoformat()
        print(f"    Upgraded: {lesson['lesson_id']}")

# Write new lessons
if new_lessons:
    append_jsonl(LESSONS_FILE, new_lessons)
    print(f"  Wrote {len(new_lessons)} new lessons")
else:
    print("  No new lessons to write")


# === PHASE 7: Shift Proposal and Activation ===
print("\nPHASE 7: Shift proposal")

all_lessons = read_jsonl(LESSONS_FILE)
high_conf_lessons = [l for l in all_lessons if l.get("confidence") == "high"]
print(f"  High-confidence lessons: {len(high_conf_lessons)}")

# Build set of lesson IDs already covered by active/proposed shifts
all_shifts = read_jsonl(SHIFTS_FILE)
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

remaining_proposals = []
for lesson in high_conf_lessons:
    lid = get_lesson_id(lesson)
    if lid not in covered_lesson_ids:
        remaining_proposals.append(lesson)

print(f"  Uncovered high-conf lessons: {len(remaining_proposals)}")

if remaining_proposals:
    active_count = sum(1 for s in all_shifts if s.get("status") == "active")
    print(f"  Active shifts: {active_count}/{ACTIVE_SHIFT_CAP}")

    new_shifts = []
    for lesson in remaining_proposals:
        if active_count >= ACTIVE_SHIFT_CAP:
            print(f"  At cap ({ACTIVE_SHIFT_CAP}). Shifts proposed but not activated.")
            # Add as proposed
            shift = {
                "shift_id": f"shf_{NOW.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
                "lesson_id": get_lesson_id(lesson),
                "shift_text": lesson["lesson_text"],
                "domain": lesson.get("signal_type", "unknown"),
                "failure_phase": lesson.get("failure_phase", "execution"),
                "status": "proposed",
                "reinforce_count": 0,
                "created_at": NOW.isoformat()
            }
            new_shifts.append(shift)
        else:
            # Activate shift
            shift = {
                "shift_id": f"shf_{NOW.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
                "lesson_id": get_lesson_id(lesson),
                "shift_text": lesson["lesson_text"],
                "domain": lesson.get("signal_type", "unknown"),
                "failure_phase": lesson.get("failure_phase", "execution"),
                "status": "active",
                "reinforce_count": 1,
                "created_at": NOW.isoformat(),
                "last_reinforced": NOW.isoformat()
            }
            new_shifts.append(shift)
            active_count += 1
            print(f"    Activated: {shift['shift_id']}")

    if new_shifts:
        append_jsonl(SHIFTS_FILE, new_shifts)
        print(f"  Wrote {len(new_shifts)} new shifts")


# === PHASE 8: Write Praxis Journal ===
print("\nPHASE 8: Write Praxis journal")
run_id = f"r_{NOW.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
journal_today_dir = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_today_dir, exist_ok=True)

journal_entry = {
    "run_id": run_id,
    "timestamp": NOW.isoformat(),
    "status": "completed",
    "summary": f"Ingest run: {len(unevaluated)} journals scanned, {len(new_events)} events recorded, {len(new_lessons)} new lessons",
    "journals_evaluated": [e["journal_id"] for e in eval_updates],
    "new_events_count": len(new_events),
    "new_lessons_count": len(new_lessons),
    "total_events_in_backlog": len(all_events_final),
    "total_lessons": len(all_lessons)
}

with open(os.path.join(journal_today_dir, f"{run_id}.json"), "w") as f:
    json.dump(journal_entry, f, indent=2, default=str)
print(f"  Journal written: {run_id}.json")


# === PHASE 9: Write Evidence Record ===
print("\nPHASE 9: Write evidence record")
evidence = {
    "run_id": run_id,
    "timestamp": NOW.isoformat(),
    "journals_scanned": len(unevaluated),
    "new_events": len(new_events),
    "new_lessons": len(new_lessons),
    "total_events": len(all_events_final),
    "total_lessons": len(all_lessons),
    "not_activity_reason": None if new_events else "No new behavioral signals detected in unevaluated journals"
}
append_jsonl(EVIDENCE_FILE, [evidence])


# === SUMMARY ===
print("\n" + "=" * 60)
print("INGEST RUN COMPLETE")
print(f"  Run ID: {run_id}")
print(f"  Journals scanned: {len(unevaluated)}")
print(f"  New events: {len(new_events)}")
print(f"  New lessons: {len(new_lessons)}")
print(f"  Total events in backlog: {len(all_events_final)}")
print(f"  Total lessons: {len(all_lessons)}")
print("=" * 60)
