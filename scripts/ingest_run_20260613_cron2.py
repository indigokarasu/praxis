#!/usr/bin/env python3
"""
Praxis Journal Ingest Run — 2026-06-13 Cron #2
Scans all skill journals for new entries, extracts behavioral signals,
records events, extracts lessons, proposes shifts, writes journal.
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone

# === Path Constants ===
DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
JOURNALS_DIR = "/root/.hermes/commons/journals"
JOURNAL_DIR = "/root/.hermes/commons/journals/ocas-praxis"
SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}

EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")
EVIDENCE_FILE = os.path.join(DATA_DIR, "evidence.jsonl")
DEBRIEFS_FILE = os.path.join(DATA_DIR, "debriefs.jsonl")

# === Helpers ===
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
    if mode == 'a':
        with open(path, 'a') as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
    else:
        with open(path, 'w') as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

def append_jsonl(path, record):
    with open(path, 'a') as f:
        f.write(json.dumps(record) + "\n")

# === Noise filter ===
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

# === Signal Extraction ===
def extract_signals(data, canonical):
    signals = []
    summary = ""

    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                s = entry.get("summary", "")
                if isinstance(s, str) and s:
                    summary = s
        return signals, summary

    if not isinstance(data, dict):
        return signals, summary

    # Top-level escalation
    if data.get("escalation_needed") is True:
        signals.append({"type": "escalation", "evidence": "top-level escalation_needed: true"})

    # decision.execution_result.status
    decision = data.get("decision", {})
    if isinstance(decision, dict):
        exec_result = decision.get("execution_result", {})
        if isinstance(exec_result, dict):
            status = exec_result.get("status", "")
            if status in ("error", "partial", "completed_with_errors"):
                signals.append({"type": "execution_error", "evidence": f"execution_result.status={status}"})
        # decision.summary
        d_summary = decision.get("summary", "")
        if isinstance(d_summary, str) and d_summary.strip():
            summary = d_summary
            d_lower = d_summary.lower()
            if any(kw in d_lower for kw in ["fail", "error", "timeout", "wrong", "broken", "unreachable"]):
                signals.append({"type": "failure_keyword", "evidence": "decision.summary contains failure keyword"})
            if any(kw in d_lower for kw in ["oauth", "token", "401", "auth", "credential"]):
                signals.append({"type": "auth_failure", "evidence": "decision.summary contains auth keyword"})
        # decision.reasoning_summary (forge status-less variant)
        r_summary = decision.get("reasoning_summary", "")
        if isinstance(r_summary, str) and r_summary.strip() and not summary:
            summary = r_summary
            r_lower = r_summary.lower()
            if any(kw in r_lower for kw in ["fail", "error", "timeout", "wrong", "broken", "unreachable"]):
                signals.append({"type": "failure_keyword", "evidence": "decision.reasoning_summary contains failure keyword"})

    # Top-level status
    status = data.get("status", "")
    if isinstance(status, str) and status in ("error", "partial", "completed_with_errors"):
        signals.append({"type": "execution_error", "evidence": f"top-level status={status}"})

    # Top-level summary (string)
    top_summary = data.get("summary", "")
    if isinstance(top_summary, str) and top_summary.strip() and not summary:
        summary = top_summary
        s_lower = top_summary.lower()
        if any(kw in s_lower for kw in ["fail", "error", "timeout", "wrong", "broken", "unreachable"]):
            signals.append({"type": "failure_keyword", "evidence": "top-level summary contains failure keyword"})
        if any(kw in s_lower for kw in ["oauth", "token", "401", "auth", "credential"]):
            signals.append({"type": "auth_failure", "evidence": "top-level summary contains auth keyword"})

    # actions_taken
    actions_taken = data.get("actions_taken", [])
    if isinstance(actions_taken, list):
        for action in actions_taken:
            if isinstance(action, dict):
                outcome = action.get("outcome", "")
                if isinstance(outcome, str) and outcome.lower() in ("error", "failure", "failed", "correction"):
                    signals.append({"type": "correction", "evidence": f"actions_taken.outcome={outcome}"})

    # fixes_applied
    fixes = data.get("fixes_applied", 0)
    if isinstance(fixes, int) and fixes > 0:
        signals.append({"type": "correction", "evidence": f"fixes_applied={fixes}"})

    # checks.fixes_applied
    checks = data.get("checks", {})
    if isinstance(checks, dict):
        check_fixes = checks.get("fixes_applied", 0)
        if isinstance(check_fixes, int) and check_fixes > 0:
            signals.append({"type": "correction", "evidence": f"checks.fixes_applied={check_fixes}"})

    # new_findings[]
    new_findings = data.get("new_findings", [])
    if isinstance(new_findings, list):
        for finding in new_findings:
            if isinstance(finding, dict):
                sev = finding.get("severity", "")
                if sev in ("critical", "high"):
                    signals.append({"type": "escalation", "evidence": f"new_findings severity={sev}"})

    # findings[] (nested)
    findings = data.get("findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict):
                if finding.get("escalation_needed") is True:
                    signals.append({"type": "escalation", "evidence": "findings[].escalation_needed: true"})
                f_status = finding.get("status", "")
                if f_status in ("error", "failed"):
                    signals.append({"type": "execution_error", "evidence": f"findings[].status={f_status}"})
                f_type = finding.get("type", "")
                if f_type == "critical":
                    signals.append({"type": "escalation", "evidence": "findings[].type=critical"})

    # finch: signals.*, sources.*, signal_sources.*, sources_scanned.*
    for key in ["signals", "sources", "signal_sources", "sources_scanned"]:
        src_data = data.get(key, {})
        if isinstance(src_data, dict):
            for src_name, src_val in src_data.items():
                if isinstance(src_val, dict):
                    src_status = src_val.get("status", "")
                    if src_status in ("blocked", "error", "failed", "inactive"):
                        signals.append({"type": "execution_error", "evidence": f"{key}.{src_name}.status={src_status}"})
                    src_error = src_val.get("error", "")
                    if isinstance(src_error, str) and src_error and src_error != "none":
                        signals.append({"type": "execution_error", "evidence": f"{key}.{src_name}.error={src_error}"})
                    new_issues = src_val.get("new_issues_since_last_scan", src_val.get("new_issues", []))
                    if isinstance(new_issues, list) and new_issues:
                        for issue in new_issues:
                            signals.append({"type": "execution_error", "evidence": f"{key}.{src_name}.new_issues: {issue}"})
                elif isinstance(src_val, str):
                    val_lower = src_val.lower()
                    if any(kw in val_lower for kw in ["unreachable", "error", "failed", "blocked", "cannot check", "unable to verify", "mcp unreachable"]):
                        signals.append({"type": "execution_error", "evidence": f"{key}.{src_name}: {src_val}"})

    # result field
    result = data.get("result", "")
    if isinstance(result, str) and result.lower() in ("error", "failed", "failure"):
        signals.append({"type": "execution_error", "evidence": f"result={result}"})

    # === Noise filter ===
    if summary and signals:
        if should_suppress_summary_signals(summary, signals):
            signals = [s for s in signals if s["type"] not in ("failure_keyword", "auth_failure")]

    return signals, summary

# === Failure Phase Tagging ===
def tag_failure_phase(signal_type, evidence, summary):
    summary_lower = summary.lower() if isinstance(summary, str) else ""
    if any(kw in summary_lower for kw in ["should have", "before", "wrong approach", "didn't check", "missing prerequisite"]):
        return "planning"
    if signal_type in ("execution_error", "escalation"):
        return "execution"
    if any(kw in summary_lower for kw in ["too verbose", "wrong format", "just give me", "make it concise", "don't explain"]):
        return "response"
    if signal_type == "failure_keyword":
        return "execution"
    if signal_type == "correction":
        return "execution"
    return "execution"

# === MAIN ===
now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
run_id = f"r_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"

print(f"=== Praxis Journal Ingest Run ===")
print(f"Run ID: {run_id}")
print(f"Time: {now.isoformat()}")
print(f"Scan window: {yesterday} + {today}")

# Step 1: Deduplicate journals_evaluated.jsonl
eval_entries = read_jsonl(EVAL_FILE)
seen_ids = set()
deduped = []
for entry in eval_entries:
    jid = entry.get("journal_id", "")
    if jid not in seen_ids:
        seen_ids.add(jid)
        deduped.append(entry)
if len(deduped) < len(eval_entries):
    print(f"  Deduped journals_evaluated: {len(eval_entries)} -> {len(deduped)}")
    write_jsonl(EVAL_FILE, deduped)

# Step 1b: Compact if >5000 entries
if len(deduped) > 5000:
    cutoff = (now - timedelta(days=30)).isoformat()
    compacted = [e for e in deduped if e.get("evaluated_at", "9999") > cutoff or not e.get("evaluated_at")]
    removed = len(deduped) - len(compacted)
    if removed > 0:
        print(f"  Compacted: removed {removed} entries older than 30 days")
        write_jsonl(EVAL_FILE, compacted)
        deduped = compacted

# Step 2: Scan filesystem for journal files
all_files = []
for root_dir, dirs, files in os.walk(JOURNALS_DIR):
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    parts = root_dir.replace(JOURNALS_DIR, "").strip('/').split('/')
    if parts and parts[0] in SKIP_DIRS:
        continue
    for fname in files:
        if not fname.endswith('.json'):
            continue
        full_path = os.path.join(root_dir, fname)
        rel_path = os.path.relpath(full_path, JOURNALS_DIR)
        path_parts = rel_path.split('/')
        if len(path_parts) >= 2:
            date_dir = path_parts[1] if len(path_parts) > 1 else ""
            if date_dir in (today, yesterday):
                skill = path_parts[0]
                canonical = f"{skill}/{date_dir}/{fname}"
                all_files.append((canonical, full_path))

print(f"  Total journal files in window: {len(all_files)}")

# Step 3: Compute unevaluated set
seen_ids = {e.get("journal_id", "") for e in deduped}
unevaluated = [(c, p) for c, p in all_files if c not in seen_ids and os.path.exists(p)]
print(f"  Unevaluated journals: {len(unevaluated)}")

# Step 3b: Supplemental mtime scan for last 48h
MTIME_WINDOW = 48 * 3600
now_ts = time.time()
all_files_supplemental = []
for root_dir, dirs, files in os.walk(JOURNALS_DIR):
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    parts = root_dir.replace(JOURNALS_DIR, "").strip('/').split('/')
    if parts and parts[0] in SKIP_DIRS:
        continue
    for fname in files:
        if not fname.endswith('.json'):
            continue
        full_path = os.path.join(root_dir, fname)
        if not os.path.exists(full_path):
            continue
        if now_ts - os.path.getmtime(full_path) > MTIME_WINDOW:
            continue
        rel_path = os.path.relpath(full_path, JOURNALS_DIR)
        if rel_path not in seen_ids:
            all_files_supplemental.append((rel_path, full_path))

# Merge supplemental (avoid duplicates)
existing_canonicals = {c for c, p in unevaluated}
for c, p in all_files_supplemental:
    if c not in existing_canonicals and os.path.exists(p):
        unevaluated.append((c, p))
        existing_canonicals.add(c)

if all_files_supplemental:
    print(f"  Supplemental mtime scan added: {len(all_files_supplemental)} files")

# Step 4: Process unevaluated journals
new_events = []
eval_updates = []
journals_with_signals = []
journals_no_signal = []

for canonical, full_path in unevaluated:
    try:
        with open(full_path, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"  ERROR reading {canonical}: {e}")
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "read_error",
            "signals_found": [],
            "reason": str(e)
        })
        continue

    signals, summary = extract_signals(data, canonical)

    if not signals:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })
        journals_no_signal.append(canonical)
        continue

    journals_with_signals.append(canonical)

    skill = canonical.split('/')[0]

    for sig in signals:
        failure_phase = tag_failure_phase(sig["type"], sig.get("evidence", ""), summary)
        event = {
            "event_id": f"evt_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}",
            "timestamp": now.isoformat(),
            "domain": skill,
            "context_summary": sig.get("evidence", "")[:200],
            "outcome_type": "failure" if sig["type"] in ("execution_error", "escalation", "failure_keyword") else "observation",
            "outcome_summary": summary[:200] if summary else sig.get("evidence", "")[:200],
            "evidence": [f"canonical: {canonical}", f"signal_type: {sig['type']}"],
            "failure_phase": failure_phase,
            "user_relevance": "agent_only",
            "source_journal": canonical,
            "signal_type": sig["type"],
            "recorded_at": now.isoformat()
        }
        new_events.append(event)

print(f"  Journals with signals: {len(journals_with_signals)}")
print(f"  Journals with no signal: {len(journals_no_signal)}")
print(f"  New events to record: {len(new_events)}")

# Step 4a: Write new events
truly_new = []
if new_events:
    existing_events = read_jsonl(EVENTS_FILE)
    existing_sources = {e.get("source_journal", "") for e in existing_events}

    for evt in new_events:
        src = evt.get("source_journal", "")
        if src in existing_sources:
            print(f"  Skipping duplicate event for {src}")
            continue
        existing_sources.add(src)
        truly_new.append(evt)
        append_jsonl(EVENTS_FILE, evt)

    print(f"  Events written (after dedup): {len(truly_new)}")
else:
    print(f"  No new events to write")

# Step 4b: Write eval_updates
for eu in eval_updates:
    append_jsonl(EVAL_FILE, eu)
print(f"  Eval updates written: {len(eval_updates)}")

# Step 5: Lesson extraction (two-pass)
all_events = read_jsonl(EVENTS_FILE)
meaningful_events = [e for e in all_events if e.get("signal_type") not in ("unknown", "?", None, "", "observation")]

groups = {}
for evt in meaningful_events:
    key = (evt.get("signal_type", ""), evt.get("failure_phase", ""))
    if key[0] and key[1]:
        if key not in groups:
            groups[key] = []
        groups[key].append(evt)

lesson_groups = {k: v for k, v in groups.items() if len(v) >= 2}
print(f"\n=== Lesson Extraction ===")
print(f"  Total meaningful events: {len(meaningful_events)}")
print(f"  Groups with 2+ events: {len(lesson_groups)}")

existing_lessons = read_jsonl(LESSONS_FILE)
existing_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_groups.add(key)

new_lessons = []
for (sig_phase, phase), events in lesson_groups.items():
    if (sig_phase, phase) in existing_groups:
        print(f"  Skipping duplicate lesson: signal_type={sig_phase}, phase={phase}")
        continue
    existing_groups.add((sig_phase, phase))

    event_summaries = [e.get("context_summary", "")[:100] for e in events[:3]]
    lesson_text = f"[LESSON] What: {len(events)} events of type '{sig_phase}' in {phase} phase. Why: Repeated pattern across {len(events)} occurrences. When: During {phase} phase of {events[0].get('domain', 'unknown')} operations."

    lesson = {
        "lesson_id": f"les_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}",
        "signal_type": sig_phase,
        "failure_phase": phase,
        "lesson_text": lesson_text,
        "confidence": "high",
        "event_count": len(events),
        "events_referenced": [get_event_id(e) for e in events],
        "causal_grounding": {
            "what": f"{len(events)} events of type '{sig_phase}' in {phase} phase",
            "why": f"Repeated pattern across {len(events)} occurrences",
            "when": f"During {phase} phase"
        },
        "domains_affected": list(set(e.get("domain", "unknown") for e in events)),
        "recorded_at": now.isoformat()
    }
    new_lessons.append(lesson)

if new_lessons:
    for lesson in new_lessons:
        append_jsonl(LESSONS_FILE, lesson)
    print(f"  New lessons written: {len(new_lessons)}")
else:
    print(f"  No new lessons to write")

# Step 6: Shift proposal
print(f"\n=== Shift Proposal ===")
all_lessons = read_jsonl(LESSONS_FILE)
all_shifts = read_jsonl(SHIFTS_FILE)

# Get active shifts
active_shifts = [s for s in all_shifts if s.get("status") == "active"]
print(f"  Active shifts: {len(active_shifts)}/12")

# Check for new lessons that need shifts
new_shift_proposals = []
for lesson in new_lessons:
    lesson_domains = lesson.get("domains_affected", [])
    lesson_domain = lesson_domains[0] if lesson_domains else "unknown"
    lesson_phase = lesson.get("failure_phase", "execution")
    lesson_sig = lesson.get("signal_type", "")

    # Check domain+phase overlap with active shifts
    overlap = False
    for s in active_shifts:
        if s.get("domain") == lesson_domain and s.get("failure_phase") == lesson_phase:
            overlap = True
            print(f"  Shift overlap detected for {lesson_domain}/{lesson_phase} — skipping")
            break

    if not overlap and len(active_shifts) < 12:
        shift_text = f"When {lesson_sig} occurs in {lesson_phase} phase ({lesson_domain}), apply lesson: {lesson.get('lesson_text', '')[:100]}"
        shift = {
            "shift_id": f"shf_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}",
            "status": "active",
            "shift_text": shift_text,
            "lesson_id": lesson.get("lesson_id", ""),
            "signal_type": lesson_sig,
            "failure_phase": lesson_phase,
            "domain": lesson_domain,
            "confidence": lesson.get("confidence", "medium"),
            "reinforcement_count": 0,
            "proposed_at": now.isoformat(),
            "activated_at": now.isoformat()
        }
        new_shift_proposals.append(shift)
        active_shifts.append(shift)  # Track to prevent duplicate in same run

if new_shift_proposals:
    for shift in new_shift_proposals:
        append_jsonl(SHIFTS_FILE, shift)
    print(f"  New shifts activated: {len(new_shift_proposals)}")
else:
    print(f"  No new shifts to activate")

# Step 7: Write evidence record
evidence_record = {
    "run_id": run_id,
    "timestamp": now.isoformat(),
    "journals_scanned": len(all_files) + len(all_files_supplemental),
    "journals_unevaluated": len(unevaluated) + len(all_files_supplemental),
    "journals_evaluated_this_run": len(eval_updates),
    "journals_with_signals": len(journals_with_signals),
    "journals_no_signal": len(journals_no_signal),
    "new_events": len(truly_new),
    "new_lessons": len(new_lessons),
    "new_shifts": len(new_shift_proposals),
    "active_shifts_total": len(active_shifts),
    "not_activity_reason": "routine_scan" if not truly_new else "signals_found"
}
append_jsonl(EVIDENCE_FILE, evidence_record)

# Step 8: Write Praxis journal
journal_dir = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_dir, exist_ok=True)
journal_record = {
    "run_id": run_id,
    "timestamp": now.isoformat(),
    "command": "praxis:journal_ingest",
    "mode": "cron",
    "source": "praxis:journal_ingest cron job",
    "result": "completed",
    "summary": f"Ingest complete. {len(eval_updates)} journals evaluated. {len(journals_with_signals)} with signals. {len(truly_new)} new events. {len(new_lessons)} new lessons. {len(new_shift_proposals)} new shifts. Active shifts: {len(active_shifts)}/12.",
    "journals_evaluated": len(eval_updates),
    "new_events": len(truly_new),
    "new_lessons": len(new_lessons),
    "new_shifts": len(new_shift_proposals),
    "active_shifts": len(active_shifts),
    "signals_found": [s for j in journals_with_signals for s in [j]],
    "journals_no_signal": journals_no_signal,
    "journals_with_signals_list": journals_with_signals
}
journal_path = os.path.join(journal_dir, f"{run_id}.json")
with open(journal_path, 'w') as f:
    json.dump(journal_record, f, indent=2)

print(f"\n=== Ingest Complete ===")
print(f"  Run ID: {run_id}")
print(f"  Journals evaluated: {len(eval_updates)}")
print(f"  New events: {len(truly_new)}")
print(f"  New lessons: {len(new_lessons)}")
print(f"  New shifts: {len(new_shift_proposals)}")
print(f"  Active shifts: {len(active_shifts)}/12")
print(f"  Journal written: {journal_path}")
