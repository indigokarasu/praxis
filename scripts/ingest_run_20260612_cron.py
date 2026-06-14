#!/usr/bin/env python3
"""
Praxis Journal Ingest Pipeline — 2026-06-12 cron run
Phase 1: Dedup journals_evaluated.jsonl
Phase 2: Scan for unevaluated journals
Phase 3: Extract signals from unevaluated journals
Phase 4: Record events (if any)
Phase 5: Lesson extraction (two-pass with causal grounding)
Phase 6: Shift proposal + activation
Phase 7: Write Praxis journal
"""

import os
import json
from datetime import datetime, timedelta, timezone

# ── Constants ──────────────────────────────────────────────────────────────
JOURNALS_DIR = "/root/.hermes/commons/journals"
DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")
EVIDENCE_FILE = os.path.join(DATA_DIR, "evidence.jsonl")
JOURNAL_DIR = os.path.join(DATA_DIR, "journals")
SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
ACTIVE_SHIFT_CAP = 12
SHIFT_DECAY_DAYS = 14

now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
run_id = f"r_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"

# ── Helpers ────────────────────────────────────────────────────────────────
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

# ── Phase 1: Dedup journals_evaluated.jsonl ────────────────────────────────
print("=" * 60)
print("Phase 1: Dedup journals_evaluated.jsonl")
eval_entries = read_jsonl(EVAL_FILE)
seen_ids = set()
deduped = []
for entry in eval_entries:
    jid = entry.get("journal_id", "")
    if jid not in seen_ids:
        seen_ids.add(jid)
        deduped.append(entry)
removed = len(eval_entries) - len(deduped)
if removed > 0:
    write_jsonl(EVAL_FILE, deduped)
    print(f"  Removed {removed} duplicates, {len(deduped)} entries remain")
else:
    print(f"  No duplicates found, {len(deduped)} entries")

# Compact if >5000
if len(deduped) > 5000:
    cutoff = (now - timedelta(days=30)).isoformat()
    compacted = [e for e in deduped
                 if e.get("evaluated_at", "9999") > cutoff
                 or not e.get("evaluated_at")]
    removed2 = len(deduped) - len(compacted)
    if removed2 > 0:
        write_jsonl(EVAL_FILE, compacted)
        deduped = compacted
        print(f"  Compacted: removed {removed2} entries older than 30 days")

# ── Phase 2: Scan for unevaluated journals ────────────────────────────────
print("\nPhase 2: Scan for unevaluated journals")
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

seen_ids = {e.get("journal_id", "") for e in deduped}
unevaluated = [(c, p) for c, p in all_files if c not in seen_ids and os.path.exists(p)]
print(f"  Total journal files (today+yesterday): {len(all_files)}")
print(f"  Unevaluated: {len(unevaluated)}")
for c, p in unevaluated:
    print(f"    {c}")

# ── Phase 3: Signal extraction ────────────────────────────────────────────
print("\nPhase 3: Signal extraction")
new_events = []
eval_updates = []

