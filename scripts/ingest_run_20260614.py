#!/usr/bin/env python3
"""Praxis journal ingest run — 2026-06-14 cron cycle."""

import json
import os
from datetime import datetime, timedelta, timezone

# ── Path constants (absolute literals — never use os.path.join with /root) ──
DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
JOURNALS_DIR = "/root/.hermes/commons/journals"
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")
JOURNAL_DIR = os.path.join(JOURNALS_DIR, "ocas-praxis")

SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
ACTIVE_SHIFT_CAP = 12
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy"
]
FORGE_NO_OP_RESULTS = {"no_op", "clean"}
MEANINGFUL_SIGNAL_TYPES = {
    "auth_failure", "escalation", "execution_error", "correction",
    "cron_errors", "failure_keyword", "platform_failure",
    "rate_limit", "timeout", "parse_error", "config_error",
    "permission_denied", "disk_full", "memory_error"
}

now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")


# ── Schema normalization helpers ──
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


# ── Step 1: Deduplicate journals_evaluated.jsonl ──
print("=== Step 1: Dedup journals_evaluated.jsonl ===")
eval_entries = []
seen_ids = set()
if os.path.exists(EVAL_FILE):
    with open(EVAL_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                jid = entry.get("journal_id", "")
                if jid and jid not in seen_ids:
                    seen_ids.add(jid)
                    eval_entries.append(entry)
            except json.JSONDecodeError:
                pass

if len(eval_entries) != sum(1 for _ in open(EVAL_FILE)) if os.path.exists(EVAL_FILE) else 0:
    with open(EVAL_FILE, "w") as f:
        for e in eval_entries:
            f.write(json.dumps(e) + "\n")
    print(f"  Deduplicated: {len(eval_entries)} unique entries")
else:
    print(f"  Already clean: {len(eval_entries)} entries")

# Compact if >5000
if len(eval_entries) > 5000:
    cutoff = (now - timedelta(days=30)).isoformat()
    compacted = [e for e in eval_entries if e.get("evaluated_at", "9999") > cutoff or not e.get("evaluated_at")]
    removed = len(eval_entries) - len(compacted)
    if removed > 0:
        eval_entries = compacted
        with open(EVAL_FILE, "w") as f:
            for e in eval_entries:
                f.write(json.dumps(e) + "\n")
        print(f"  Compacted: removed {removed} entries older than 30 days")

seen_ids = {e.get("journal_id", "") for e in eval_entries}


# ── Step 2: Scan filesystem ──
print(f"\n=== Step 2: Scan journals (today={today}, yesterday={yesterday}) ===")
all_files = []
for root_dir, dirs, files in os.walk(JOURNALS_DIR):
    dirs[:] = [d for d in dirs if not d.startswith(".")]
    parts = root_dir.replace(JOURNALS_DIR, "").strip("/").split("/")
    if parts and parts[0] in SKIP_DIRS:
        continue
    for fname in files:
        if not fname.endswith(".json"):
            continue
        full_path = os.path.join(root_dir, fname)
        rel_path = os.path.relpath(full_path, JOURNALS_DIR)
        path_parts = rel_path.split("/")
        if len(path_parts) >= 2:
            date_dir = path_parts[1] if len(path_parts) > 1 else ""
            if date_dir in (today, yesterday):
                skill = path_parts[0]
                canonical = f"{skill}/{date_dir}/{fname}"
                all_files.append((canonical, full_path))

print(f"  Total journal files found: {len(all_files)}")

# ── Step 3: Compute unevaluated ──
print("\n=== Step 3: Compute unevaluated ===")
unevaluated = [(c, p) for c, p in all_files if c in seen_ids and os.path.exists(p)]
already_evaluated_new = [(c, p) for c, p in all_files if c in seen_ids and os.path.exists(p)]
unevaluated_new = [(c, p) for c, p in all_files if c not in seen_ids and os.path.exists(p)]
print(f"  Evaluated (skip): {len(all_files) - len(unevaluated_new)}")
print(f"  Unevaluated: {len(unevaluated_new)}")

for c, p in unevaluated_new:
    print(f"    → {c}")

eval_updates = []
new_events = []
journals_with_errors = []

# ── Step 4: Signal extraction ──
print("\n=== Step 4: Signal extraction ===")

for canonical, fpath in unevaluated_new:
    print(f"\n  Processing: {canonical}")
    try:
        with open(fpath, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"    ERROR loading: {e}")
        eval_updates.append({
            "journal_id": canonical, "evaluated_at": now.isoformat(),
            "action_taken": "error_loading", "signals_found": [],
            "reason": f"Failed to load: {str(e)}"
        })
        journals_with_errors.append(canonical)
        continue
    except FileNotFoundError:
        print(f"    FILE NOT FOUND (moved/deleted)")
        continue

    signals_found = []
    summary = ""

    # Handle list-format journals
    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                s = entry.get("summary", "")
                if isinstance(s, str) and s:
                    summary += " " + s
                st = entry.get("status", "")
                if st in ("error", "failed", "partial"):
                    signals_found.append({"type": "execution_error", "source": "list_entry"})
    elif isinstance(data, dict):
        # Check top-level escalation
        if data.get("escalation_needed") is True:
            signals_found.append({"type": "escalation", "source": "top_level"})

        # Check various status fields
        status = ""
        decision = data.get("decision", {})
        if isinstance(decision, dict):
            exec_result = decision.get("execution_result", {})
            if isinstance(exec_result, dict):
                status = exec_result.get("status", "")
            if not status:
                status = decision.get("status", "")

        if not status:
            status = data.get("status", "")

        # Handle "completed_with_errors"
        if status in ("completed_with_errors", "partial"):
            signals_found.append({"type": "execution_error", "source": "status"})

        # Check summary field
        summary_raw = data.get("summary", decision.get("summary", ""))
        if isinstance(summary_raw, dict):
            summary = json.dumps(summary_raw)
        elif isinstance(summary_raw, str):
            summary = summary_raw

        # Check findings arrays
        findings = data.get("findings", data.get("new_findings", []))
        if isinstance(findings, list):
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                if finding.get("escalation_needed") is True:
                    signals_found.append({"type": "escalation", "source": "finding"})
                f_status = finding.get("status", "")
                if f_status in ("error", "failed", "partial"):
                    signals_found.append({"type": "execution_error", "source": "finding"})
                f_severity = finding.get("severity", "")
                f_title = finding.get("title", "")
                f_detail = finding.get("detail", "")
                if f_severity in ("critical", "high"):
                    sig_text = f"{f_title} {f_detail}".lower()
                    if "auth" in sig_text or "oauth" in sig_text or "token" in sig_text or "401" in sig_text:
                        signals_found.append({"type": "auth_failure", "source": "finding"})
                    if "error" in sig_text or "fail" in sig_text:
                        signals_found.append({"type": "failure_keyword", "source": "finding"})

        # Check actions_taken
        actions = data.get("actions_taken", [])
        if isinstance(actions, list):
            for action in actions:
                if isinstance(action, dict):
                    outcome = action.get("outcome", "")
                    if outcome in ("error", "failure", "failed"):
                        signals_found.append({"type": "execution_error", "source": "action"})
                    elif outcome in ("corrected", "fixed", "applied"):
                        signals_found.append({"type": "correction", "source": "action"})

        # Check fixes_applied
        fixes = data.get("fixes_applied", data.get("checks", {}).get("fixes_applied", 0))
        if isinstance(fixes, int) and fixes > 0:
            signals_found.append({"type": "correction", "source": "fixes_applied"})

        # Check finch signals/sources
        finch_signals = data.get("signals", {})
        if isinstance(finch_signals, dict):
            cron_data = finch_signals.get("cron", {})
            if isinstance(cron_data, dict):
                new_errors = cron_data.get("new_errors", [])
                if isinstance(new_errors, list) and new_errors:
                    signals_found.append({"type": "cron_errors", "source": "finch_signals"})
                error_bd = cron_data.get("error_breakdown", {})
                if isinstance(error_bd, dict):
                    for k, v in error_bd.items():
                        if isinstance(v, int) and v > 0:
                            signals_found.append({"type": "cron_errors", "source": "finch_error_breakdown"})

        # Check finch tasks_added
        tasks_added = data.get("tasks_added", [])
        if isinstance(tasks_added, list):
            for task in tasks_added:
                if isinstance(task, str) and any(kw in task.lower() for kw in ["error", "fail", "broken"]):
                    signals_found.append({"type": "failure_keyword", "source": "finch_task"})

        # Check forge result
        result = data.get("result", data.get("status", ""))
        if isinstance(result, str):
            result_clean = result.lower().strip()
            if result_clean in FORGE_NO_OP_RESULTS or result_clean.startswith("clean"):
                # Forge no-op — suppress all signals
                signals_found = []
                eval_updates.append({
                    "journal_id": canonical, "evaluated_at": now.isoformat(),
                    "action_taken": "no_signal", "signals_found": [],
                    "reason": f"No-op forge scan result: '{result}'"
                })
                print(f"    → Forge no-op: '{result}'")
                continue

        # Spot observation no-op handler
        journal_type = data.get("type", "")
        if journal_type == "observation" or "sweep" in canonical.lower():
            summary_lower = summary.lower() if isinstance(summary, str) else ""
            spot_skip_phrases = ["skipped", "permanently broken", "dead watch", "expired", "no new availability", "no active watches", "all clean", "0 active"]
            if any(phrase in summary_lower for phrase in spot_skip_phrases):
                signals_found = []
                eval_updates.append({
                    "journal_id": canonical, "evaluated_at": now.isoformat(),
                    "action_taken": "no_signal", "signals_found": [],
                    "reason": f"Spot observation no-op: {summary[:100]}"
                })
                print(f"    → Spot observation no-op")
                continue

        # Keyword scanning on summary (only if non-empty string)
        if isinstance(summary, str) and len(summary.strip()) > 0:
            summary_lower = summary.lower()
            # Auth failure keywords
            if any(kw in summary_lower for kw in ["oauth", "token expired", "401", "unauthorized", "auth fail"]):
                signals_found.append({"type": "auth_failure", "source": "summary"})
            # Failure keywords
            if any(kw in summary_lower for kw in ["error", "fail", "broken", "crash", "timeout", "exception"]):
                signals_found.append({"type": "failure_keyword", "source": "summary"})

    # Semantic suppression for summary-derived signals
    if isinstance(summary, str) and signals_found:
        summary_derived = {"failure_keyword", "auth_failure"}
        non_summary = [s for s in signals_found if s["type"] not in summary_derived]
        if not non_summary:
            summary_lower = summary.lower()
            if any(phrase in summary_lower for phrase in SUPPRESS_PHRASES):
                signals_found = []
                print(f"    → Suppressed summary-derived signals (routine scan)")

    # Deduplicate signals by type
    seen_signal_types = set()
    deduped_signals = []
    for s in signals_found:
        if s["type"] not in seen_signal_types:
            seen_signal_types.add(s["type"])
            deduped_signals.append(s)
    signals_found = deduped_signals

    # Record events for real signals
    if signals_found:
        for sig in signals_found:
            sig_type = sig["type"]
            if sig_type not in MEANINGFUL_SIGNAL_TYPES:
                continue
            # Determine failure phase
            phase = "execution"
            if summary and isinstance(summary, str):
                sl = summary.lower()
                if any(kw in sl for kw in ["should have", "before", "wrong approach", "didn't check", "missing prerequisite"]):
                    phase = "planning"
                elif any(kw in sl for kw in ["too verbose", "wrong format", "just give me", "make it concise", "don't explain"]):
                    phase = "response"

            event = {
                "event_id": f"evt_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}",
                "source_journal": canonical,
                "signal_type": sig_type,
                "failure_phase": phase,
                "domain": canonical.split("/")[0] if "/" in canonical else "unknown",
                "evidence": {
                    "summary": summary[:500] if summary else "",
                    "signal_source": sig.get("source", "unknown")
                },
                "recorded_at": now.isoformat()
            }
            new_events.append(event)
            print(f"    → Event: {sig_type} ({phase})")

        eval_updates.append({
            "journal_id": canonical, "evaluated_at": now.isoformat(),
            "action_taken": "event_recorded",
            "signals_found": [s["type"] for s in signals_found],
            "reason": f"Extracted {len(signals_found)} signal(s)"
        })
    else:
        eval_updates.append({
            "journal_id": canonical, "evaluated_at": now.isoformat(),
            "action_taken": "no_signal", "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })
        print(f"    → No signals")


# ── Step 4b: Write new events ──
print(f"\n=== Step 4b: Write events ({len(new_events)} new) ===")
if new_events:
    # Read existing events
    existing_events = []
    if os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing_events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    all_events = existing_events + new_events

    # Post-write dedup by (source_journal, signal_type)
    deduped_events = {}
    for evt in all_events:
        key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
        if key not in deduped_events:
            deduped_events[key] = evt
        # Keep earliest recorded_at
        elif evt.get("recorded_at", "") < deduped_events[key].get("recorded_at", ""):
            deduped_events[key] = evt

    final_events = list(deduped_events.values())
    with open(EVENTS_FILE, "w") as f:
        for evt in final_events:
            f.write(json.dumps(evt) + "\n")
    print(f"  Written: {len(final_events)} total events ({len(new_events)} new)")
else:
    print("  No new events to write")
    existing_events = []
    if os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing_events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    final_events = existing_events


# ── Step 5: Lesson extraction (two-pass) ──
print(f"\n=== Step 5: Lesson extraction ===")

# Read existing lessons
existing_lessons = []
if os.path.exists(LESSONS_FILE):
    with open(LESSONS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    existing_lessons.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

# Build content fingerprint set for dedup
existing_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_groups.add(key)

# Filter to meaningful events
meaningful_events = [e for e in final_events if e.get("signal_type") in MEANINGFUL_SIGNAL_TYPES]
print(f"  Meaningful events: {len(meaningful_events)}")

# Group by (signal_type, failure_phase)
from collections import defaultdict
groups = defaultdict(list)
for evt in meaningful_events:
    key = (evt.get("signal_type", ""), evt.get("failure_phase", ""))
    if key[0] and key[1]:
        groups[key].append(evt)

new_lessons = []
for (sig_type, phase), events in groups.items():
    if len(events) < 2:
        continue
    if (sig_type, phase) in existing_groups:
        print(f"  Skipping duplicate lesson: signal_type={sig_type}, phase={phase}")
        continue

    # Pass 2: Causal grounding
    lesson_text = f"[LESSON] What: {sig_type} pattern observed across {len(events)} events in {phase} phase. "
    lesson_text += f"Why: Repeated {sig_type} indicates systemic issue in {phase} stage. "
    lesson_text += f"When: Applies to {phase} phase operations involving {sig_type}."

    lesson = {
        "lesson_id": f"les_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}",
        "signal_type": sig_type,
        "failure_phase": phase,
        "lesson_text": lesson_text,
        "confidence": "high",
        "causal_grounding": {
            "what": f"{sig_type} pattern in {phase} phase",
            "why": f"Systemic issue causing repeated {sig_type}",
            "when": f"During {phase} phase operations"
        },
        "event_count": len(events),
        "source_events": [get_event_id(e) for e in events[:5]],
        "extracted_at": now.isoformat()
    }
    new_lessons.append(lesson)
    existing_groups.add((sig_type, phase))
    print(f"  New lesson: {sig_type} / {phase} ({len(events)} events)")

if new_lessons:
    all_lessons = existing_lessons + new_lessons
    with open(LESSONS_FILE, "w") as f:
        for l in all_lessons:
            f.write(json.dumps(l) + "\n")
    print(f"  Written: {len(all_lessons)} total lessons ({len(new_lessons)} new)")
else:
    print("  No new lessons to extract")
    all_lessons = existing_lessons


# ── Step 6: Shift proposal ──
print(f"\n=== Step 6: Shift proposal ===")

# Read existing shifts
all_shifts = []
if os.path.exists(SHIFTS_FILE):
    with open(SHIFTS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    all_shifts.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

active_shifts = [s for s in all_shifts if s.get("status") == "active"]
proposed_shifts = [s for s in all_shifts if s.get("status") == "proposed"]
print(f"  Active shifts: {len(active_shifts)}/{ACTIVE_SHIFT_CAP}")
print(f"  Proposed shifts: {len(proposed_shifts)}")

# Build covered lesson IDs
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

new_proposals = []
for lesson in all_lessons:
    lid = get_lesson_id(lesson)
    st = lesson.get("signal_type", "")
    phase = lesson.get("failure_phase", "")

    # Guard: skip malformed lessons
    if not st or st in ("unknown", "?", ""):
        print(f"  Skipping malformed lesson: {lid} (signal_type='{st}')")
        continue
    if not phase:
        print(f"  Skipping malformed lesson: {lid} (failure_phase='{phase}')")
        continue

    if lesson.get("confidence") == "high" and lid not in covered_lesson_ids:
        # Check domain+phase overlap with active shifts
        domain = lesson.get("domain", st)
        overlap = False
        for active in active_shifts:
            a_domain = active.get("domain", "")
            a_phase = get_failure_phase(active)
            if a_domain == domain and a_phase == phase:
                overlap = True
                # Reinforce active shift
                active["reinforcement_count"] = active.get("reinforcement_count", 0) + 1
                active["last_reinforced"] = now.isoformat()
                print(f"  Reinforced active shift: {get_shift_id(active)} ({a_domain}/{a_phase})")
                break

        if not overlap:
            proposal = {
                "shift_id": f"shf_{now.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}",
                "lesson_id": lid,
                "signal_type": st,
                "failure_phase": phase,
                "domain": domain,
                "shift_text": f"Address {st} in {phase} phase",
                "status": "proposed",
                "proposed_at": now.isoformat()
            }
            new_proposals.append(proposal)
            covered_lesson_ids.add(lid)
            print(f"  New proposal: {st} / {phase}")

# Merge-overlap check and activate
activated = 0
for proposal in new_proposals:
    domain = proposal.get("domain", "")
    phase = proposal.get("failure_phase", "")

    # Check overlap again (may have been reinforced above)
    overlap = False
    for active in active_shifts:
        a_domain = active.get("domain", "")
        a_phase = get_failure_phase(active)
        if a_domain == domain and a_phase == phase:
            overlap = True
            proposal["status"] = "rejected"
            proposal["rejection_reason"] = f"Overlap with active shift {get_shift_id(active)}"
            break

    if not overlap:
        if len(active_shifts) < ACTIVE_SHIFT_CAP:
            proposal["status"] = "active"
            proposal["activated_at"] = now.isoformat()
            active_shifts.append(proposal)
            activated += 1
            print(f"  Activated: {proposal['shift_id']} ({domain}/{phase})")
        else:
            print(f"  At cap ({ACTIVE_SHIFT_CAP}), keeping proposed: {proposal['shift_id']}")

# Rewrite shifts file
all_shifts_final = active_shifts + proposed_shifts + new_proposals
# Dedup by shift_id
seen_shift_ids = {}
for s in all_shifts_final:
    sid = get_shift_id(s)
    if sid not in seen_shift_ids:
        seen_shift_ids[sid] = s
    elif s.get("status") == "active" and seen_shift_ids[sid].get("status") != "active":
        seen_shift_ids[sid] = s

with open(SHIFTS_FILE, "w") as f:
    for s in seen_shift_ids.values():
        f.write(json.dumps(s) + "\n")

print(f"  Shifts written: {len(seen_shift_ids)} total, {len([s for s in seen_shift_ids.values() if s.get('status')=='active'])} active")


# ── Step 7: Write eval_updates ──
print(f"\n=== Step 7: Write eval_updates ({len(eval_updates)}) ===")
with open(EVAL_FILE, "a") as f:
    for eu in eval_updates:
        f.write(json.dumps(eu) + "\n")
print(f"  Done. Total eval entries: {len(eval_entries) + len(eval_updates)}")


# ── Step 8: Write decisions log ──
print(f"\n=== Step 8: Decisions log ===")
decision = {
    "decision_id": f"dec_{now.strftime('%Y%m%d%H%M%S')}",
    "timestamp": now.isoformat(),
    "action": "journal_ingest",
    "journals_scanned": len(unevaluated_new),
    "events_recorded": len(new_events),
    "lessons_extracted": len(new_lessons),
    "shifts_proposed": len(new_proposals),
    "shifts_activated": activated,
    "active_shifts_total": len([s for s in seen_shift_ids.values() if s.get("status") == "active"]),
    "journals_with_errors": len(journals_with_errors)
}
with open(DECISIONS_FILE, "a") as f:
    f.write(json.dumps(decision) + "\n")
print(f"  Decision logged: {decision['decision_id']}")


# ── Step 9: Write Praxis journal ──
print(f"\n=== Step 9: Praxis journal ===")
run_id = f"r_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
journal_path = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_path, exist_ok=True)

journal_entry = {
    "run_id": run_id,
    "timestamp": now.isoformat(),
    "type": "ingest",
    "decision": {
        "summary": f"Ingest cycle: {len(unevaluated_new)} journals scanned, {len(new_events)} events, {len(new_lessons)} lessons, {activated} shifts activated",
        "execution_result": {"status": "ok"},
        "payload": {
            "entities_observed": [
                {"name": "journal_ingest", "type": "process", "user_relevance": "system"}
            ],
            "action_result": {
                "journals_scanned": len(unevaluated_new),
                "events_recorded": len(new_events),
                "lessons_extracted": len(new_lessons),
                "shifts_activated": activated
            }
        }
    }
}

with open(os.path.join(journal_path, f"{run_id}.json"), "w") as f:
    json.dump(journal_entry, f, indent=2)
print(f"  Journal written: {run_id}")


# ── Summary ──
print(f"\n{'='*60}")
print(f"INGEST COMPLETE — {now.isoformat()}")
print(f"  Journals scanned: {len(unevaluated_new)}")
print(f"  Events recorded: {len(new_events)}")
print(f"  Lessons extracted: {len(new_lessons)}")
print(f"  Shifts proposed: {len(new_proposals)}")
print(f"  Shifts activated: {activated}")
print(f"  Active shifts: {len([s for s in seen_shift_ids.values() if s.get('status')=='active'])}/{ACTIVE_SHIFT_CAP}")
print(f"  Journals with errors: {len(journals_with_errors)}")
print(f"{'='*60}")
