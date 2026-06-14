#!/usr/bin/env python3
"""
Praxis Journal Ingest — 2026-06-13 Cron Run
Scans all skill journals for new entries, extracts behavioral signals,
records events, extracts lessons, proposes shifts, and writes journal.
"""

import json
import os
from datetime import datetime, timedelta, timezone

# === Path Constants ===
JOURNALS_DIR = "/root/.hermes/commons/journals"
DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")
JOURNAL_DIR = os.path.join(JOURNALS_DIR, "ocas-praxis")

SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%m")
# Fix: correct yesterday calc
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

run_id = f"r_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"

# === Schema Normalization Helpers ===
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

# === Noise Filter Constants ===
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy"
]

FORGE_NO_OP_RESULTS = {"no_op", "clean"}

# === Step 1: Deduplicate journals_evaluated.jsonl ===
print("=" * 60)
print("PRAXIS JOURNAL INGEST — 2026-06-13 Cron Run")
print("=" * 60)

eval_entries = []
if os.path.exists(EVAL_FILE):
    seen_ids = set()
    with open(EVAL_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            jid = entry.get("journal_id", "")
            if jid and jid not in seen_ids:
                seen_ids.add(jid)
                eval_entries.append(entry)
            elif jid and jid in seen_ids:
                pass  # duplicate, skip
    with open(EVAL_FILE, 'w') as f:
        for e in eval_entries:
            f.write(json.dumps(e) + "\n")

print(f"\nEvaluated journals loaded: {len(eval_entries)}")

# Compact if >5000
if len(eval_entries) > 5000:
    cutoff = (now - timedelta(days=30)).isoformat()
    compacted = [e for e in eval_entries
                 if e.get("evaluated_at", "9999") > cutoff
                 or not e.get("evaluated_at")]
    removed = len(eval_entries) - len(compacted)
    if removed > 0:
        eval_entries = compacted
        with open(EVAL_FILE, 'w') as f:
            for e in eval_entries:
                f.write(json.dumps(e) + "\n")
        print(f"  Compacted: removed {removed} entries older than 30 days")

# === Step 2: Scan filesystem for journal files ===
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

print(f"Journal files found (today+yesterday): {len(all_files)}")

# === Step 3: Compute unevaluated set ===
seen_ids = {e.get("journal_id", "") for e in eval_entries}
unevaluated = [(c, p) for c, p in all_files if c not in seen_ids and os.path.exists(p)]

print(f"Unevaluated journals: {len(unevaluated)}")
for c, p in unevaluated:
    print(f"  → {c}")

# === Signal Extraction ===
new_events = []
eval_updates = []
all_new_signals = []

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

for canonical, fpath in unevaluated:
    try:
        with open(fpath, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"  ERROR reading {canonical}: {e}")
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "read_error",
            "signals_found": [],
            "reason": f"Cannot read/parse: {e}"
        })
        continue

    signals = []
    skill = canonical.split("/")[0]

    # --- Top-level checks ---
    # Check escalation_needed
    if data.get("escalation_needed") is True:
        signals.append({"type": "escalation", "source": "top_level", "detail": "escalation_needed: true"})

    # Check top-level status
    top_status = data.get("status", "")
    if isinstance(top_status, str):
        if top_status in ("error", "failed"):
            signals.append({"type": "execution_error", "source": "top_level_status", "detail": f"status: {top_status}"})
        elif top_status in ("partial", "completed_with_errors"):
            signals.append({"type": "execution_error", "source": "top_level_status", "detail": f"status: {top_status}"})

    # Check decision.execution_result
    decision = data.get("decision", {})
    if isinstance(decision, dict):
        exec_result = decision.get("execution_result", {})
        if isinstance(exec_result, dict):
            exec_status = exec_result.get("status", "")
            if exec_status in ("error", "failed"):
                signals.append({"type": "execution_error", "source": "decision.exec_result", "detail": f"exec_status: {exec_status}"})
            elif exec_status == "partial":
                signals.append({"type": "execution_error", "source": "decision.exec_result", "detail": "exec_status: partial"})

        # Check decision.summary
        summary = decision.get("summary", "")
        if isinstance(summary, dict):
            summary_str = json.dumps(summary).lower()
        elif isinstance(summary, str) and summary.strip():
            summary_str = summary.lower()
        else:
            summary_str = ""

        if summary_str:
            failure_keywords = ["error", "failed", "failure", "timeout", "broken", "crash", "exception", "oom", "killed"]
            auth_keywords = ["oauth", "token expired", "401", "unauthorized", "auth fail", "revoked"]
            for kw in failure_keywords:
                if kw in summary_str:
                    signals.append({"type": "failure_keyword", "source": "decision.summary", "detail": f"keyword: {kw}"})
                    break
            for kw in auth_keywords:
                if kw in summary_str:
                    signals.append({"type": "auth_failure", "source": "decision.summary", "detail": f"keyword: {kw}"})
                    break

    # Check top-level summary
    top_summary = data.get("summary", "")
    summary = ""  # Initialize for later use
    if isinstance(top_summary, dict):
        summary_str = json.dumps(top_summary).lower()
        summary = json.dumps(top_summary)
    elif isinstance(top_summary, str) and top_summary.strip():
        summary_str = top_summary.lower()
        summary = top_summary
    else:
        summary_str = ""
        summary = ""

    if summary_str:
        failure_keywords = ["error", "failed", "failure", "timeout", "broken", "crash", "exception", "oom", "killed"]
        auth_keywords = ["oauth", "token expired", "401", "unauthorized", "auth fail", "revoked"]
        for kw in failure_keywords:
            if kw in summary_str:
                signals.append({"type": "failure_keyword", "source": "top_summary", "detail": f"keyword: {kw}"})
                break
        for kw in auth_keywords:
            if kw in summary_str:
                signals.append({"type": "auth_failure", "source": "top_summary", "detail": f"keyword: {kw}"})
                break

    # Check actions_taken
    actions = data.get("actions_taken", [])
    if isinstance(actions, list):
        for action in actions:
            if isinstance(action, dict):
                outcome = action.get("outcome", "")
                if isinstance(outcome, str) and outcome.lower() in ("error", "failure", "failed"):
                    signals.append({"type": "execution_error", "source": "actions_taken", "detail": f"outcome: {outcome}"})

    # Check fixes_applied
    fixes = data.get("fixes_applied", 0)
    if isinstance(fixes, int) and fixes > 0:
        signals.append({"type": "correction", "source": "fixes_applied", "detail": f"fixes_applied: {fixes}"})

    checks = data.get("checks", {})
    if isinstance(checks, dict) and checks.get("fixes_applied", 0) > 0:
        signals.append({"type": "correction", "source": "checks", "detail": f"checks.fixes_applied: {checks['fixes_applied']}"})

    # Check new_findings / findings arrays
    for findings_key in ["new_findings", "findings"]:
        findings = data.get(findings_key, [])
        if isinstance(findings, list):
            for finding in findings:
                if isinstance(finding, dict):
                    if finding.get("escalation_needed") is True:
                        signals.append({"type": "escalation", "source": f"{findings_key}[]", "detail": f"title: {finding.get('title', '?')}"})
                    fstatus = finding.get("status", "")
                    if fstatus in ("error", "failed"):
                        signals.append({"type": "execution_error", "source": f"{findings_key}[]", "detail": f"status: {fstatus}"})
                    detail_str = json.dumps(finding).lower()
                    if any(kw in detail_str for kw in ["fix applied", "corrected", "resolved", "patched"]):
                        signals.append({"type": "correction", "source": f"{findings_key}[]", "detail": f"fix action in finding"})

    # Check escalation arrays
    escalations = data.get("escalations", [])
    if isinstance(escalations, list):
        for esc in escalations:
            if isinstance(esc, dict) and esc.get("type") == "new_item":
                signals.append({"type": "escalation", "source": "escalations[]", "detail": f"new escalation: {esc.get('id', '?')}"})

    # Check escalation_flagged — these are NOT new escalations (known issues tracking)
    # SKIP: escalation_flagged arrays track previously-known issues

    # Finch-specific checks
    if skill == "ocas-finch":
        signals_data = data.get("signals", {})
        if isinstance(signals_data, dict):
            cron_data = signals_data.get("cron", {})
            if isinstance(cron_data, dict):
                new_errors = cron_data.get("new_errors", [])
                if isinstance(new_errors, list):
                    for err in new_errors:
                        if isinstance(err, dict):
                            signals.append({"type": "cron_errors", "source": "finch.signals.cron.new_errors",
                                           "detail": f"job: {err.get('job', '?')}, msg: {err.get('message', '?')}"[:200]})
                breakdown = cron_data.get("error_breakdown", {})
                if isinstance(breakdown, dict):
                    for k in ["http_401", "http_429", "script_path_blocked", "stale_401"]:
                        if breakdown.get(k, 0) > 0:
                            signals.append({"type": "cron_errors", "source": "finch.signals.cron.error_breakdown",
                                           "detail": f"{k}: {breakdown[k]}"})
            tasks_added = data.get("tasks_added", [])
            if isinstance(tasks_added, list):
                for t in tasks_added:
                    t_lower = str(t).lower()
                    if any(kw in t_lower for kw in ["error", "failed", "broken"]):
                        signals.append({"type": "failure_keyword", "source": "finch.tasks_added",
                                       "detail": f"error task: {str(t)[:150]}"})

    # Forge-specific checks
    if skill == "ocas-forge":
        result_val = data.get("result", "")
        if isinstance(result_val, str):
            r = result_val.lower().strip()
            # no_op / clean / "clean — ..." are healthy
            is_no_op = r in FORGE_NO_OP_RESULTS or r.startswith("clean")
            if not is_no_op and r not in ("ok", "success", "complete", "completed", ""):
                # Check for real failures
                if any(kw in r for kw in ["error", "failed", "failure", "timeout", "exception"]):
                    signals.append({"type": "execution_error", "source": "forge.result", "detail": f"result: {result_val}"})

    # Spot-specific: observation with transient platform phrases → no_signal
    if skill == "ocas-spot":
        jtype = data.get("type", "")
        jsummary = data.get("summary", "")
        jsummary_str = jsummary if isinstance(jsummary, str) else json.dumps(jsummary) if isinstance(jsummary, dict) else ""
        skip_signals = False
        if jtype == "observation":
            transient_phrases = ["skipped", "permanently broken", "dead watch", "expired", "no new availability"]
            for phrase in transient_phrases:
                if phrase in jsummary_str.lower():
                    skip_signals = True
                    break
        if skip_signals:
            signals = []
        elif jtype == "observation" and not signals:
            # Routine observation, no real signals
            pass

    # Apply semantic suppression for summary-derived signals only
    if summary_str and signals:
        if should_suppress_summary_signals(summary_str, signals):
            filtered = [s for s in signals if s["type"] not in ("failure_keyword", "auth_failure")]
            suppressed_count = len(signals) - len(filtered)
            signals = filtered
            if suppressed_count > 0:
                print(f"  Suppressed {suppressed_count} summary-derived signals from {canonical}")

    # --- Record events for real signals ---
    if signals:
        for sig in signals:
            event = {
                "event_id": f"evt_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}",
                "source_journal": canonical,
                "signal_type": sig["type"],
                "domain": skill,
                "evidence": sig["detail"],
                "failure_phase": "execution",  # default
                "recorded_at": now.isoformat(),
                "confidence": "medium"
            }
            # Failure-phase tagging
            detail_lower = sig["detail"].lower()
            if any(kw in detail_lower for kw in ["should have", "before", "wrong approach", "didn't check", "missing prerequisite"]):
                event["failure_phase"] = "planning"
            elif any(kw in detail_lower for kw in ["too verbose", "wrong format", "just give me", "make it concise", "don't explain"]):
                event["failure_phase"] = "response"

            new_events.append(event)
            all_new_signals.append(sig["type"])

        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "event_recorded",
            "signals_found": [s["type"] for s in signals],
            "reason": f"Extracted {len(signals)} signal(s): {[s['type'] for s in signals]}"
        })
        print(f"  ✓ {canonical}: {len(signals)} signals → {[s['type'] for s in signals]}")
    else:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })
        print(f"  ✓ {canonical}: no signals")