for canonical, fpath in unevaluated:
    print(f"\n  Processing: {canonical}")
    try:
        with open(fpath) as f:
            data = json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        print(f"    ERROR reading file: {e}")
        # Record a parse error event for forge journals
        if "ocas-forge" in canonical:
            evt_id = f"evt_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
            new_events.append({
                "event_id": evt_id,
                "recorded_at": now.isoformat(),
                "source_journal": canonical,
                "skill": "ocas-forge",
                "domain": "ocas-forge",
                "signal_type": "execution_error",
                "failure_phase": "execution",
                "context_summary": f"Malformed JSON in journal: {str(e)}",
                "evidence": {"file": fpath, "error": str(e)},
                "outcome_type": "failure"
            })
            eval_updates.append({
                "journal_id": canonical,
                "evaluated_at": now.isoformat(),
                "action_taken": "event_recorded",
                "signals_found": ["execution_error"],
                "event_ids": [evt_id],
                "reason": f"JSON parse error: {str(e)}"
            })
        else:
            eval_updates.append({
                "journal_id": canonical,
                "evaluated_at": now.isoformat(),
                "action_taken": "no_signal",
                "signals_found": [],
                "reason": f"JSON parse error: {str(e)}"
            })
        continue

    signals = []
    summary = ""

    # Extract summary from various locations
    if isinstance(data, dict):
        # Top-level summary
        if "summary" in data and isinstance(data["summary"], str):
            summary = data["summary"]
        elif "decision" in data and isinstance(data["decision"], dict):
            dec = data["decision"]
            if "summary" in dec and isinstance(dec["summary"], str):
                summary = dec["summary"]

        # Check top-level status
        status = data.get("status", "")
        if isinstance(status, str) and status in ("ok", "success", "complete", "completed"):
            if not signals:
                pass  # Will emit no_signal below

        # Check top-level escalation_needed
        if data.get("escalation_needed") is True:
            signals.append({"type": "escalation", "source": "top-level"})

        # Check execution_result
        if "decision" in data and isinstance(data["decision"], dict):
            exec_result = data["decision"].get("execution_result", {})
            if isinstance(exec_result, dict):
                exec_status = exec_result.get("status", "")
                if exec_status in ("error", "partial"):
                    signals.append({"type": "execution_error", "source": "execution_result"})

        # Check actions_taken
        if "actions_taken" in data and isinstance(data["actions_taken"], list):
            for action in data["actions_taken"]:
                if isinstance(action, dict):
                    outcome = action.get("outcome", "")
                    if isinstance(outcome, str) and outcome.lower() in ("error", "failure", "failed"):
                        signals.append({"type": "execution_error", "source": "actions_taken"})

        # Check fixes_applied
        fixes = data.get("fixes_applied", 0)
        if isinstance(fixes, int) and fixes > 0:
            signals.append({"type": "correction", "source": "fixes_applied"})

        # Check new_findings
        if "new_findings" in data and isinstance(data["new_findings"], list):
            for finding in data["new_findings"]:
                if isinstance(finding, dict):
                    sev = finding.get("severity", "")
                    if sev in ("critical", "high", "error"):
                        signals.append({"type": "execution_error", "source": "new_findings"})

        # Check nested findings array
        if "findings" in data and isinstance(data["findings"], list):
            for finding in data["findings"]:
                if isinstance(finding, dict):
                    if finding.get("escalation_needed") is True:
                        signals.append({"type": "escalation", "source": "findings"})
                    fstatus = finding.get("status", "")
                    if fstatus in ("error", "failed"):
                        signals.append({"type": "execution_error", "source": "findings"})
                    action_taken = finding.get("action_taken", "")
                    if isinstance(action_taken, str) and any(kw in action_taken.lower() for kw in ["fix", "correct", "update", "repair"]):
                        signals.append({"type": "correction", "source": "findings"})

        # Check sources_scanned (newer finch schema)
        if "sources_scanned" in data and isinstance(data["sources_scanned"], dict):
            for src_name, src_data in data["sources_scanned"].items():
                if isinstance(src_data, dict):
                    src_status = src_data.get("status", "")
                    if src_status in ("blocked", "error", "failed", "inactive"):
                        signals.append({"type": "execution_error", "source": f"sources_scanned.{src_name}"})
                    src_error = src_data.get("error", "")
                    if isinstance(src_error, str) and src_error and src_error != "none":
                        signals.append({"type": "execution_error", "source": f"sources_scanned.{src_name}"})
                    # Check for auth-related errors
                    if isinstance(src_error, str) and any(kw in src_error.lower() for kw in ["oauth", "token", "auth", "invalid_grant"]):
                        signals.append({"type": "auth_failure", "source": f"sources_scanned.{src_name}"})
                    # Check findings within source
                    src_findings = src_data.get("findings", [])
                    if isinstance(src_findings, list):
                        for sf in src_findings:
                            if isinstance(sf, str) and any(kw in sf.lower() for kw in ["error", "fail", "blocked"]):
                                signals.append({"type": "execution_error", "source": f"sources_scanned.{src_name}.findings"})

        # Check signal_sources (newer finch schema)
        if "signal_sources" in data and isinstance(data["signal_sources"], dict):
            for src_name, src_data in data["signal_sources"].items():
                if isinstance(src_data, dict):
                    src_status = src_data.get("status", "")
                    if src_status in ("blocked", "error", "failed", "inactive"):
                        signals.append({"type": "execution_error", "source": f"signal_sources.{src_name}"})
                    src_error = src_data.get("error", "")
                    if isinstance(src_error, str) and src_error and src_error != "none":
                        signals.append({"type": "execution_error", "source": f"signal_sources.{src_name}"})
                    new_issues = src_data.get("new_issues_since_last_scan", src_data.get("new_issues", []))
                    if isinstance(new_issues, list) and len(new_issues) > 0:
                        for issue in new_issues:
                            signals.append({"type": "execution_error", "source": f"signal_sources.{src_name}.new_issues"})
                    # Cron-specific
                    if src_name == "cron_health":
                        error_jobs = src_data.get("error_jobs", 0)
                        if isinstance(error_jobs, int) and error_jobs > 0:
                            signals.append({"type": "cron_errors", "source": "signal_sources.cron_health"})
                        unchanged = src_data.get("unchanged_errors", [])
                        if isinstance(unchanged, list):
                            for ue in unchanged:
                                if isinstance(ue, str) and any(kw in ue.lower() for kw in ["oauth", "token", "auth"]):
                                    signals.append({"type": "auth_failure", "source": "signal_sources.cron_health"})

        # Check signals.* (older finch schema)
        if "signals" in data and isinstance(data["signals"], dict):
            for sig_key, sig_val in data["signals"].items():
                if isinstance(sig_val, dict):
                    if sig_val.get("status") in ("error", "failed", "blocked"):
                        signals.append({"type": "execution_error", "source": f"signals.{sig_key}"})
                    new_errs = sig_val.get("new_errors", [])
                    if isinstance(new_errs, list) and len(new_errs) > 0:
                        signals.append({"type": "cron_errors", "source": f"signals.{sig_key}"})
                    notes = sig_val.get("notes", "")
                    if isinstance(notes, str) and any(kw in notes.lower() for kw in ["escalat", "critical", "urgent"]):
                        signals.append({"type": "escalation", "source": f"signals.{sig_key}"})

        # Check sources.* (older finch schema)
        if "sources" in data and isinstance(data["sources"], dict):
            for src_key, src_val in data["sources"].items():
                if isinstance(src_val, dict):
                    if src_val.get("status") in ("error", "failed", "blocked"):
                        signals.append({"type": "execution_error", "source": f"sources.{src_key}"})
                    err_bd = src_val.get("error_breakdown", {})
                    if isinstance(err_bd, dict):
                        for err_type, count in err_bd.items():
                            if isinstance(count, int) and count > 0:
                                if "401" in err_type or "auth" in err_type:
                                    signals.append({"type": "auth_failure", "source": f"sources.{src_key}"})
                                else:
                                    signals.append({"type": "cron_errors", "source": f"sources.{src_key}"})

        # Check task_changes / new_tasks (finch)
        if "task_changes" in data and isinstance(data["task_changes"], dict):
            new_tasks = data["task_changes"].get("new", [])
            if isinstance(new_tasks, list):
                for t in new_tasks:
                    if isinstance(t, str) and any(kw in t.lower() for kw in ["error", "fail", "blocked", "down"]):
                        signals.append({"type": "failure_keyword", "source": "task_changes.new"})

        if "new_tasks" in data:
            nt = data["new_tasks"]
            if isinstance(nt, list):
                for t in nt:
                    if isinstance(t, str) and any(kw in t.lower() for kw in ["error", "fail", "blocked", "down"]):
                        signals.append({"type": "failure_keyword", "source": "new_tasks"})
                    elif isinstance(t, dict):
                        tid = t.get("id", t.get("reason", ""))
                        if isinstance(tid, str) and any(kw in tid.lower() for kw in ["error", "fail", "blocked", "down"]):
                            signals.append({"type": "failure_keyword", "source": "new_tasks"})

        # Check tasks_added (older finch)
        if "tasks_added" in data:
            ta = data["tasks_added"]
            if isinstance(ta, int) and ta > 0:
                pass  # Just a count, check new_tasks for details
            elif isinstance(ta, list):
                for t in ta:
                    if isinstance(t, str) and any(kw in t.lower() for kw in ["error", "fail"]):
                        signals.append({"type": "failure_keyword", "source": "tasks_added"})

        # Check source_details (finch scan-1525 schema)
        if "source_details" in data and isinstance(data["source_details"], dict):
            for src_name, src_data in data["source_details"].items():
                if isinstance(src_data, dict):
                    src_status = src_data.get("status", "")
                    if src_status == "blocked":
                        reason = src_data.get("reason", "")
                        if isinstance(reason, str) and any(kw in reason.lower() for kw in ["oauth", "token", "auth", "invalid_grant"]):
                            signals.append({"type": "auth_failure", "source": f"source_details.{src_name}"})
                        signals.append({"type": "execution_error", "source": f"source_details.{src_name}"})
                    elif src_status in ("error", "failed"):
                        signals.append({"type": "execution_error", "source": f"source_details.{src_name}"})
                    # Check errors list
                    errors_list = src_data.get("errors", [])
                    if isinstance(errors_list, list) and len(errors_list) > 0:
                        signals.append({"type": "cron_errors", "source": f"source_details.{src_name}"})
                    # Check new_errors
                    new_errs = src_data.get("new_errors_since_daily", src_data.get("new_errors", []))
                    if isinstance(new_errs, list) and len(new_errs) > 0:
                        signals.append({"type": "cron_errors", "source": f"source_details.{src_name}"})

        # Summary keyword matching (with noise suppression)
        if isinstance(summary, str) and len(summary.strip()) > 0:
            summary_lower = summary.lower()
            if any(kw in summary_lower for kw in ["error", "failed", "failure", "timeout", "crash"]):
                signals.append({"type": "failure_keyword", "source": "summary"})
            if any(kw in summary_lower for kw in ["oauth", "token", "auth", "401", "invalid_grant"]):
                signals.append({"type": "auth_failure", "source": "summary"})

    # Apply summary noise suppression
    if isinstance(summary, str) and signals:
        if should_suppress_summary_signals(summary, signals):
            print(f"    Suppressed summary-derived signals (noise filter)")
            signals = []

    # Check for completed_with_errors status
    if isinstance(data, dict):
        tl_status = data.get("status", "")
        if isinstance(tl_status, str) and tl_status == "completed_with_errors":
            if not any(s["type"] == "execution_error" for s in signals):
                signals.append({"type": "execution_error", "source": "status"})

    # Emit results
    if not signals:
        print(f"    No signals found")
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })
    else:
        print(f"    Signals found: {[s['type'] for s in signals]}")
        event_ids_for_eval = []
        for sig in signals:
            evt_id = f"evt_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}_{canonical.split('/')[0][:5]}"
            # Determine failure phase
            fp = "execution"  # default for error signals
            if sig["type"] in ("escalation",):
                fp = "planning"
            elif sig["type"] in ("correction",):
                fp = "execution"

            evt = {
                "event_id": evt_id,
                "timestamp": data.get("timestamp", data.get("scan_time", now.isoformat())),
                "domain": canonical.split("/")[0],
                "context_summary": f"{sig['type']}: {sig['source']}",
                "outcome_type": "failure",
                "outcome_summary": f"Signal: {sig['type']} from {sig['source']}",
                "evidence": [f"canonical: {canonical}", f"signal_type: {sig['type']}", f"source: {sig['source']}"],
                "failure_phase": fp,
                "user_relevance": "agent_only",
                "source_journal": canonical,
                "signal_type": sig["type"],
                "recorded_at": now.isoformat()
            }
            new_events.append(evt)
            event_ids_for_eval.append(evt_id)

        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "event_recorded",
            "signals_found": [s["type"] for s in signals],
            "event_ids": event_ids_for_eval,
            "reason": f"Recorded {len(signals)} events"
        })

