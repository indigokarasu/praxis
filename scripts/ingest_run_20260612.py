#!/usr/bin/env python3
"""
Praxis Journal Ingest Run — 2026-06-12
Scans skill journals, extracts behavioral signals, records events/lessons/shifts.
"""

import json
import os
from datetime import datetime, timezone, timedelta

# === Path constants (absolute literals — os.path.join strips leading dot) ===
DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
JOURNALS_DIR = "/root/.hermes/commons/journals"
JOURNAL_DIR = "/root/.hermes/commons/journals/ocas-praxis"
SKILL_DIR = "/root/.hermes/profiles/indigo/skills/ocas-praxis"

EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")

SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
SUMMARY_DERIVED_TYPES = {"failure_keyword", "auth_failure"}
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy", "no_op", "no-op", "none_required",
    "no_new_proposals", "clean — no"
]

# === Schema normalization helpers ===
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

def write_jsonl(path, records):
    with open(path, 'w') as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

def append_jsonl(path, records):
    with open(path, 'a') as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

# === Step 1: Deduplicate journals_evaluated.jsonl ===
print("=== Step 1: Deduplicate journals_evaluated.jsonl ===")
eval_entries = read_jsonl(EVAL_FILE)
original_count = len(eval_entries)
seen_ids = {}
for e in eval_entries:
    jid = e.get("journal_id", "")
    if jid not in seen_ids:
        seen_ids[jid] = e
eval_entries = list(seen_ids.values())
if len(eval_entries) < original_count:
    write_jsonl(EVAL_FILE, eval_entries)
    print(f"  Deduped: {original_count} -> {len(eval_entries)} entries")
else:
    print(f"  No duplicates found ({len(eval_entries)} entries)")

# === Step 1b: Compact if >5000 entries ===
if len(eval_entries) > 5000:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    compacted = [e for e in eval_entries
                 if e.get("evaluated_at", "9999") > cutoff
                 or not e.get("evaluated_at")]
    removed = len(eval_entries) - len(compacted)
    if removed > 0:
        eval_entries = compacted
        write_jsonl(EVAL_FILE, eval_entries)
        print(f"  Compacted: removed {removed} entries older than 30 days")
else:
    print(f"  No compaction needed ({len(eval_entries)} entries)")

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
                skill = path_parts[0]
                date_dir = path_parts[1]
                if date_dir in (today, yesterday):
                    canonical = f"{skill}/{date_dir}/{fname}"
                    all_files.append((canonical, full_path))

print(f"  Found {len(all_files)} journal files (today={today}, yesterday={yesterday})")

# === Step 3: Compute unevaluated set ===
print("\n=== Step 3: Compute unevaluated set ===")
seen_eval_ids = {e.get("journal_id", "") for e in eval_entries}
unevaluated = [(c, p) for c, p in all_files if c not in seen_eval_ids and os.path.exists(p)]
print(f"  Unevaluated journals: {len(unevaluated)}")

# === Step 4: Signal extraction ===
print("\n=== Step 4: Signal extraction ===")

new_events = []
eval_updates = []
now = datetime.now(timezone.utc).isoformat()

# Load existing events for dedup
existing_events = read_jsonl(EVENTS_FILE)
existing_event_keys = set()
for e in existing_events:
    sj = e.get("source_journal", "")
    st = e.get("signal_type", "")
    if sj and st:
        existing_event_keys.add((sj, st))

