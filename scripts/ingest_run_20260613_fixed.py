#!/usr/bin/env python3
"""
Praxis Journal Ingest Run — 2026-06-13 (07:24 UTC) FIXED
Scans all skill journals for new entries, extracts behavioral signals,
records events, extracts lessons, proposes/activates shifts.

Fix: Finch sources.* can be simple strings (not dicts), e.g. "MCP unreachable — cannot check"
Also: Finch findings[].type == "critical" should produce escalation signals
Also: Mentor evaluation_coverage < 0.2 should produce planning-phase observation events
"""

import json
import os
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import hashlib

# === PATHS ===
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
    "operational", "healthy",
    "no unprocessed", "nothing to process", "no variant",
    "only config.json", "scan locations were empty"
]

# === HELPERS ===

def get_event_id(evt):
    return evt.get("event_id", evt.get("id", ""))

def get_lesson_id(les):
    return les.get("lesson_id", les.get("id", ""))

def get_shift_id(s):
    return s.get("shift_id", s.get("id", "?"))

def get_failure_phase_s(s):
    return s.get("failure_phase", s.get("phase", "execution"))

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
    SUMMARY_DERIVED_TYPES = {"failure_keyword", "auth_failure"}
    non_summary = [s for s in signals if s["type"] not in SUMMARY_DERIVED_TYPES]
    if non_summary:
        return False
    summary_lower = summary_str.lower()
    for phrase in SUPPRESS_PHRASES:
        if phrase in summary_lower:
            return True
    return False