print(f"\n  Total new events: {len(new_events)}")
print(f"  Total eval updates: {len(eval_updates)}")

# ── Phase 4: Write events + eval updates ──────────────────────────────────
print("\nPhase 4: Write events + eval updates")
if new_events:
    append_jsonl(EVENTS_FILE, new_events)
    print(f"  Appended {len(new_events)} events to events.jsonl")

# Post-write dedup of events by (source_journal, signal_type)
all_events = read_jsonl(EVENTS_FILE)
deduped_events = []
seen_event_keys = set()
for evt in all_events:
    key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
    if key not in seen_event_keys:
        seen_event_keys.add(key)
        deduped_events.append(evt)
    # else: skip duplicate (source_journal, signal_type) — keep earliest
if len(deduped_events) < len(all_events):
    write_jsonl(EVENTS_FILE, deduped_events)
    print(f"  Post-write dedup: {len(all_events)} -> {len(deduped_events)} events")
else:
    print(f"  No event dedup needed ({len(all_events)} events)")

# Append eval updates
append_jsonl(EVAL_FILE, eval_updates)
print(f"  Appended {len(eval_updates)} eval updates")

# ── Phase 5: Lesson extraction (two-pass) ─────────────────────────────────
print("\nPhase 5: Lesson extraction (two-pass)")