print(f"\nNew events extracted: {len(new_events)}")
print(f"Signal types: {dict((s, all_new_signals.count(s)) for s in set(all_new_signals))}")

# === Step 4: Write new events to events.jsonl ===
if new_events:
    existing_events = []
    if os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing_events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    all_events = existing_events + new_events

    # Post-write dedup by (source_journal, signal_type)
    deduped = {}
    for evt in all_events:
        key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
        if key not in deduped:
            deduped[key] = evt

    with open(EVENTS_FILE, 'w') as f:
        for evt in deduped.values():
            f.write(json.dumps(evt) + "\n")

    print(f"Events written: {len(all_events)} → deduped to {len(deduped)}")
    all_events = list(deduped.values())
else:
    all_events = []
    if os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        all_events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    print(f"No new events. Total events on disk: {len(all_events)}")

# === Step 5: Lesson Extraction (Two-Pass) ===
print("\n--- LESSON EXTRACTION ---")

# Filter to meaningful events
meaningful_types = {"auth_failure", "escalation", "execution_error", "correction", "cron_errors", "failure_keyword"}
meaningful_events = [e for e in all_events if e.get("signal_type") in meaningful_types]

# Group by (signal_type, failure_phase)
from collections import defaultdict
groups = defaultdict(list)
for evt in meaningful_events:
    key = (evt.get("signal_type", "?"), evt.get("failure_phase", "execution"))
    groups[key].append(evt)