for canonical, fpath in unevaluated:
    print(f"\n  Processing: {canonical}")
    try:
        with open(fpath, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"    ERROR reading file: {e}")
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now,
            "action_taken": "read_error",
            "signals_found": [],
            "reason": f"File read error: {e}"
        })
        continue

    # Handle list-format journals
    if isinstance(data, list):
        data_list = data
    else:
        data_list = [data]

    signals_found = []
    summary = ""
    status = ""

    for entry in data_list:
        if not isinstance(entry, dict):
            continue

        # Extract status from various locations
        status = entry.get("status", "")
        if not status:
            decision = entry.get("decision", {})
            if isinstance(decision, dict):
                exec_result = decision.get("execution_result", {})
                if isinstance(exec_result, dict):
                    status = exec_result.get("status", "")
                if not status:
                    status = decision.get("status", "")

        # Extract summary from various locations
        summary = entry.get("summary", "")
        if not summary:
            decision = entry.get("decision", {})
            if isinstance(decision, dict):
                summary = decision.get("summary", "")
                if not summary:
                    reasoning = decision.get("reasoning_summary", "")
                    if reasoning:
                        summary = reasoning

        # Check escalation_needed
        if entry.get("escalation_needed") is True:
            signals_found.append({"type": "escalation", "source": "top_level"})
            print(f"    Signal: escalation (top_level)")

        # Check findings array
        findings = entry.get("findings", [])
        if isinstance(findings, list):
            for finding in findings:
                if isinstance(finding, dict):
                    if finding.get("escalation_needed") is True:
                        signals_found.append({"type": "escalation", "source": "finding"})
                        print(f"    Signal: escalation (finding)")

        # Check actions_taken
        actions_taken = entry.get("actions_taken", [])
        if isinstance(actions_taken, list):
            for action in actions_taken:
                if isinstance(action, dict):
                    outcome = action.get("outcome", "")
                    if isinstance(outcome, str) and outcome.lower() in ("error", "failure", "failed"):
                        signals_found.append({"type": "execution_error", "source": "actions_taken"})
                        print(f"    Signal: execution_error (actions_taken)")

        # Check fixes_applied
        fixes = entry.get("fixes_applied", 0)
        if fixes and isinstance(fixes, (int, float)) and fixes > 0:
            signals_found.append({"type": "correction", "source": "fixes_applied"})
            print(f"    Signal: correction (fixes_applied={fixes})")

        # Check metrics
        metrics = entry.get("metrics", {})
        if isinstance(metrics, dict):
            fixes_applied = metrics.get("fixes_applied", 0)
            if fixes_applied and fixes_applied > 0:
                signals_found.append({"type": "correction", "source": "metrics.fixes_applied"})
                print(f"    Signal: correction (metrics.fixes_applied={fixes_applied})")

        # Check result field
        result = entry.get("result", "")
        if isinstance(result, str):
            result_lower = result.lower()
            if any(x in result_lower for x in ["error", "fail"]):
                # But suppress if it's a no-op success
                if "no_op" not in result_lower and "no-op" not in result_lower and "clean" not in result_lower:
                    signals_found.append({"type": "failure_keyword", "source": "result"})
                    print(f"    Signal: failure_keyword (result={result})")

        # Check signal_sources (newer finch scans)
        signal_sources = entry.get("signal_sources", {})
        if isinstance(signal_sources, dict):
            for src_name, src_data in signal_sources.items():
                if isinstance(src_data, dict):
                    src_status = src_data.get("status", "")
                    if src_status in ("blocked", "error", "failed", "inactive"):
                        signals_found.append({"type": "execution_error", "source": f"signal_sources.{src_name}"})
                        print(f"    Signal: execution_error (signal_sources.{src_name}={src_status})")
                    src_error = src_data.get("error", "")
                    if src_error and src_error != "none":
                        signals_found.append({"type": "execution_error", "source": f"signal_sources.{src_name}.error"})
                        print(f"    Signal: execution_error (signal_sources.{src_name}.error)")
                    new_issues = src_data.get("new_issues_since_last_scan", src_data.get("new_issues", []))
                    if isinstance(new_issues, list) and len(new_issues) > 0:
                        signals_found.append({"type": "execution_error", "source": f"signal_sources.{src_name}.new_issues"})
                        print(f"    Signal: execution_error (signal_sources.{src_name}.new_issues={len(new_issues)})")

        # Check signals.* (older finch scans)
        signals_block = entry.get("signals", {})
        if isinstance(signals_block, dict):
            for sig_key, sig_data in signals_block.items():
                if isinstance(sig_data, dict):
                    new_errors = sig_data.get("new_errors", [])
                    if isinstance(new_errors, list) and len(new_errors) > 0:
                        signals_found.append({"type": "cron_errors", "source": f"signals.{sig_key}.new_errors"})
                        print(f"    Signal: cron_errors (signals.{sig_key}.new_errors={len(new_errors)})")

    # === Noise filter: semantic suppression for summary-derived signals ===
    if isinstance(summary, str) and signals_found:
        non_summary_signals = [s for s in signals_found if s["type"] not in SUMMARY_DERIVED_TYPES]
        if not non_summary_signals:
            summary_lower = summary.lower()
            suppressed = False
            for phrase in SUPPRESS_PHRASES:
                if phrase in summary_lower:
                    print(f"    SUPPRESSED: all summary-derived signals (phrase: '{phrase}')")
                    signals_found = []
                    suppressed = True
                    break

    # === Noise filter: status-based suppression ===
    if not signals_found:
        # No signals found — mark as no_signal
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now,
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })
        print(f"    -> no_signal (no behavioral signals)")
        continue

    # === Record events for each signal ===
    events_for_this_journal = []
    for sig in signals_found:
        sig_type = sig["type"]
        dedup_key = (canonical, sig_type)
        if dedup_key in existing_event_keys:
            print(f"    SKIP duplicate event: {sig_type}")
            continue

        # Determine failure_phase
        failure_phase = "execution"  # default for error signals
        if sig_type == "escalation":
            failure_phase = "planning"
        elif sig_type == "correction":
            failure_phase = "execution"

        event = {
            "event_id": f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}_{canonical[:8]}",
            "timestamp": now,
            "domain": canonical.split("/")[0],
            "source_journal": canonical,
            "signal_type": sig_type,
            "failure_phase": failure_phase,
            "context_summary": f"Signal from {sig['source']}",
            "outcome_type": "failure" if sig_type in ("execution_error", "cron_errors", "auth_failure", "failure_keyword") else "correction" if sig_type == "correction" else "observation",
            "outcome_summary": f"Signal type {sig_type} detected in {canonical}",
            "evidence": [f"source: {sig['source']}"],
            "user_relevance": "agent_only"
        }
        events_for_this_journal.append(event)
        existing_event_keys.add(dedup_key)
        print(f"    -> Event recorded: {sig_type} (phase={failure_phase})")

    if events_for_this_journal:
        new_events.extend(events_for_this_journal)
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now,
            "action_taken": "event_recorded",
            "signals_found": [s["type"] for s in signals_found],
            "reason": f"Recorded {len(events_for_this_journal)} events"
        })
    else:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now,
            "action_taken": "no_new_events",
            "signals_found": [s["type"] for s in signals_found],
            "reason": "All signals were duplicates"
        })