def extract_signals(journal_data, canonical):
    signals = []
    summary = ""

    if isinstance(journal_data, list):
        for entry in journal_data:
            if isinstance(entry, dict):
                signals.extend(extract_signals(entry, canonical))
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

    # 3. Top-level status
    status = journal_data.get("status", "")
    if status in ("error", "partial", "completed_with_errors"):
        signals.append({"type": "execution_error", "detail": f"top-level status={status}"})

    # 4. Summary resolution
    dec_summary = ""
    if isinstance(decision, dict):
        dec_summary = decision.get("summary", "")
    top_summary = journal_data.get("summary", "")

    if isinstance(dec_summary, str) and dec_summary.strip():
        summary = dec_summary
    elif isinstance(top_summary, str) and top_summary.strip():
        summary = top_summary
    elif isinstance(top_summary, dict):
        summary = json.dumps(top_summary)

    # 5. actions_taken[].outcome
    actions_taken = journal_data.get("actions_taken", [])
    if isinstance(actions_taken, list):
        for action in actions_taken:
            if isinstance(action, dict):
                outcome = str(action.get("outcome", "")).lower()
                if outcome in ("error", "failure", "failed"):
                    signals.append({"type": "execution_error", "detail": f"action_outcome={outcome}"})
                elif outcome in ("corrected", "fix_applied", "fixed", "applied"):
                    signals.append({"type": "correction", "detail": f"action_outcome={outcome}"})

    # 6. fixes_applied
    fixes = journal_data.get("fixes_applied", 0)
    if isinstance(fixes, int) and fixes > 0:
        signals.append({"type": "correction", "detail": f"fixes_applied={fixes}"})

    checks = journal_data.get("checks", {})
    if isinstance(checks, dict):
        checks_fixes = checks.get("fixes_applied", 0)
        if isinstance(checks_fixes, int) and checks_fixes > 0:
            signals.append({"type": "correction", "detail": f"checks.fixes_applied={checks_fixes}"})

    # 7. new_findings[]
    new_findings = journal_data.get("new_findings", [])
    if isinstance(new_findings, list):
        for finding in new_findings:
            if isinstance(finding, dict):
                sev = finding.get("severity", "")
                if sev in ("error", "critical", "high"):
                    signals.append({"type": "execution_error", "detail": f"finding: {finding.get('title', finding.get('id', ''))}"})

    # 8. findings[] (nested)
    findings = journal_data.get("findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict):
                if finding.get("escalation_needed") is True:
                    signals.append({"type": "escalation", "detail": f"finding escalation: {finding.get('title', finding.get('id', ''))}"})
                f_status = finding.get("status", "")
                if f_status in ("error", "failed"):
                    signals.append({"type": "execution_error", "detail": f"finding status={f_status}: {finding.get('title', finding.get('id', ''))}"})
                f_type = finding.get("type", "")
                if f_type == "critical":
                    signals.append({"type": "escalation", "detail": f"critical finding: {finding.get('title', '')} — {finding.get('detail', '')}"})
                action_taken = finding.get("action_taken", "")
                if isinstance(action_taken, str) and any(kw in action_taken.lower() for kw in ["fix", "correct", "update", "applied"]):
                    signals.append({"type": "correction", "detail": f"finding action: {action_taken}"})

    # 9. Finch signals.* (dict-based)
    finch_signals = journal_data.get("signals", {})
    if isinstance(finch_signals, dict) and finch_signals:
        for sig_key, sig_val in finch_signals.items():
            if isinstance(sig_val, dict):
                cron_signals = sig_val if sig_key == "cron" else {}
                if sig_key == "cron":
                    new_errors = sig_val.get("new_errors", [])
                    if isinstance(new_errors, list):
                        for err in new_errors:
                            if isinstance(err, dict):
                                signals.append({"type": "cron_errors", "detail": f"new_cron_error: {err.get('job', err.get('name', ''))} — {err.get('error', err.get('message', ''))}"})
                            elif isinstance(err, str):
                                signals.append({"type": "cron_errors", "detail": f"new_cron_error: {err}"})
                    error_breakdown = sig_val.get("error_breakdown", {})
                    if isinstance(error_breakdown, dict):
                        for key, val in error_breakdown.items():
                            if isinstance(val, int) and val > 0:
                                signals.append({"type": "cron_errors", "detail": f"error_breakdown.{key}={val}"})
                notes = sig_val.get("notes", "")
                if isinstance(notes, str) and notes.strip():
                    notes_lower = notes.lower()
                    for kw in ["error", "fail", "escalat", "correction", "fix"]:
                        if kw in notes_lower:
                            signals.append({"type": "failure_keyword", "detail": f"signals.{sig_key}.notes: {notes}"})
                            break

    # 9b. Finch sources.* — can be dicts OR simple strings like "MCP unreachable — cannot check"
    sources = journal_data.get("sources", {})
    if isinstance(sources, dict) and sources:
        for src_name, src_val in sources.items():
            if isinstance(src_val, dict):
                src_status = src_val.get("status", "")
                if src_status in ("blocked", "error", "failed", "inactive"):
                    signals.append({"type": "execution_error", "detail": f"sources.{src_name}.status={src_status}"})
                src_error = src_val.get("error", "")
                if isinstance(src_error, str) and src_error.strip() and src_error.strip().lower() != "none":
                    signals.append({"type": "execution_error", "detail": f"sources.{src_name}.error={src_error}"})
                new_issues = src_val.get("new_issues_since_last_scan", src_val.get("new_issues", []))
                if isinstance(new_issues, list):
                    for issue in new_issues:
                        signals.append({"type": "execution_error", "detail": f"sources.{src_name}.new_issue={issue}"})
                if src_name == "cron_health":
                    error_jobs = src_val.get("error_jobs", 0)
                    if isinstance(error_jobs, int) and error_jobs > 0:
                        signals.append({"type": "cron_errors", "detail": f"cron_health.error_jobs={error_jobs}"})
            elif isinstance(src_val, str):
                # Simple string format: "MCP unreachable — cannot check" or "Unable to verify — Google Workspace MCP unreachable"
                src_lower = src_val.lower()
                if any(kw in src_lower for kw in ["unreachable", "error", "failed", "blocked", "cannot check", "unable to verify", "mcp unreachable"]):
                    signals.append({"type": "execution_error", "detail": f"sources.{src_name}: {src_val}"})
                if any(kw in src_lower for kw in ["oauth", "token", "401", "auth"]):
                    signals.append({"type": "auth_failure", "detail": f"sources.{src_name}: {src_val}"})

    # 9c. Finch signal_sources.*
    signal_sources = journal_data.get("signal_sources", {})
    if isinstance(signal_sources, dict) and signal_sources:
        for src_name, src_data in signal_sources.items():
            if isinstance(src_data, dict):
                src_status = src_data.get("status", "")
                if src_status in ("blocked", "error", "failed", "inactive"):
                    signals.append({"type": "execution_error", "detail": f"signal_sources.{src_name}.status={src_status}"})
                src_error = src_data.get("error", "")
                if isinstance(src_error, str) and src_error.strip() and src_error.strip().lower() != "none":
                    signals.append({"type": "execution_error", "detail": f"signal_sources.{src_name}.error={src_error}"})
                new_issues = src_data.get("new_issues_since_last_scan", src_data.get("new_issues", []))
                if isinstance(new_issues, list):
                    for issue in new_issues:
                        signals.append({"type": "execution_error", "detail": f"signal_sources.{src_name}.new_issue={issue}"})

    # 9d. Finch sources_scanned.*
    sources_scanned = journal_data.get("sources_scanned", {})
    if isinstance(sources_scanned, dict) and sources_scanned:
        for src_name, src_data in sources_scanned.items():
            if isinstance(src_data, dict):
                src_status = src_data.get("status", "")
                if src_status in ("blocked", "error", "failed", "inactive"):
                    src_reason = src_data.get("reason", "")
                    signals.append({"type": "execution_error", "detail": f"sources_scanned.{src_name}.status={src_status}: {src_reason}"})
                    if isinstance(src_reason, str) and any(kw in src_reason.lower() for kw in ["oauth", "token", "401", "auth"]):
                        signals.append({"type": "auth_failure", "detail": f"sources_scanned.{src_name}.auth_issue: {src_reason}"})
                src_findings = src_data.get("findings", [])
                if isinstance(src_findings, list):
                    for fnd in src_findings:
                        if isinstance(fnd, str) and fnd.strip():
                            signals.append({"type": "execution_error", "detail": f"sources_scanned.{src_name}.finding: {fnd}"})

    # 10. key_findings
    key_findings = journal_data.get("key_findings", [])
    if isinstance(key_findings, list):
        for kf in key_findings:
            if isinstance(kf, str):
                kf_lower = kf.lower()
                if any(kw in kf_lower for kw in ["error", "fail", "blocked", "oauth", "401", "unreachable"]):
                    signals.append({"type": "failure_keyword", "detail": f"key_finding: {kf}"})

    # 11. tasks_added / new_tasks
    tasks_added = journal_data.get("tasks_added", [])
    if isinstance(tasks_added, list):
        for task in tasks_added:
            if isinstance(task, str):
                task_lower = task.lower()
                if any(kw in task_lower for kw in ["error", "fail"]):
                    signals.append({"type": "failure_keyword", "detail": f"task_added: {task}"})
            elif isinstance(task, dict):
                tid = task.get("id", task.get("reason", ""))
                signals.append({"type": "correction", "detail": f"task_added: {tid}"})

    new_tasks = journal_data.get("new_tasks", [])
    if isinstance(new_tasks, list):
        for task in new_tasks:
            if isinstance(task, dict):
                reason = task.get("reason", "")
                if isinstance(reason, str):
                    reason_lower = reason.lower()
                    if any(kw in reason_lower for kw in ["error", "fail", "blocked", "oauth", "401", "token"]):
                        signals.append({"type": "failure_keyword", "detail": f"new_task.reason: {reason}"})

    # 12. Persistent platform failure (spot sweep journals)
    if "persistent_failure" in journal_data and journal_data["persistent_failure"]:
        signals.append({"type": "persistent_platform_failure", "detail": str(journal_data["persistent_failure"])})

    consecutive_failures = journal_data.get("consecutive_failures", 0)
    if isinstance(consecutive_failures, int) and consecutive_failures > 10:
        signals.append({"type": "persistent_platform_failure", "detail": f"consecutive_failures={consecutive_failures}"})

    # 13. Mentor evaluation_coverage < 0.2 → planning observation
    metrics = journal_data.get("metrics", {})
    if isinstance(metrics, dict):
        eval_cov = metrics.get("evaluation_coverage", 1.0)
        if isinstance(eval_cov, (int, float)) and eval_cov < 0.2:
            signals.append({"type": "observation", "detail": f"Low evaluation coverage: {eval_cov:.4f} (below 0.2 threshold)"})

    # 14. Summary keyword scanning
    if isinstance(summary, str) and summary.strip():
        summary_lower = summary.lower()
        failure_keywords = ["error", "failed", "failure", "timeout", "truncat", "crash", "exception", "unreachable"]
        for kw in failure_keywords:
            if kw in summary_lower:
                signals.append({"type": "failure_keyword", "detail": f"summary contains '{kw}'"})
                break
        auth_keywords = ["oauth", "token", "401", "unauthorized", "auth"]
        for kw in auth_keywords:
            if kw in summary_lower:
                signals.append({"type": "auth_failure", "detail": f"summary contains '{kw}'"})
                break

        # Apply semantic suppression
        if should_suppress_summary_signals(summary, signals):
            signals = [s for s in signals if s["type"] not in ("failure_keyword", "auth_failure")]

    return signals

def determine_failure_phase(signal_type, detail):
    detail_lower = detail.lower() if isinstance(detail, str) else ""
    if any(kw in detail_lower for kw in ["should have", "before", "wrong approach", "didn't check", "missing prerequisite"]):
        return "planning"
    if any(kw in detail_lower for kw in ["too verbose", "wrong format", "just give me", "make it concise"]):
        return "response"
    if signal_type in ("execution_error", "cron_errors", "escalation", "persistent_platform_failure"):
        return "execution"
    if signal_type in ("correction", "observation"):
        return "execution"
    return "execution"

# === MAIN ===

print("=" * 60)
print("PRAXIS JOURNAL INGEST (FIXED) — 2026-06-13 07:24 UTC")
print("=" * 60)

now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
day_before = (now - timedelta(days=2)).strftime("%Y-%m-%d")
run_id = f"r_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"

print(f"\nRun ID: {run_id}")

# Re-read eval (already written by first run, so we need to undo those no_signal writes)
# Actually the first run already marked all 11 as evaluated with no_signal.
# We need to re-process them. Let's read the eval file and remove the ones we're re-processing.

eval_entries = read_jsonl(EVAL_FILE)
# Remove the entries we incorrectly marked as no_signal in the first run
# The 11 journals from the first run
to_reprocess = [
    "ocas-mentor/2026-06-13/mentor-light-20260613T065528Z.json",
    "ocas-mentor/2026-06-13/mentor-light-20260613T061534Z.json",
    "ocas-forge/2026-06-13/r_1781331042.json",
    "ocas-forge/2026-06-13/r_1781334952.json",
    "ocas-forge/2026-06-12/r_20260612_journal-scan-1781332886.json",
    "ocas-spot/2026-06-13/sweep_20260613_030000.json",
    "ocas-spot/2026-06-13/spot-20260613-000102.json",
    "ocas-spot/2026-06-13/sweep-20260613-001628.json",
    "ocas-spot/2026-06-12/sweep_20260612T234644-07:00.json",
    "ocas-spot/2026-06-12/sweep_20260612_231648.json",
    "ocas-finch/2026-06-13/scan-0600.json",
]

print(f"\nRe-processing {len(to_reprocess)} journals from first run...")

# Build file path map
fpath_map = {}
SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
for root_dir, dirs, files in os.walk(JOURNALS_DIR):
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    parts = root_dir.replace(JOURNALS_DIR, "").strip('/').split('/')
    if parts and parts[0] in SKIP_DIRS:
        continue
    for fname in files:
        if fname.endswith('.json'):
            full_path = os.path.join(root_dir, fname)
            rel_path = os.path.relpath(full_path, JOURNALS_DIR)
            fpath_map[rel_path] = full_path

new_events = []
eval_updates = []

for canonical in to_reprocess:
    fpath = fpath_map.get(canonical)
    if not fpath or not os.path.exists(fpath):
        print(f"  SKIP {canonical}: file not found")
        continue

    try:
        with open(fpath, 'r') as f:
            journal_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"  SKIP {canonical}: {e}")
        continue

    signals = extract_signals(journal_data, canonical)

    if not signals:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now_iso(),
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })
        continue

    # Dedup by (canonical, signal_type)
    seen_types = set()
    unique_signals = []
    for s in signals:
        key = (canonical, s["type"])
        if key not in seen_types:
            seen_types.add(key)
            unique_signals.append(s)

    event_ids_for_journal = []
    for sig in unique_signals:
        sig_type = sig["type"]
        event_id = f"evt_{now.strftime('%Y%m%d_%H%M%S')}_{hashlib.md5((canonical + '_' + sig_type + '_' + now_iso()).encode()).hexdigest()[:8]}"
        failure_phase = determine_failure_phase(sig["type"], sig["detail"])
        domain = canonical.split("/")[0] if "/" in canonical else "unknown"

        event = {
            "event_id": event_id,
            "timestamp": now_iso(),
            "domain": domain,
            "context_summary": sig["detail"][:200],
            "outcome_type": "failure" if sig["type"] in ("execution_error", "cron_errors", "escalation", "persistent_platform_failure") else sig["type"],
            "outcome_summary": sig["detail"][:200],
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

# Read existing events, append new, dedup
existing_events = read_jsonl(EVENTS_FILE)
all_events = existing_events + new_events

# Dedup by (source_journal, signal_type)
deduped_events = []
seen_keys = set()
for evt in all_events:
    key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
    if key not in seen_keys:
        seen_keys.add(key)
        deduped_events.append(evt)
write_jsonl(EVENTS_FILE, deduped_events)
print(f"  Events: {len(existing_events)} existing + {len(new_events)} new -> {len(deduped_events)} after dedup")

# Update eval entries: remove old no_signal for reprocessed journals, add new ones
eval_entries_clean = [e for e in eval_entries if e.get("journal_id") not in to_reprocess]
eval_entries_clean.extend(eval_updates)
write_jsonl(EVAL_FILE, eval_entries_clean)
print(f"  Eval entries: {len(eval_entries)} -> {len(eval_entries_clean)}")

# === LESSON EXTRACTION ===
print("\n[LESSON EXTRACTION]")
all_events = read_jsonl(EVENTS_FILE)
meaningful = [e for e in all_events if e.get("signal_type") and e.get("signal_type") not in ("unknown", "?", None, "", "observation")]

groups = defaultdict(list)
for evt in meaningful:
    key = (evt.get("signal_type", ""), evt.get("failure_phase", ""))
    if key[0] and key[1]:
        groups[key].append(evt)

existing_lessons = read_jsonl(LESSONS_FILE)
existing_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_groups.add(key)

new_lessons = []
for (sig_type, phase), evts in groups.items():
    if len(evts) >= 2 and (sig_type, phase) not in existing_groups:
        lesson_id = f"les_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()[:6]}"
        summaries = [e.get("context_summary", "")[:100] for e in evts[:3]]
        lesson_text = f"[LESSON] What: Recurring {sig_type} in {phase} phase ({len(evts)} events): {'; '.join(summaries)}"
        lesson = {
            "lesson_id": lesson_id,
            "event_ids": [get_event_id(e) for e in evts],
            "lesson_text": lesson_text,
            "confidence": "high",
            "scope": evts[0].get("domain", "unknown"),
            "status": "proposed",
            "failure_phase": phase,
            "causal_grounding": {"what": f"Recurring {sig_type}", "why": f"Multiple events across domains indicate systemic pattern", "when": f"During {phase} phase"},
            "signal_type": sig_type,
            "skills_affected": list(set(e.get("domain", "unknown") for e in evts)),
            "extracted_at": now_iso()
        }
        new_lessons.append(lesson)
        print(f"  Lesson: signal_type={sig_type}, phase={phase}, events={len(evts)}")
        print(f"    Text: {lesson_text[:120]}")

if new_lessons:
    append_jsonl(LESSONS_FILE, new_lessons)
    print(f"  Wrote {len(new_lessons)} lessons to lessons.jsonl")
else:
    print(f"  No new lesson groups (all groups <2 events or already covered)")
    print(f"  Total event groups: {len(groups)}")
    for (st, ph), evts in groups.items():
        print(f"    ({st}, {ph}): {len(evts)} events")

# === SHIFT PROPOSAL ===
print("\n[SHIFT PROPOSAL]")
all_shifts = read_jsonl(SHIFTS_FILE)
active_count = sum(1 for s in all_shifts if s.get("status") == "active")
print(f"  Active shifts: {active_count}/12")

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

new_proposals = []
for les in new_lessons:
    lid = get_lesson_id(les)
    if les.get('confidence') == 'high' and lid not in covered_lesson_ids:
        # Check domain+phase overlap with active shifts
        domain = les.get("scope", "unknown")
        phase = les.get("failure_phase", "execution")
        overlap = False
        for s in all_shifts:
            if s.get("status") == "active":
                s_domain = s.get("domain", "")
                s_phase = get_failure_phase_s(s)
                if s_domain == domain and s_phase == phase:
                    overlap = True
                    # Reinforce existing
                    s["reinforcement_count"] = s.get("reinforcement_count", 0) + 1
                    s["last_reinforced"] = now_iso()
                    print(f"  Reinforced existing shift: {get_shift_id(s)} ({s_domain}/{s_phase})")
                    break
        if not overlap and active_count + len(new_proposals) < 12:
            shift_id = f"shf_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()[:6]}"
            proposal = {
                "shift_id": shift_id,
                "shift_text": f"When in {phase} phase for {domain} tasks, watch for {les.get('signal_type', 'unknown')} patterns: {les.get('lesson_text', '')[:100]}",
                "lesson_id": lid,
                "domain": domain,
                "failure_phase": phase,
                "status": "active",
                "confidence": "high",
                "created_at": now_iso(),
                "reinforcement_count": 1,
                "last_reinforced": now_iso(),
                "source_signal_type": les.get("signal_type", "unknown")
            }
            new_proposals.append(proposal)
            print(f"  Proposed shift: {shift_id} ({domain}/{phase})")

if new_proposals:
    # Rewrite shifts file with all shifts
    all_shifts.extend(new_proposals)
    write_jsonl(SHIFTS_FILE, all_shifts)
    print(f"  Wrote {len(new_proposals)} new shifts (total: {len(all_shifts)})")
else:
    # Still rewrite to include any reinforcements
    write_jsonl(SHIFTS_FILE, all_shifts)
    print(f"  No new shifts proposed")

# === JOURNAL OUTPUT ===
print("\n[JOURNAL OUTPUT]")
journal_path = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_path, exist_ok=True)

