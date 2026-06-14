#!/usr/bin/env python3
"""Praxis journal ingest run 2026-06-13 cron (9th run)."""

import json
import os
import sys
from datetime import datetime, timezone

# --- Path constants (absolute literals, NOT os.path.join with root) ---
DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
JOURNALS_DIR = "/root/.hermes/commons/journals"
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
JOURNAL_DIR = os.path.join(DATA_DIR, "journal")

# --- Helper functions ---

def get_event_id(evt):
    return evt.get("event_id", evt.get("id", ""))

def get_lesson_id(les):
    return les.get("lesson_id", les.get("id", ""))

def get_shift_id(s):
    return s.get("shift_id", s.get("id", "?"))

def normalize_phase(s):
    return s.get("failure_phase", s.get("phase", "execution"))

# --- Step 0: Dedup evaluated journals ---

print("Step 0: Deduplicating journals_evaluated.jsonl...")
eval_entries = []
seen_ids = set()
if os.path.exists(EVAL_FILE):
    with open(EVAL_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            jid = entry.get("journal_id", "")
            if jid not in seen_ids:
                seen_ids.add(jid)
                eval_entries.append(entry)

print(f"  {len(eval_entries)} unique evaluated entries after dedup")

# --- Step 1: Scan for journal files ---

print("\nStep 1: Scanning for unevaluated journals...")
SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
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
            if date_dir in ('2026-06-12', '2026-06-13'):
                canonical = f"{path_parts[0]}/{date_dir}/{fname}"
                all_files.append((canonical, full_path))

# Filter to unevaluated
unevaluated = [(c, p) for c, p in all_files if c not in seen_ids and os.path.exists(p)]
print(f"  Total journal files in window: {len(all_files)}")
print(f"  Unevaluated: {len(unevaluated)}")
for c, p in sorted(unevaluated):
    print(f"    {c}")

# --- Step 2: Signal extraction ---

print("\nStep 2: Extracting signals from unevaluated journals...")

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

eval_updates = []
new_events = []

for canonical, filepath in sorted(unevaluated):
    print(f"\n  Processing: {canonical}")
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"    ERROR reading file: {e}")
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "action_taken": "error_reading_file",
            "signals_found": [],
            "reason": str(e)
        })
        continue

    signals = []
    summary = ""
    journal_skill = canonical.split('/')[0]

    # --- Schema detection ---
    
    # Finch scan journals: check sources*, signals*, signal_sources*, sources_scanned*
    has_sources = "sources" in data and isinstance(data.get("sources"), dict)
    has_signal_sources = "signal_sources" in data and isinstance(data.get("signal_sources"), dict)
    has_sources_scanned = "sources_scanned" in data and isinstance(data.get("sources_scanned"), dict)
    has_findings_arr = "findings" in data and isinstance(data.get("findings"), list)
    
    # --- Finch scan string-value sources.* (scan-0600 pattern) ---
    if has_sources:
        sources = data["sources"]
        for src_name, src_val in sources.items():
            if isinstance(src_val, str):
                src_lower = src_val.lower()
                if any(kw in src_lower for kw in ["unreachable", "error", "failed", "blocked", "cannot check", "unable to verify", "mcp unreachable"]):
                    sig_type = "auth_failure" if any(kw in src_lower for kw in ["oauth", "token", "401"]) else "execution_error"
                    signals.append({"type": sig_type, "source_journal": canonical, "detail": f"{src_name}: {src_val}"})
                    print(f"    Signal: {sig_type} from sources.{src_name} (string)")
            elif isinstance(src_val, dict):
                status = src_val.get("status", "")
                error = src_val.get("error", "")
                if status in ("blocked", "error", "failed", "inactive"):
                    signals.append({"type": "execution_error", "source_journal": canonical, "detail": f"{src_name} status={status}"})
                    print(f"    Signal: execution_error from sources.{src_name} status={status}")
                if error and error != "none":
                    signals.append({"type": "execution_error", "source_journal": canonical, "detail": f"{src_name} error: {error}"})
                    print(f"    Signal: execution_error from sources.{src_name}.error")
                new_issues = src_val.get("new_issues_since_last_scan", src_val.get("new_issues", []))
                if new_issues:
                    signals.append({"type": "execution_error", "source_journal": canonical, "detail": f"{src_name} {len(new_issues)} new issues"})
                    print(f"    Signal: execution_error from sources.{src_name} ({len(new_issues)} new issues)")

    # --- Finch dict-valued signal_sources.* ---
    if has_signal_sources:
        for src_name, src_data in data["signal_sources"].items():
            if not isinstance(src_data, dict):
                continue
            status = src_data.get("status", "")
            error = src_data.get("error", "")
            if status in ("blocked", "error", "failed", "inactive"):
                signals.append({"type": "execution_error", "source_journal": canonical, "detail": f"signal_sources.{src_name} status={status}"})
                print(f"    Signal: execution_error from signal_sources.{src_name}")
            if error and error != "none":
                signals.append({"type": "execution_error", "source_journal": canonical, "detail": f"signal_sources.{src_name} error: {error}"})
                print(f"    Signal: execution_error from signal_sources.{src_name}.error")

    # --- Finch dict-valued sources_scanned.* ---
    if has_sources_scanned:
        for src_name, src_data in data["sources_scanned"].items():
            if not isinstance(src_data, dict):
                continue
            status = src_data.get("status", "")
            reason = src_data.get("reason", "")
            if status in ("blocked", "error", "failed"):
                sig_type = "auth_failure" if any(kw in reason.lower() for kw in ["oauth", "token", "401"]) else "execution_error"
                signals.append({"type": sig_type, "source_journal": canonical, "detail": f"sources_scanned.{status}: {reason}"})
                print(f"    Signal: {sig_type} from sources_scanned.{src_name}")
            elif reason and any(kw in reason.lower() for kw in ["unreachable", "cannot", "unable", "mcp"]):
                sig_type = "auth_failure" if any(kw in reason.lower() for kw in ["oauth", "token", "401"]) else "execution_error"
                signals.append({"type": sig_type, "source_journal": canonical, "detail": f"sources_scanned.{src_name}: {reason}"})
                print(f"    Signal: {sig_type} from sources_scanned.{src_name} reason")

    # --- Finch findings[] array ---
    if has_findings_arr:
        for finding in data["findings"]:
            if not isinstance(finding, dict):
                continue
            if finding.get("escalation_needed"):
                signals.append({"type": "escalation", "source_journal": canonical, "detail": f"finding: {finding.get('title', 'unknown')}"})
                print(f"    Signal: escalation from findings[]")
            if finding.get("type") == "critical":
                signals.append({"type": "escalation", "source_journal": canonical, "detail": f"critical finding: {finding.get('title', 'unknown')}"})
                print(f"    Signal: escalation from critical finding")
            if finding.get("status") in ("error", "failed"):
                signals.append({"type": "execution_error", "source_journal": canonical, "detail": f"finding status: {finding.get('title', 'unknown')}"})
                print(f"    Signal: execution_error from finding status")
            if isinstance(finding.get("action_taken"), str) and any(kw in finding["action_taken"].lower() for kw in ["fix", "correction", "repair", "resolve"]):
                signals.append({"type": "correction", "source_journal": canonical, "detail": finding["action_taken"]})
                print(f"    Signal: correction from finding action_taken")

    # --- Top-level esalation_needed ---
    if data.get("escalation_needed"):
        signals.append({"type": "escalation", "source_journal": canonical, "detail": "top-level escalation_needed=true"})
        print(f"    Signal: escalation (top-level)")

    # --- Decision-based schemas ---
    decision = data.get("decision", {})
    if isinstance(decision, dict):
        exec_result = decision.get("execution_result", {})
        if isinstance(exec_result, dict):
            status = exec_result.get("status", "")
            if status in ("error", "partial", "completed_with_errors"):
                signals.append({"type": "execution_error", "source_journal": canonical, "detail": f"decision.execution_result.status={status}"})
                print(f"    Signal: execution_error from decision status={status}")

    # --- Status field ---
    top_status = data.get("status", "")
    if top_status in ("completed_with_errors", "error", "partial"):
        signals.append({"type": "execution_error", "source_journal": canonical, "detail": f"top-level status={top_status}"})
        print(f"    Signal: execution_error from top-level status={top_status}")

    # --- Summary string extraction (with noise filter) ---
    if isinstance(data.get("summary"), str):
        summary = data["summary"]
    elif isinstance(decision.get("summary"), str):
        summary = decision["summary"]

    if isinstance(summary, str) and len(summary.strip()) > 0:
        summary_lower = summary.lower()
        # Check for failure keywords in summary
        FAILURE_KW = ["error", "failed", "failure", "outage", "unreachable", "blocked", "unavailable"]
        auth_kw = ["oauth", "expired", "401", "unauthorized", "token"]
        
        for kw in FAILURE_KW:
            if kw in summary_lower:
                signals.append({"type": "failure_keyword", "source_journal": canonical, "detail": f"summary contains '{kw}'"})
                print(f"    Signal: failure_keyword '{kw}' in summary (pending suppress filter)")
        for kw in auth_kw:
            if kw in summary_lower:
                signals.append({"type": "auth_failure", "source_journal": canonical, "detail": f"summary contains '{kw}'"})
                print(f"    Signal: auth_failure '{kw}' in summary (pending suppress filter)")

    # --- Forge journal-scan status-less schema ---
    if "result" in data and data.get("result") == "no_op":
        results_val = data.get("results", [])
        if isinstance(results_val, dict):
            files_found = results_val.get("files_found", 0)
            files_processed = results_val.get("files_processed", 0)
        else:
            files_found = 0
            files_processed = 0
        if files_found == 0:
            signals.append({"type": "failure_keyword", "source_journal": canonical, "detail": "forge: no files found"})
            print(f"    Signal: forge no-op detected (pending suppress)")

    # --- Spot sweep / Observation journals ---
    if data.get("type") == "Observation" and "results" in data and isinstance(data["results"], list):
        # Spot journals: check for new failures beyond known platform issues
        pass  # Routine observations handled by summary suppress

    # --- Apply noise filters ---
    if summary and signals:
        if should_suppress_summary_signals(summary, signals):
            print(f"    Suppress filter MATCHED — clearing {len(signals)} summary-derived signals")
            signals = []

    # --- Post-finch dict-summary false positive guard ---
    # (gotcha: finch scan-1311 cron_health notes contain "gateway collision error ... transient, self-resolved")
    # The sources.* handler already emits these, but the suppress filter catches them
    # Additional guard: if all sources are status:ok, clear any signals from cron_health notes
    if has_sources and signals:
        all_ok = all(
            isinstance(v, dict) and v.get("status") == "ok"
            for v in data["sources"].values()
            if isinstance(v, dict)
        )
        all_str_ok = all(
            isinstance(v, str) and "ok" in v.lower()
            for v in data["sources"].values()
            if isinstance(v, str)
        )
        if all_ok or all_str_ok:
            non_source_signals = [s for s in signals if "cron_health" not in s.get("detail", "") and "gateway collision" not in s.get("detail", "")]
            source_only = [s for s in signals if "cron_health" in s.get("detail", "") or "gateway collision" in s.get("detail", "")]
            if source_only and not non_source_signals:
                print(f"    All sources ok — clearing {len(source_only)} transient source signals")
                signals = non_source_signals

    # --- Record ---
    if signals:
        now = datetime.now(timezone.utc).isoformat()
        for sig in signals:
            event = {
                "event_id": f"evt_{os.urandom(4).hex()}",
                "source_journal": canonical,
                "signal_type": sig["type"],
                "failure_phase": "execution",
                "recorded_at": now,
                "detail": sig["detail"],
                "domain": journal_skill
            }
            new_events.append(event)
        print(f"    => {len(signals)} signal(s) extracted")
    else:
        print(f"    => no_signal")

    eval_updates.append({
        "journal_id": canonical,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "action_taken": "signals_extracted" if signals else "no_signal",
        "signals_found": [s["type"] for s in signals],
        "reason": "No behavioral signals after noise filtering" if not signals else f"Extracted {len(signals)} signal(s)"
    })