# Re-read events from disk
all_events = read_jsonl(EVENTS_FILE)
print(f"  Total events on disk: {len(all_events)}")

# Filter to meaningful events
MEANINGFUL_TYPES = {"auth_failure", "escalation", "execution_error", "correction", "cron_errors", "failure_keyword"}
meaningful_events = [e for e in all_events if e.get("signal_type") in MEANINGFUL_TYPES]
print(f"  Meaningful events: {len(meaningful_events)}")

# Group by (signal_type, failure_phase)
from collections import defaultdict
groups = defaultdict(list)
for evt in meaningful_events:
    key = (evt.get("signal_type", ""), evt.get("failure_phase", "execution"))
    groups[key].append(evt)

print(f"  Event groups: {len(groups)}")
for k, v in groups.items():
    print(f"    {k}: {len(v)} events")

# Load existing lessons
existing_lessons = read_jsonl(LESSONS_FILE)
existing_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", "execution"))
    if key[0] and key[1]:
        existing_groups.add(key)

print(f"  Existing lesson groups: {existing_groups}")

# Pass 1: Extract lesson stubs for groups with 2+ events
new_lessons = []
for (sig_type, phase), events in groups.items():
    if len(events) < 2:
        continue
    if (sig_type, phase) in existing_groups:
        print(f"    Skipping duplicate lesson: signal_type={sig_type}, phase={phase}")
        continue

    # Build lesson text
    what_parts = []
    for e in events[:5]:  # Cap at 5 evidence items
        ctx = e.get("context_summary", e.get("outcome_summary", ""))
        if ctx:
            what_parts.append(ctx)
    what = "; ".join(what_parts) if what_parts else f"Recurring {sig_type} in {phase} phase"

    lesson_id = f"les_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()[:6]}"
    lesson = {
        "lesson_id": lesson_id,
        "event_ids": [get_event_id(e) for e in events],
        "lesson_text": f"[LESSON] What: {what}. Why: extracted from {len(events)} events. When: Observed in phase={phase}",
        "confidence": "high",
        "scope": events[0].get("domain", "unknown"),
        "status": "proposed",
        "failure_phase": phase,
        "causal_grounding": "what+why+when",
        "signal_type": sig_type,
        "skills_affected": [events[0].get("domain", "unknown")],
        "created_at": now.isoformat(),
        "what": what,
        "why": f"Pattern observed across {len(events)} events in {events[0].get('domain', 'unknown')}",
        "when": f"Observed in phase={phase}, domain={events[0].get('domain', 'unknown')}"
    }
    new_lessons.append(lesson)
    print(f"    New lesson: {sig_type}/{phase} ({len(events)} events)")