journal_entry = {
    "run_id": run_id,
    "timestamp": now_iso(),
    "status": "completed",
    "fix_applied": "Re-processed 11 journals from first run with improved signal extraction (finch sources.* string format, findings[].type=critical, mentor eval coverage)",
    "journals_reprocessed": len(to_reprocess),
    "new_events": len(new_events),
    "total_events": len(deduped_events),
    "new_lessons": len(new_lessons),
    "new_shifts": len(new_proposals),
    "active_shifts": active_count + len(new_proposals),
    "signal_summary": {}
}
for evt in new_events:
    st = evt.get("signal_type", "unknown")
    journal_entry["signal_summary"][st] = journal_entry["signal_summary"].get(st, 0) + 1

with open(os.path.join(journal_path, f"{run_id}.json"), 'w') as f:
    json.dump(journal_entry, f, indent=2)
print(f"  Journal written")

# === DECISION LOG ===
decisions = read_jsonl(DECISIONS_FILE)
decisions.append({
    "timestamp": now_iso(),
    "decision": f"Praxis journal ingest (fixed) {run_id}",
    "reasoning": f"Re-processed 11 journals with improved extraction. First run missed finch sources.* string-format signals and findings[].type=critical. Found {len(new_events)} new events, {len(new_lessons)} lessons, {len(new_proposals)} shifts.",
    "outcome": "completed",
    "new_events": len(new_events),
    "new_lessons": len(new_lessons),
    "new_shifts": len(new_proposals)
})
write_jsonl(DECISIONS_FILE, decisions)

# === SUMMARY ===
print("\n" + "=" * 60)
print("INGEST COMPLETE (FIXED)")
print("=" * 60)
print(f"  Run ID: {run_id}")
print(f"  Journals re-processed: {len(to_reprocess)}")
print(f"  New events: {len(new_events)}")
print(f"  Total events: {len(deduped_events)}")
print(f"  New lessons: {len(new_lessons)}")
print(f"  New shifts: {len(new_proposals)}")
print(f"  Active shifts: {active_count + len(new_proposals)}/12")
print(f"  Signal summary: {journal_entry['signal_summary']}")