# === Step 4b: Write new events ===
print(f"\n=== Step 4b: Write events ===")
print(f"  New events to write: {len(new_events)}")
if new_events:
    append_jsonl(EVENTS_FILE, new_events)
    print(f"  Written {len(new_events)} events to {EVENTS_FILE}")

    # Post-write dedup by (source_journal, signal_type)
    all_events = read_jsonl(EVENTS_FILE)
    dedup_map = {}
    for e in all_events:
        key = (e.get("source_journal", ""), e.get("signal_type", ""))
        if key not in dedup_map:
            dedup_map[key] = e
    deduped_events = list(dedup_map.values())
    if len(deduped_events) < len(all_events):
        write_jsonl(EVENTS_FILE, deduped_events)
        print(f"  Post-write dedup: {len(all_events)} -> {len(deduped_events)} events")
    else:
        print(f"  No post-write dedup needed ({len(all_events)} events)")
else:
    print("  No new events to write")

# === Step 4c: Write eval_updates ===
print(f"\n=== Step 4c: Write eval_updates ===")
print(f"  Eval updates to write: {len(eval_updates)}")
if eval_updates:
    append_jsonl(EVAL_FILE, eval_updates)
    print(f"  Written {len(eval_updates)} eval entries")

# === Step 5: Lesson extraction (two-pass) ===
print(f"\n=== Step 5: Lesson extraction ===")

# Re-read events from disk
all_events = read_jsonl(EVENTS_FILE)
print(f"  Total events on disk: {len(all_events)}")

# Load existing lessons
existing_lessons = read_jsonl(LESSONS_FILE)
existing_lesson_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_lesson_groups.add(key)

print(f"  Existing lessons: {len(existing_lessons)}")
print(f"  Existing lesson groups: {existing_lesson_groups}")

# Filter to meaningful events
meaningful_events = [e for e in all_events
                     if e.get("signal_type", "") not in ("unknown", "?", None, "", "cron_errors_dedup", "cron_errors_dedup2")]