# Extract lesson stubs for groups with 2+ events
new_lessons_pass1 = []
for (sig_type, phase), events in groups.items():
    if len(events) >= 2:
        lesson_text = f"[{sig_type}] Pattern detected: {len(events)} events of type '{sig_type}' in {phase} phase."
        lesson = {
            "lesson_id": f"les_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}",
            "signal_type": sig_type,
            "failure_phase": phase,
            "lesson_text": lesson_text,
            "event_count": len(events),
            "events_ref": [get_event_id(e) for e in events[:10]],
            "confidence": "low",
            "extracted_at": now.isoformat()
        }
        new_lessons_pass1.append(lesson)

print(f"Pass 1 lesson stubs: {len(new_lessons_pass1)}")

# Pass 2: Causal grounding upgrade
existing_lessons = []
if os.path.exists(LESSONS_FILE):
    with open(LESSONS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    existing_lessons.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

# Lesson content dedup by (signal_type, failure_phase)
existing_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_groups.add(key)

filtered_new_lessons = []
for lesson in new_lessons_pass1:
    key = (lesson.get("signal_type", ""), lesson.get("failure_phase", ""))
    if key in existing_groups:
        print(f"  Skipping duplicate lesson: signal_type={key[0]}, phase={key[1]}")
        continue
    existing_groups.add(key)
    filtered_new_lessons.append(lesson)

# Add causal grounding
for lesson in filtered_new_lessons:
    events_in_group = groups.get((lesson["signal_type"], lesson["failure_phase"]), [])
    sources = list(set(e.get("source_journal", "?") for e in events_in_group[:5]))
    lesson["causal_grounding"] = {
        "what": f"Recurring {lesson['signal_type']} events ({lesson['event_count']} occurrences) in {lesson['failure_phase']} phase",
        "why": f"Observed across {len(sources)} source journal(s): {', '.join(sources[:3])}",
        "when": f"During {lesson['failure_phase']} phase of skill execution"
    }
    lesson["confidence"] = "high"

print(f"Pass 2 lessons with causal grounding: {len(filtered_new_lessons)}")

all_lessons = existing_lessons + filtered_new_lessons
with open(LESSONS_FILE, 'w') as f:
    for l in all_lessons:
        f.write(json.dumps(l) + "\n")

print(f"Total lessons on disk: {len(all_lessons)}")

# === Step 6: Shift Proposal & Activation ===
print("\n--- SHIFT PROPOSAL & ACTIVATION ---")

existing_shifts = []
if os.path.exists(SHIFTS_FILE):
    with open(SHIFTS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    existing_shifts.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

active_shifts = [s for s in existing_shifts if s.get("status") == "active"]
proposed_shifts = [s for s in existing_shifts if s.get("status") == "proposed"]

# Build covered lesson IDs from active/proposed shifts
covered_lesson_ids = set()
for s in existing_shifts:
    if s.get("status") in ("active", "proposed"):
        for field in ["lesson_id", "lesson_ref", "source_lesson", "source_lesson_ids"]:
            val = s.get(field)
            if val:
                if isinstance(val, list):
                    covered_lesson_ids.update(val)
                elif isinstance(val, str):
                    covered_lesson_ids.add(val)

print(f"Active shifts: {len(active_shifts)}, Proposed: {len(proposed_shifts)}")
print(f"Covered lesson IDs: {len(covered_lesson_ids)}")

# Propose shifts for uncovered high-confidence lessons
new_proposals = []
for lesson in all_lessons:
    lid = get_lesson_id(lesson)
    if lesson.get("confidence") == "high" and lid not in covered_lesson_ids and lid:
        # Check domain+phase overlap with active shifts
        lesson_domain = lesson.get("signal_type", "")
        lesson_phase = lesson.get("failure_phase", "execution")
        overlap = False
        for s in active_shifts:
            s_domain = s.get("domain", "")
            s_phase = get_failure_phase(s)
            if s_domain == lesson_domain and s_phase == lesson_phase:
                overlap = True
                # Reinforce active shift
                s["reinforcement_count"] = s.get("reinforcement_count", 0) + 1
                s["last_reinforced"] = now.isoformat()
                break

        if not overlap:
            proposal = {
                "shift_id": f"shf_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}",
                "lesson_id": lid,
                "shift_text": f"In {lesson_phase} phase: address recurring {lesson_domain} patterns",
                "domain": lesson_domain,
                "failure_phase": lesson_phase,
                "status": "proposed",
                "proposed_at": now.isoformat()
            }
            new_proposals.append(proposal)
            covered_lesson_ids.add(lid)

print(f"New shift proposals: {len(new_proposals)}")

# Activate proposals if under cap
ACTIVE_CAP = 12
newly_activated = 0
for proposal in new_proposals:
    if len(active_shifts) < ACTIVE_CAP:
        proposal["status"] = "active"
        proposal["activated_at"] = now.isoformat()
        active_shifts.append(proposal)
        newly_activated += 1
        print(f"  Activated: {proposal['domain']} ({proposal['failure_phase']})")
    else:
        proposed_shifts.append(proposal)
        print(f"  Left proposed (at cap): {proposal['domain']} ({proposal['failure_phase']})")

# Rewrite shifts file with all shifts
all_shifts = active_shifts + proposed_shifts + [s for s in existing_shifts if s.get("status") not in ("active", "proposed")]
with open(SHIFTS_FILE, 'w') as f:
    for s in all_shifts:
        f.write(json.dumps(s) + "\n")

print(f"Total shifts: {len(all_shifts)} (active: {len(active_shifts)}, proposed: {len(proposed_shifts)})")
print(f"Newly activated: {newly_activated}")

# === Step 7: Write eval_updates ===
with open(EVAL_FILE, 'a') as f:
    for eu in eval_updates:
        f.write(json.dumps(eu) + "\n")

print(f"\nEval updates written: {len(eval_updates)}")

# === Step 8: Write decisions journal ===
decision_entry = {
    "decision_id": f"dec_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}",
    "timestamp": now.isoformat(),
    "action": "journal_ingest",
    "journals_scanned": len(unevaluated),
    "new_events": len(new_events),
    "new_lessons": len(filtered_new_lessons),
    "new_shifts_activated": newly_activated,
    "total_active_shifts": len(active_shifts),
    "total_events": len(all_events),
    "total_lessons": len(all_lessons),
    "run_id": run_id
}

existing_decisions = []
if os.path.exists(DECISIONS_FILE):
    with open(DECISIONS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    existing_decisions.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

existing_decisions.append(decision_entry)
with open(DECISIONS_FILE, 'w') as f:
    for d in existing_decisions:
        f.write(json.dumps(d) + "\n")

# === Step 9: Write Praxis journal ===
journal_today_dir = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_today_dir, exist_ok=True)
journal_path = os.path.join(journal_today_dir, f"{run_id}.json")

journal_entry = {
    "run_id": run_id,
    "timestamp": now.isoformat(),
    "type": "journal_ingest",
    "summary": f"Ingest completed: {len(unevaluated)} journals scanned, {len(new_events)} events, {len(filtered_new_lessons)} lessons, {newly_activated} shifts activated",
    "entities_observed": [
        {"name": "skill_journals", "type": "system", "count": len(unevaluated), "user_relevance": "system"},
        {"name": "new_events", "type": "outcome", "count": len(new_events), "user_relevance": "system"},
        {"name": "new_lessons", "type": "outcome", "count": len(filtered_new_lessons), "user_relevance": "system"},
        {"name": "active_shifts", "type": "outcome", "count": len(active_shifts), "user_relevance": "system"}
    ],
    "relationships_observed": [
        {"source": "journal_scan", "target": "event_extraction", "type": "produced"},
        {"source": "event_extraction", "target": "lesson_extraction", "type": "informed"},
        {"source": "lesson_extraction", "target": "shift_activation", "type": "proposed"}
    ],
    "preferences_observed": [],
    "decision": {
        "execution_result": {"status": "ok"},
        "summary": f"Ingest run {run_id}: {len(new_events)} new events from {len(unevaluated)} journals, {len(filtered_new_lessons)} new lessons, {newly_activated} shifts activated. Active cap usage: {len(active_shifts)}/12.",
        "payload": {
            "entities_observed": ["skill_journals", "events", "lessons", "shifts"],
            "action_result": {
                "journals_scanned": len(unevaluated),
                "events_recorded": len(new_events),
                "lessons_extracted": len(filtered_new_lessons),
                "shifts_activated": newly_activated
            }
        }
    }
}

with open(journal_path, 'w') as f:
    json.dump(journal_entry, f, indent=2)

print(f"\nPraxis journal written: {journal_path}")

# === Final Summary ===
print("\n" + "=" * 60)
print("INGEST COMPLETE — SUMMARY")
print("=" * 60)
print(f"  Journals scanned:       {len(unevaluated)}")
print(f"  New events:             {len(new_events)}")
print(f"  Signal breakdown:       {dict((s, all_new_signals.count(s)) for s in set(all_new_signals)) if all_new_signals else 'none'}")
print(f"  New lessons:            {len(filtered_new_lessons)}")
print(f"  Total lessons:          {len(all_lessons)}")
print(f"  Shifts activated:       {newly_activated}")
print(f"  Total active shifts:    {len(active_shifts)}/12")
print(f"  Total events on disk:   {len(all_events)}")
print(f"  Run ID:                 {run_id}")
print("=" * 60)