if new_lessons:
    append_jsonl(LESSONS_FILE, new_lessons)
    print(f"  Wrote {len(new_lessons)} new lessons")
else:
    print(f"  No new lessons to write")

# ── Phase 6: Shift proposal + activation ──────────────────────────────────
print("\nPhase 6: Shift proposal + activation")

# Re-read lessons
all_lessons = read_jsonl(LESSONS_FILE)
all_shifts = read_jsonl(SHIFTS_FILE)

# Count active shifts
active_shifts = [s for s in all_shifts if s.get("status") == "active"]
proposed_shifts = [s for s in all_shifts if s.get("status") == "proposed"]
print(f"  Active shifts: {len(active_shifts)}/{ACTIVE_SHIFT_CAP}")
print(f"  Proposed shifts: {len(proposed_shifts)}")

# Build set of lesson IDs covered by active/proposed shifts
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

# Find high-confidence lessons not covered
new_proposals = []
for lesson in all_lessons:
    lid = get_lesson_id(lesson)
    if lesson.get("confidence") == "high" and lid and lid not in covered_lesson_ids:
        new_proposals.append(lesson)

print(f"  Uncovered high-confidence lessons: {len(new_proposals)}")

# Propose shifts for uncovered lessons
truly_new = []
for lesson in new_proposals:
    sig_type = lesson.get("signal_type", "")
    phase = lesson.get("failure_phase", "execution")
    domain = lesson.get("skills_affected", ["unknown"])[0] if lesson.get("skills_affected") else "unknown"

    # Check domain+phase overlap with active shifts
    overlap = False
    for active in active_shifts:
        a_domain = active.get("domain", "")
        a_phase = get_failure_phase(active)
        if a_domain == domain and a_phase == phase:
            # Reinforce active shift
            active["last_reinforced_at"] = now.isoformat()
            active["reinforcement_count"] = active.get("reinforcement_count", 0) + 1
            active["last_reviewed_at"] = now.isoformat()
            overlap = True
            print(f"    Reinforced active shift: {get_shift_id(active)} ({domain}/{phase})")
            break

    if not overlap:
        shift_id = f"shf_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()[:6]}"
        lesson_id = get_lesson_id(lesson)
        shift = {
            "shift_id": shift_id,
            "source_lesson_ids": [lesson_id] if lesson_id else [],
            "shift_text": f"Behavioral adjustment for {sig_type} in {phase} phase: {lesson.get('what', '')[:120]}",
            "status": "proposed",
            "activation_reason": f"Proposed from {sig_type} lesson ({len(lesson.get('event_ids', []))} events)",
            "created_at": now.isoformat(),
            "last_reviewed_at": now.isoformat(),
            "expiry_condition": f"{SHIFT_DECAY_DAYS}_days without reinforcement",
            "priority": 1,
            "last_reinforced_at": now.isoformat(),
            "reinforcement_count": 0,
            "failure_phase": phase,
            "domain": domain
        }
        truly_new.append(shift)
        print(f"    New shift proposal: {shift_id} ({domain}/{phase})")