# Group by (signal_type, failure_phase)
from collections import defaultdict
groups = defaultdict(list)
for e in meaningful_events:
    key = (e.get("signal_type", ""), e.get("failure_phase", ""))
    if key[0] and key[1]:
        groups[key].append(e)

print(f"  Event groups: {len(groups)}")
for key, events in groups.items():
    print(f"    {key}: {len(events)} events")

# Pass 1: Extract lesson stubs for groups with 2+ events
new_lessons_pass1 = []
for (sig_type, phase), events in groups.items():
    if len(events) >= 2:
        if (sig_type, phase) not in existing_lesson_groups:
            lesson_id = f"les_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
            lesson = {
                "lesson_id": lesson_id,
                "event_ids": [get_event_id(e) for e in events],
                "signal_type": sig_type,
                "failure_phase": phase,
                "lesson_text": f"[LESSON] What: Recurring {sig_type} in {phase} phase ({len(events)} events)",
                "confidence": "low",
                "scope": events[0].get("domain", "unknown"),
                "status": "proposed",
                "causal_grounding": {"what": f"Recurring {sig_type}", "why": "", "when": ""},
                "what": f"Recurring {sig_type} in {phase} phase",
                "why": "",
                "when": ""
            }
            new_lessons_pass1.append(lesson)
            print(f"  Pass 1: Created lesson stub for ({sig_type}, {phase}) — {len(events)} events")
        else:
            print(f"  Pass 1: Skipping ({sig_type}, {phase}) — already has lesson")

print(f"  Pass 1 produced {len(new_lessons_pass1)} lesson stubs")

# Pass 2: Causal grounding upgrade
new_lessons = []
for lesson_stub in new_lessons_pass1:
    sig_type = lesson_stub["signal_type"]
    phase = lesson_stub["failure_phase"]
    events = groups[(sig_type, phase)]

    # Build causal grounding from event evidence
    domains = list(set(e.get("domain", "unknown") for e in events))
    evidence_summaries = [e.get("outcome_summary", "") for e in events[:3]]

    what = f"Recurring {sig_type} in {phase} phase across {len(events)} events"
    why = f"Pattern detected in {', '.join(domains)}: {sig_type} consistently occurs during {phase}"
    when = f"Applies when {phase} phase operations involve {', '.join(domains[:3])}"

    lesson_stub["confidence"] = "high"
    lesson_stub["causal_grounding"] = {"what": what, "why": why, "when": when}
    lesson_stub["what"] = what
    lesson_stub["why"] = why
    lesson_stub["when"] = when
    lesson_stub["lesson_text"] = f"[LESSON] What: {what}. Why: {why}. When: {when}"
    lesson_stub["status"] = "accepted"

    new_lessons.append(lesson_stub)
    print(f"  Pass 2: Upgraded ({sig_type}, {phase}) to high confidence")

# Write new lessons
if new_lessons:
    append_jsonl(LESSONS_FILE, new_lessons)
    print(f"  Written {len(new_lessons)} lessons to {LESSONS_FILE}")
else:
    print("  No new lessons to write")

# === Step 6: Shift proposal and activation ===
print(f"\n=== Step 6: Shift proposal and activation ===")

# Load all lessons and shifts
all_lessons = read_jsonl(LESSONS_FILE)
all_shifts = read_jsonl(SHIFTS_FILE)

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

active_shifts = [s for s in all_shifts if s.get("status") == "active"]
print(f"  Active shifts: {len(active_shifts)}/12")
print(f"  Covered lesson IDs: {len(covered_lesson_ids)}")

# Find high-confidence lessons not covered by active shifts
remaining_proposals = []
for lesson in all_lessons:
    lid = get_lesson_id(lesson)
    if lesson.get("confidence") == "high" and lid and lid not in covered_lesson_ids:
        remaining_proposals.append(lesson)
        print(f"  Proposed shift for lesson: {lid} ({lesson.get('signal_type','?')}, {lesson.get('failure_phase','?')})")

print(f"  Remaining proposals: {len(remaining_proposals)}")

# Check cap
cap = 12
new_shifts = []
activated_shifts = []