# --- Step 3: Post-write dedup ---

print("\nStep 3: Post-write dedup on events...")
existing_events = []
if os.path.exists(EVENTS_FILE):
    with open(EVENTS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                existing_events.append(json.loads(line))

# Dedup by (source_journal, signal_type)
seen_evt_keys = set()
deduped_events = []
for evt in existing_events:
    key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
    if key not in seen_evt_keys:
        seen_evt_keys.add(key)
        deduped_events.append(evt)

# Add new events (deduped)
for evt in new_events:
    key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
    if key not in seen_evt_keys:
        seen_evt_keys.add(key)
        deduped_events.append(evt)

with open(EVENTS_FILE, 'w') as f:
    for evt in deduped_events:
        f.write(json.dumps(evt) + "\n")
print(f"  Total events written: {len(deduped_events)} (new: {len(new_events)})")

# --- Step 4: Lesson extraction (two-pass) ---

print("\nStep 4: Lesson extraction...")

# Load all events (fresh from disk)
all_events = []
if os.path.exists(EVENTS_FILE):
    with open(EVENTS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                all_events.append(json.loads(line))

# Load existing lessons
existing_lessons = []
if os.path.exists(LESSONS_FILE):
    with open(LESSONS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                existing_lessons.append(json.loads(line))

# Pass 1: Group by (signal_type, failure_phase)
MEANINGFUL_TYPES = {"auth_failure", "escalation", "execution_error", "correction", "failure_keyword", "cron_errors", "platform_failure"}
groups = {}
for evt in all_events:
    st = evt.get("signal_type", "")
    if st not in MEANINGFUL_TYPES:
        continue
    phase = evt.get("failure_phase", "execution")
    key = (st, phase)
    if key not in groups:
        groups[key] = []
    groups[key].append(evt)

# Pass 2: Extract lessons for groups with 2+ events
new_lessons = []
for (st, phase), evts in groups.items():
    if len(evts) < 2:
        continue
    lesson_text = f"[{st}] Repeated {st} in {phase} phase — {len(evts)} occurrences across journals."
    cg = {
        "what": f"{st} occurring {len(evts)} times in {phase} phase",
        "why": f"Multiple journals report {st} — suggests systemic issue in {phase}",
        "when": f"Observed in {phase} phase across {len(evts)} events"
    }
    lesson = {
        "lesson_id": f"les_{os.urandom(4).hex()}",
        "signal_type": st,
        "failure_phase": phase,
        "confidence": "high",
        "lesson_text": lesson_text,
        "causal_grounding": cg,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "event_count": len(evts)
    }
    new_lessons.append(lesson)

# Content dedup: skip lessons for (signal_type, phase) already covered
existing_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_groups.add(key)

filtered_lessons = []
for lesson in new_lessons:
    key = (lesson["signal_type"], lesson["failure_phase"])
    if key in existing_groups:
        print(f"  Skipping duplicate lesson: {key}")
        continue
    existing_groups.add(key)
    filtered_lessons.append(lesson)

# Write lessons (append new, deduped)
with open(LESSONS_FILE, 'a') as f:
    for l in filtered_lessons:
        f.write(json.dumps(l) + "\n")

print(f"  New lessons: {len(filtered_lessons)}")
all_lessons = existing_lessons + filtered_lessons
print(f"  Total lessons: {len(all_lessons)}")

# --- Step 5: Shift proposal and activation ---

print("\nStep 5: Shift proposal and activation...")

# Load existing shifts
all_shifts = []
if os.path.exists(SHIFTS_FILE):
    with open(SHIFTS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                all_shifts.append(json.loads(line))

active_shifts = [s for s in all_shifts if s.get("status") == "active"]
proposed_shifts = [s for s in all_shifts if s.get("status") == "proposed"]

# Build covered lesson IDs
covered_lesson_ids = set()
for s in all_shifts:
    if s.get("status") in ("active", "proposed"):
        for field in ['lesson_id', 'source_lesson', 'source_lesson_ids']:
            val = s.get(field)
            if val:
                if isinstance(val, list):
                    covered_lesson_ids.update(val)
                elif isinstance(val, str):
                    covered_lesson_ids.add(str(val))

# Propose shifts for uncovered high-confidence lessons
CAP = 12
new_proposals = []
for lesson in all_lessons:
    lid = get_lesson_id(lesson)
    if lesson.get("confidence") == "high" and lid not in covered_lesson_ids:
        shift_text = f"When {lesson['signal_type']} occurs in {lesson['failure_phase']} phase, apply behavioral adjustment (from lesson: {lesson['lesson_text'][:80]})"
        proposal = {
            "shift_id" if "shift_id" in lesson else "id": f"shift_{os.urandom(4).hex()}",
            "status": "proposed",
            "shift_text": shift_text,
            "failure_phase": lesson["failure_phase"],
            "domain": lesson.get("signal_type", "general"),
            "lesson_id": lid,
            "proposed_at": datetime.now(timezone.utc).isoformat(),
            "reinforce_count": 0
        }
        new_proposals.append(proposal)
        covered_lesson_ids.add(lid)

# Merge-overlap check and activation
final_shifts = list(all_shifts)  # copy

for proposal in new_proposals:
    # Check overlap with active shifts
    overlap = False
    for active in [s for s in final_shifts if s.get("status") == "active"]:
        p_phase = normalize_phase(proposal)
        a_phase = normalize_phase(active)
        p_domain = proposal.get("domain", "")
        a_domain = active.get("domain", "")
        if p_phase == a_phase and (p_domain == a_domain or not p_domain or not a_domain):
            # Merge: reinforce active
            active["reinforce_count"] = active.get("reinforce_count", 0) + 1
            active["last_reinforced"] = datetime.now(timezone.utc).isoformat()
            print(f"  Merged proposal into active shift: {get_shift_id(active)}")
            overlap = True
            break
    if not overlap:
        # Check cap
        active_count = len([s for s in final_shifts if s.get("status") == "active"])
        if active_count < CAP:
            proposal["status"] = "active"
            proposal["activated_at"] = datetime.now(timezone.utc).isoformat()
            final_shifts.append(proposal)
            print(f"  Activated new shift: {proposal.get('shift_id', proposal.get('id', '?'))}")
        else:
            final_shifts.append(proposal)
            print(f"  Cap reached — shift remains proposed: {proposal.get('shift_id', proposal.get('id', '?'))}")

# Determine actual shift_id key for each shift before writing
for s in final_shifts:
    if "shift_id" not in s and "id" in s:
        s["shift_id"] = s.pop("id")

with open(SHIFTS_FILE, 'w') as f:
    for s in final_shifts:
        f.write(json.dumps(s) + "\n")

active_count = len([s for s in final_shifts if s.get("status") == "active"])
proposed_count = len([s for s in final_shifts if s.get("status") == "proposed"])
print(f"  Active shifts: {active_count}/{CAP}, Proposed: {proposed_count}")

# --- Step 6: Write eval_updates ---

print("\nStep 6: Writing eval_updates...")
with open(EVAL_FILE, 'a') as f:
    for eu in eval_updates:
        f.write(json.dumps(eu) + "\n")
print(f"  Wrote {len(eval_updates)} eval_updates")

# --- Step 7: Write journal entry ---

print("\nStep 7: Writing journal entry...")
now = datetime.now(timezone.utc)
run_id = f"r_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
today = now.strftime("%Y-%m-%d")
journal_path = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_path, exist_ok=True)

journal_entry = {
    "run_id": run_id,
    "timestamp": now.isoformat(),
    "command": "praxis:journal_ingest",
    "mode": "cron",
    "journals_scanned": len(unevaluated),
    "new_events": len(new_events),
    "new_lessons": len(filtered_lessons),
    "total_events": len(deduped_events),
    "total_lessons": len(all_lessons),
    "active_shifts": active_count,
    "proposed_shifts": proposed_count,
    "summary": f"Ingested {len(unevaluated)} journals. {len(new_events)} new events, {len(filtered_lessons)} new lessons. Active shifts: {active_count}/{CAP}."
}

entry_path = os.path.join(journal_path, f"{run_id}.json")
with open(entry_path, 'w') as f:
    json.dump(journal_entry, f, indent=2)
print(f"  Journal: {entry_path}")

# --- Final summary ---
print(f"\n{'='*60}")
print(f"INGEST COMPLETE")
print(f"  Run ID: {run_id}")
print(f"  Journals scanned: {len(unevaluated)}")
print(f"  New events: {len(new_events)}")
print(f"  New lessons: {len(filtered_lessons)}")
print(f"  Active shifts: {active_count}/{CAP}")
print(f"{'='*60}")