# Activate proposals if under cap
remaining_proposals = []
for shift in truly_new:
    current_active = len([s for s in all_shifts if s.get("status") == "active"]) + len([s for s in truly_new if s.get("status") == "active"])
    if current_active < ACTIVE_SHIFT_CAP:
        shift["status"] = "active"
        print(f"    Activated: {get_shift_id(shift)}")
    else:
        remaining_proposals.append(shift)
        print(f"    Held at cap: {get_shift_id(shift)}")

# Rewrite shifts file: existing (with reinforcements) + new proposals
all_shifts_out = []
# Add reinforced active shifts (updated in memory)
shift_map = {get_shift_id(s): s for s in all_shifts}
for shift in truly_new:
    sid = get_shift_id(shift)
    if sid not in shift_map:
        all_shifts_out.append(shift)
# Write all existing shifts (reinforced ones are already updated in the list)
seen_shift_ids = set()
final_shifts = []
for s in all_shifts + truly_new:
    sid = get_shift_id(s)
    if sid not in seen_shift_ids:
        seen_shift_ids.add(sid)
        final_shifts.append(s)

write_jsonl(SHIFTS_FILE, final_shifts)
print(f"  Total shifts on disk: {len(final_shifts)}")

# ── Phase 7: Write Praxis journal ─────────────────────────────────────────
print("\nPhase 7: Write Praxis journal")