for lesson in remaining_proposals:
    if len(active_shifts) >= cap:
        print(f"  CAP REACHED ({len(active_shifts)}/{cap}) — cannot activate more shifts")
        break

    lid = get_lesson_id(lesson)
    sig_type = lesson.get("signal_type", "unknown")
    phase = lesson.get("failure_phase", "execution")
    domain = lesson.get("scope", "unknown")
    cg = get_lesson_causal_grounding(lesson)

    shift_id = f"shf_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
    shift_text = f"Behavioral adjustment for {sig_type} in {phase} phase: {cg.get('what', 'No description')[:80]}"

    shift = {
        "shift_id": shift_id,
        "lesson_id": lid,
        "source_lesson_ids": [lid],
        "shift_text": shift_text,
        "status": "active",
        "activation_reason": f"Lesson {lid} with high confidence and causal grounding",
        "created_at": now,
        "last_reviewed_at": now,
        "expiry_condition": f"auto_expire_after_14_days_no_reinforcement",
        "priority": 1,
        "last_reinforced_at": now,
        "reinforcement_count": 0,
        "failure_phase": phase,
        "domain": domain
    }
    new_shifts.append(shift)
    active_shifts.append(shift)
    activated_shifts.append(shift)
    print(f"  ACTIVATED: {shift_id} ({sig_type}, {phase})")

# Rewrite shifts.jsonl with all shifts (existing + new)
if new_shifts:
    all_shifts.extend(new_shifts)
    write_jsonl(SHIFTS_FILE, all_shifts)
    print(f"  Written {len(all_shifts)} total shifts ({len(new_shifts)} new)")
else:
    print("  No new shifts to write")

# === Step 7: Decision log ===
print(f"\n=== Step 7: Decision log ===")
run_id = f"r_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
decision = {
    "decision_id": f"dec_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
    "timestamp": now,
    "decision_type": "journal_ingest",
    "summary": f"Ingest run {run_id}: processed {len(unevaluated)} journals, recorded {len(new_events)} events, extracted {len(new_lessons)} lessons, proposed {len(activated_shifts)} shifts, activated {len(activated_shifts)}",
    "evidence": [
        f"journals_scanned: {len(unevaluated)}",
        f"events_recorded: {len(new_events)}",
        f"lessons_extracted: {len(new_lessons)}",
        f"shifts_activated: {len(activated_shifts)}",
        f"active_shifts_total: {len(active_shifts)}/12"
    ],
    "outcome": "completed"
}
append_jsonl(DECISIONS_FILE, [decision])
print(f"  Decision logged: {decision['summary']}")

# === Step 8: Praxis journal ===
print(f"\n=== Step 8: Praxis journal ===")
journal_path = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_path, exist_ok=True)

journal_entry = {
    "run_id": run_id,
    "skill": "ocas-praxis",
    "command": "praxis:journal_ingest",
    "timestamp": now,
    "mode": "cron",
    "findings": {
        "journals_scanned": len(unevaluated),
        "events_recorded": len(new_events),
        "lessons_extracted": len(new_lessons),
        "shifts_activated": len(activated_shifts),
        "active_shifts_total": len(active_shifts),
        "eval_entries_total": len(eval_entries) + len(eval_updates)
    },
    "actions_taken": [
        f"Scanned {len(unevaluated)} new journals",
        f"Recorded {len(new_events)} events",
        f"Extracted {len(new_lessons)} lessons",
        f"Activated {len(activated_shifts)} shifts"
    ] if new_events or new_lessons or activated_shifts else ["No new signals found"],
    "result": "completed"
}

journal_file = os.path.join(journal_path, f"{run_id}.json")
with open(journal_file, 'w') as f:
    json.dump(journal_entry, f, indent=2)
print(f"  Journal written: {journal_file}")

# === Summary ===
print(f"\n{'='*60}")
print(f"INGEST RUN COMPLETE")
print(f"{'='*60}")
print(f"  Run ID: {run_id}")
print(f"  Journals scanned: {len(unevaluated)}")
print(f"  New events: {len(new_events)}")
print(f"  New lessons: {len(new_lessons)}")
print(f"  Shifts activated: {len(activated_shifts)}")
print(f"  Active shifts: {len(active_shifts)}/12")
print(f"  Eval entries: {len(eval_entries) + len(eval_updates)}")
print(f"{'='*60}")