# Count active shifts for real
final_active = len([s for s in final_shifts if s.get("status") == "active"])

journal_entry = {
    "run_id": run_id,
    "timestamp": now.isoformat(),
    "command": "praxis:journal_ingest",
    "skill": "ocas-praxis",
    "skill_version": "3.2.0",
    "decision": {
        "journals_scanned": len(unevaluated),
        "new_events_recorded": len(new_events),
        "new_lessons_extracted": len(new_lessons),
        "new_shifts_proposed": len(truly_new),
        "active_shifts": final_active,
        "shift_cap": ACTIVE_SHIFT_CAP,
        "total_events_on_disk": len(all_events),
        "total_lessons_on_disk": len(all_lessons),
        "total_shifts_on_disk": len(final_shifts),
        "eval_updates_written": len(eval_updates)
    },
    "execution_result": {
        "status": "ok",
        "summary": f"Ingest complete: {len(unevaluated)} journals scanned, {len(new_events)} events, {len(new_lessons)} lessons, {len(truly_new)} shift proposals"
    }
}

journal_path = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_path, exist_ok=True)
with open(os.path.join(journal_path, f"{run_id}.json"), 'w') as f:
    json.dump(journal_entry, f, indent=2)

print(f"  Journal written: {journal_path}/{run_id}.json")

# ── Decision log ──────────────────────────────────────────────────────────
decision_entry = {
    "timestamp": now.isoformat(),
    "run_id": run_id,
    "decision": "praxis:journal_ingest",
    "outcome": "completed",
    "details": {
        "journals_scanned": len(unevaluated),
        "new_events": len(new_events),
        "new_lessons": len(new_lessons),
        "new_shifts": len(truly_new),
        "active_shifts": final_active
    }
}
append_jsonl(DECISIONS_FILE, [decision_entry])

# ── Evidence log ──────────────────────────────────────────────────────────
evidence_entry = {
    "timestamp": now.isoformat(),
    "run_id": run_id,
    "activity": "praxis:journal_ingest",
    "not_activity_reason": None,
    "gap_detected": False,
    "degraded": None
}
append_jsonl(EVIDENCE_FILE, [evidence_entry])

print("\n" + "=" * 60)
print("INGEST COMPLETE")
print(f"  Run ID: {run_id}")
print(f"  Journals scanned: {len(unevaluated)}")
print(f"  New events: {len(new_events)}")
print(f"  New lessons: {len(new_lessons)}")
print(f"  New shift proposals: {len(truly_new)}")
print(f"  Active shifts: {final_active}/{ACTIVE_SHIFT_CAP}")
print(f"  Total events: {len(all_events)}")
print(f"  Total lessons: {len(all_lessons)}")
print(f"  Total shifts: {len(final_shifts)}")
