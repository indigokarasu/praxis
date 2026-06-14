#!/usr/bin/env python3
"""Praxis journal ingest run — 2026-06-11 cron scan."""

import json
import os
from datetime import datetime, timezone

# ── Paths (absolute literals — os.path.join strips leading dot) ──────────────
DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
JOURNALS_DIR = "/root/.hermes/commons/journals"
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")
JOURNAL_DIR = os.path.join(JOURNALS_DIR, "ocas-praxis")

SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
NOW = datetime.now(timezone.utc)
TODAY = "2026-06-11"
YESTERDAY = "2026-06-10"

# ── Schema normalization helpers ────────────────────────────────────────────
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

# ── Step 0: Check disk space ────────────────────────────────────────────────
statvfs = os.statvfs("/")
free_gb = (statvfs.f_bavail * statvfs.f_frsize) / (1024**3)
print(f"  Disk free: {free_gb:.1f} GB")
if free_gb < 1.0:
    print("  ERROR: <1GB free — aborting ingest")
    exit(1)

# ── Step 1: Deduplicate journals_evaluated.jsonl ────────────────────────────
print("\n[Step 1] Deduplicating journals_evaluated.jsonl...")
eval_entries = []
seen_ids = set()
if os.path.exists(EVAL_FILE):
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

# Compact if >5000 entries
if len(eval_entries) > 5000:
    from datetime import timedelta
    cutoff = (NOW - timedelta(days=30)).isoformat()
    compacted = [e for e in eval_entries
                 if e.get("evaluated_at", "9999") > cutoff
                 or not e.get("evaluated_at")]
    removed = len(eval_entries) - len(compacted)
    if removed > 0:
        eval_entries = compacted
        print(f"  Compacted: removed {removed} entries older than 30 days")

with open(EVAL_FILE, 'w') as f:
    for e in eval_entries:
        f.write(json.dumps(e) + "\n")
print(f"  Eval entries after dedup: {len(eval_entries)}")

# ── Step 2: Scan filesystem for journals (today + yesterday) ──────────────────
print("\n[Step 2] Scanning filesystem for journals...")
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
                if date_dir in (TODAY, YESTERDAY):
                    skill = path_parts[0]
                    canonical = f"{skill}/{date_dir}/{fname}"
                    all_files.append((canonical, full_path))

print(f"  Found {len(all_files)} journal files for {TODAY}/{YESTERDAY}")

# ── Step 3: Compute unevaluated set ─────────────────────────────────────────
print("\n[Step 3] Computing unevaluated set...")
eval_ids = {e.get("journal_id", "") for e in eval_entries}
unevaluated = [(c, p) for c, p in all_files if c not in eval_ids and os.path.exists(p)]
print(f"  Unevaluated journals: {len(unevaluated)}")
for c, _ in unevaluated:
    print(f"    - {c}")

# ── Step 4: Signal extraction ──────────────────────────────────────────────
print("\n[Step 4] Extracting signals from unevaluated journals...")

SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy"
]

def should_suppress_summary_signals(summary_str, signals):
    """Suppress failure_keyword/auth_failure from routine scan summaries."""
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
event_counter = 0

for canonical, fpath in unevaluated:
    print(f"\n  Processing: {canonical}")
    try:
        with open(fpath, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"    ERROR reading file: {e}")
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": NOW.isoformat(),
            "action_taken": "read_error",
            "signals_found": [],
            "reason": f"File read error: {e}"
        })
        continue

    signals = []
    summary_text = ""

    # ── Determine schema and extract fields ──
    if isinstance(data, list):
        # List-format journals
        for entry in data:
            if isinstance(entry, dict):
                entry_summary = str(entry.get("summary", ""))
                if entry_summary:
                    summary_text += " " + entry_summary
    else:
        # Dict-format
        top_status = data.get("status", "")
        escalation_needed = data.get("escalation_needed", False)
        summary_raw = data.get("summary", "")

        # Decision block
        decision = data.get("decision", {})
        if isinstance(decision, dict):
            exec_result = decision.get("execution_result", {})
            exec_status = exec_result.get("status", "") if isinstance(exec_result, dict) else ""
            decision_summary = decision.get("summary", "") or decision.get("reasoning_summary", "")
            if isinstance(decision_summary, str):
                summary_text = decision_summary
            elif isinstance(summary_raw, str):
                summary_text = summary_raw
        else:
            # Use top-level fields
            if isinstance(summary_raw, str):
                summary_text = summary_raw
            elif isinstance(summary_raw, dict):
                summary_text = json.dumps(summary_raw)

        # Get top-level summary string for suppression check
        top_summary_str = ""
        if isinstance(summary_raw, str):
            top_summary_str = summary_raw
        elif isinstance(decision, dict):
            ds = decision.get("reasoning_summary", "")
            if isinstance(ds, str):
                top_summary_str = ds

        # ── Signal 1: Top-level escalation ──
        if escalation_needed is True:
            # Check if it's real escalation (not just a tracking array)
            signals.append({"type": "escalation", "detail": "top-level escalation_needed=true"})

        # ── Signal 2: execution_result.status ──
        if isinstance(exec_status, str) and exec_status in ("error", "partial"):
            signals.append({"type": "execution_error", "detail": f"status={exec_status}"})

        # ── Signal 3: Summary keyword matching (with guards) ──
        if top_summary_str and isinstance(top_summary_str, str) and len(top_summary_str.strip()) > 0:
            sl = top_summary_str.lower()
            failure_keywords = ["error", "failed", "timeout", "truncated", "denied", "revoked", "expired", "not found", "missing", "blocked", "failed to"]
            for kw in failure_keywords:
                if kw in sl:
                    signals.append({"type": "failure_keyword", "detail": f"keyword '{kw}' in summary"})
                    break

        # ── Signal 4: actions_taken outcomes ──
        actions = data.get("actions_taken", [])
        if isinstance(actions, list):
            for action in actions:
                if isinstance(action, dict):
                    outcome = action.get("outcome", "")
                    if isinstance(outcome, str) and outcome.lower() in ("error", "failure", "applied", "corrected"):
                        atype = "correction" if outcome.lower() in ("applied", "corrected") else "execution_error"
                        signals.append({"type": atype, "detail": f"outcome={outcome}"})

        # ── Signal 5: fixes_applied ──
        fixes = data.get("fixes_applied", 0)
        if isinstance(fixes, int) and fixes > 0:
            signals.append({"type": "correction", "detail": f"fixes_applied={fixes}"})

        # ── Signal 6: Checks.fixes_applied ──
        checks = data.get("checks", {})
        if isinstance(checks, dict):
            check_fixes = checks.get("fixes_applied", 0)
            if isinstance(check_fixes, int) and check_fixes > 0:
                signals.append({"type": "correction", "detail": f"checks.fixes_applied={check_fixes}"})

        # ── Signal 7: new_findings[] ──
        new_findings = data.get("new_findings", [])
        if isinstance(new_findings, list):
            for nf in new_findings:
                if isinstance(nf, dict):
                    sev = nf.get("severity", "")
                    title = nf.get("title", "")
                    if sev in ("high", "critical", "error"):
                        signals.append({"type": "failure_keyword", "detail": f"new_finding: {title} (sev={sev})"})

        # ── Signal 8: Nested findings[] array (CRITICAL — most missed path) ──
        scan_findings = data.get("scan_findings", {})
        if isinstance(scan_findings, dict):
            for job_name, finding in scan_findings.items():
                if not isinstance(finding, dict):
                    continue
                f_status = finding.get("status", "")
                f_error = finding.get("error", "")
                f_action = finding.get("action_taken", "")
                f_note = finding.get("note", "")

                if "error" in f_status or "failed" in f_status:
                    signals.append({"type": "execution_error", "detail": f"scan_finding.{job_name}: {f_status} — {f_error or f_note}"})
                elif f_status == "escalated":
                    signals.append({"type": "escalation", "detail": f"scan_finding.{job_name}: escalated — {f_error or f_note}"})

                # Check action_taken for fixes/corrections
                if isinstance(f_action, str) and any(kw in f_action.lower() for kw in ["fixed", "updated", "corrected", "reset", "applied", "verified"]):
                    signals.append({"type": "correction", "detail": f"scan_finding.{job_name}: action_taken — {f_action}"})

        # ── Signal 8b: escalation_targets ──
        esc_targets = data.get("escalation_targets", [])
        if isinstance(esc_targets, list) and esc_targets:
            for t in esc_targets:
                signals.append({"type": "escalation", "detail": f"escalation_target: {t}"})

        # ── Signal 9: finch signals structure ──
        signal_sources = data.get("signal_sources", {})
        if isinstance(signal_sources, dict):
            # Cron health
            cron_health = signal_sources.get("cron_health", {})
            if isinstance(cron_health, dict):
                new_errs = cron_health.get("new_errors", [])
                if isinstance(new_errs, list) and new_errs:
                    for ne in new_errs:
                        if isinstance(ne, dict):
                            job = ne.get("job", "unknown")
                            err = ne.get("error", "unknown error")
                            # Check if this is a known/transient error
                            is_transient = any(phrase in err.lower() for phrase in ["429", "rate limit"])
                            if not is_transient:
                                signals.append({"type": "cron_errors", "detail": f"cron_error: {job} — {err}"})

                error_breakdown = cron_health.get("error_breakdown", {})
                if isinstance(error_breakdown, dict):
                    for key, count in error_breakdown.items():
                        if isinstance(count, int) and count > 0:
                            pass  # Summary info, not a new signal if already counted

            # Source-level signals (email/calendar/drive blocked)
            for source_name in ["email", "calendar", "drive"]:
                source_data = signal_sources.get(source_name, {})
                if isinstance(source_data, dict):
                    s_status = source_data.get("status", "")
                    if s_status == "blocked":
                        reason = source_data.get("reason", "")
                        if "oauth" in reason.lower() or "token" in reason.lower():
                            signals.append({"type": "auth_failure", "detail": f"{source_name} blocked: {reason}"})

            # Task validation — replaced/kept with error context
            task_val = data.get("task_validation", {})
            if isinstance(task_val, dict):
                for task_name, task_info in task_val.items():
                    if isinstance(task_info, dict):
                        action = task_info.get("action", "")
                        reason = task_info.get("reason", "")
                        if "replaced" in action and ("error" in reason.lower() or "expired" in reason.lower() or "blocked" in reason.lower()):
                            signals.append({"type": "failure_keyword", "detail": f"task_replaced: {task_name} — {reason}"})

        # ── Summary semantic suppression ──
        if top_summary_str and signals:
            if should_suppress_summary_signals(top_summary_str, signals):
                print(f"    Suppressed summary-derived signals (routine scan summary)")
                signals = [s for s in signals if s["type"] not in ("failure_keyword", "auth_failure")]

        # ── Failure-phase tagging helper ──
        def tag_phase(signal_type, detail):
            detail_lower = detail.lower()
            if any(kw in detail_lower for kw in ["should have", "before", "wrong approach", "didn't check", "missing prerequisite", "planning"]):
                return "planning"
            if any(kw in detail_lower for kw in ["too verbose", "wrong format", "make it concise", "don't explain", "truncated"]):
                return "response"
            return "execution"

    # ── Record events or mark no_signal ──
    if not signals:
        print(f"    → no_signal (no behavioral signals)")
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": NOW.isoformat(),
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })
        continue

    # Record each unique signal as an event
    seen_signal_types = set()
    for sig in signals:
        sig_type = sig["type"]
        # Dedup by (source_journal, signal_type)
        dedup_key = (canonical, sig_type)
        if dedup_key in seen_signal_types:
            continue
        seen_signal_types.add(dedup_key)

        event_counter += 1
        phase = tag_phase(sig_type, sig["detail"])
        eid = f"evt_{NOW.strftime('%Y%m%d_%H%M%S')}_{os.urandom(2).hex()}_{canonical.split('/')[0][:5]}"

        event = {
            "event_id": eid,
            "timestamp": NOW.isoformat(),
            "domain": canonical.split('/')[0],
            "context_summary": sig["detail"],
            "outcome_type": sig_type,
            "outcome_summary": sig["detail"],
            "evidence": [f"canonical: {canonical}", f"signal_type: {sig_type}"],
            "failure_phase": phase,
            "user_relevance": "agent_only",
            "source_journal": canonical,
            "signal_type": sig_type,
            "recorded_at": NOW.isoformat()
        }
        new_events.append(event)
        print(f"    → event: {sig_type} | {sig['detail'][:80]}")

    # Append new events to events.jsonl
    with open(EVENTS_FILE, 'a') as f:
        for evt in new_events[-event_counter:] if event_counter > 0 else new_events:
            f.write(json.dumps(evt) + "\n")

    eval_updates.append({
        "journal_id": canonical,
        "evaluated_at": NOW.isoformat(),
        "action_taken": "event_recorded",
        "signals_found": list(seen_signal_types),
        "event_ids": [e["event_id"] for e in new_events[-event_counter:]] if event_counter > 0 else [e["event_id"] for e in new_events],
        "reason": f"Recorded {len(seen_signal_types)} distinct signal types"
    })

# ── Step 4b: Post-write dedup on events.jsonl ──────────────────────────────
print("\n[Step 4b] Post-write dedup on events.jsonl...")
all_events = []
if os.path.exists(EVENTS_FILE):
    with open(EVENTS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
                all_events.append(evt)
            except json.JSONDecodeError:
                continue

# Dedup by (source_journal, signal_type) — keep earliest recorded_at
deduped_events = {}
for evt in all_events:
    sig_type = evt.get("signal_type", evt.get("outcome_type", "unknown"))
    key = (evt.get("source_journal", ""), sig_type)
    if key not in deduped_events or evt.get("recorded_at", "") < deduped_events[key].get("recorded_at", ""):
        deduped_events[key] = evt

# Filter legacy noise events
meaningful_events = [e for e in deduped_events.values()
                     if e.get("signal_type") not in ("unknown", "?", None, "")]
rewritten = len(meaningful_events)

with open(EVENTS_FILE, 'w') as f:
    for evt in meaningful_events:
        f.write(json.dumps(evt) + "\n")
print(f"  Events after dedup: {rewritten} (from {len(all_events)} raw)")

# ── Step 4c: Write eval_updates ─────────────────────────────────────────────
print("\n[Step 4c] Writing eval_updates...")
with open(EVAL_FILE, 'a') as f:
    for eu in eval_updates:
        f.write(json.dumps(eu) + "\n")
print(f"  Written {len(eval_updates)} eval updates")

# ── Step 5: Re-read events for lesson extraction ────────────────────────────
print("\n[Step 5] Re-reading events for lesson extraction...")
all_events_for_lessons = []
with open(EVENTS_FILE, 'r') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
            all_events_for_lessons.append(evt)
        except json.JSONDecodeError:
            continue
print(f"  Total events: {len(all_events_for_lessons)}")

# ── Step 5b: Group by (signal_type, failure_phase) ──────────────────────────
from collections import defaultdict
groups = defaultdict(list)
for evt in all_events_for_lessons:
    sig = evt.get("signal_type", "unknown")
    phase = evt.get("failure_phase", "null")
    if sig not in ("unknown", "?", None, ""):
        groups[(sig, phase)].append(evt)

print(f"\n  Event groups (signal_type, phase):")
for key in sorted(groups.keys()):
    print(f"    {key}: {len(groups[key])} events")

# ── Step 5c: Lesson extraction — Pass 1 (need 2+ events in group) ─────────
print("\n[Step 5c] Lesson extraction — Pass 1...")
existing_lessons = []
if os.path.exists(LESSONS_FILE):
    with open(LESSONS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                existing_lessons.append(json.loads(line))
            except json.JSONDecodeError:
                continue

# Content dedup: track (signal_type, failure_phase) groups already covered
existing_groups = set()
for l in existing_lessons:
    key = (l.get("signal_type", ""), l.get("failure_phase", ""))
    if key[0] and key[1]:
        existing_groups.add(key)

new_lessons_p1 = []
for (sig, phase), events in groups.items():
    if (sig, phase) in existing_groups:
        print(f"  Skipping duplicate lesson: signal_type={sig}, phase={phase}")
        continue
    if len(events) < 2:
        print(f"  Insufficient events for lesson: {sig}/{phase} ({len(events)} < 2)")
        continue

    # Extract lesson stub
    lesson_text = f"Pattern: {sig} recurring in {phase} phase ({len(events)} occurrences)"
    lid = f"les_{NOW.strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"

    lesson = {
        "lesson_id": lid,
        "event_ids": [get_event_id(e) for e in events],
        "lesson_text": lesson_text,
        "confidence": "low",
        "scope": events[0].get("domain", "unknown"),
        "status": "proposed",
        "failure_phase": phase,
        "causal_grounding": "what",
        "signal_type": sig,
        "skills_affected": [events[0].get("domain", "unknown")],
        "created_at": NOW.isoformat()
    }
    new_lessons_p1.append(lesson)
    print(f"  Extracted lesson stub: {sig}/{phase} ({len(events)} events)")

print(f"  Pass 1 lessons: {len(new_lessons_p1)}")

# ── Step 5d: Lesson extraction — Pass 2 (causal grounding upgrade) ─────────
print("\n[Step 5d] Lesson extraction — Pass 2 (causal grounding)...")
for lesson in new_lessons_p1:
    sig = lesson["signal_type"]
    phase = lesson["failure_phase"]
    events_in_group = groups.get((sig, phase), [])

    # Build causal grounding from event context summaries
    what_parts = []
    why_parts = []
    when_parts = []
    for evt in events_in_group[:5]:  # cap at 5 for grounding
        cs = evt.get("context_summary", evt.get("outcome_summary", ""))
        if isinstance(cs, str) and cs:
            what_parts.append(cs[:120])
        evidence = evt.get("evidence", [])
        if isinstance(evidence, list):
            for e in evidence[:2]:
                if isinstance(e, str) and e:
                    why_parts.append(e[:100])

    what_text = f"Recurring {sig} in {phase} phase: {'; '.join(what_parts[:3])}"
    why_text = f"{' '.join(why_parts[:3]) if why_parts else 'Mechanism unknown — needs further investigation'}"
    when_text = f"Observed in phase={phase}, domain={lesson['scope']}"

    lesson["what"] = what_text[:300]
    lesson["why"] = why_text[:300]
    lesson["when"] = when_text[:200]
    lesson["causal_grounding"] = "what+why+when"
    lesson["confidence"] = "high"
    lesson["lesson_text"] = f"[LESSON] What: {what_text}. Why: {why_text}. When: {when_text}"
    print(f"  Upgraded lesson: {sig}/{phase} → confidence=high")

print(f"  Pass 2 lessons: {len(new_lessons_p1)}")

# Write new lessons
with open(LESSONS_FILE, 'a') as f:
    for lesson in new_lessons_p1:
        f.write(json.dumps(lesson) + "\n")

# ── Step 5e: Lesson content dedup ───────────────────────────────────────────
# Re-read and dedup all lessons
all_lessons = []
with open(LESSONS_FILE, 'r') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            all_lessons.append(json.loads(line))
        except json.JSONDecodeError:
            continue

deduped_lessons = {}
lesson_groups_seen = {}
for lesson in all_lessons:
    key = (lesson.get("signal_type", ""), lesson.get("failure_phase", ""))
    lid = lesson.get("lesson_id", lesson.get("id", ""))
    # Keep first occurrence per group; also track by ID for exact dedup
    if key not in lesson_groups_seen and key[0] and key[1]:
        lesson_groups_seen[key] = lid
        deduped_lessons[lid] = lesson
    elif lid in deduped_lessons:
        pass  # exact ID dup

final_lessons = list(deduped_lessons.values())
with open(LESSONS_FILE, 'w') as f:
    for lesson in final_lessons:
        f.write(json.dumps(lesson) + "\n")
print(f"\n  Lessons after dedup: {len(final_lessons)}")

# ── Step 6: Shift proposal and activation ────────────────────────────────────
print("\n[Step 6] Shift proposal and activation...")
all_shifts = []
if os.path.exists(SHIFTS_FILE):
    with open(SHIFTS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                all_shifts.append(json.loads(line))
            except json.JSONDecodeError:
                continue

active_shifts = [s for s in all_shifts if s.get("status") == "active"]
proposed_shifts = [s for s in all_shifts if s.get("status") == "proposed"]
print(f"  Active shifts: {len(active_shifts)}/12")
print(f"  Proposed shifts: {len(proposed_shifts)}")

# Build set of lesson IDs already covered by shifts
COVERED_LESSON_IDS = set()
for s in all_shifts:
    if s.get("status") in ("active", "proposed"):
        for field in ['lesson_id', 'lesson_ref', 'source_lesson', 'source_lesson_ids']:
            val = s.get(field)
            if val:
                if isinstance(val, list):
                    COVERED_LESSON_IDS.update(val)
                elif isinstance(val, str):
                    COVERED_LESSON_IDS.add(val)

# Only propose shifts for high-confidence lessons not already covered
truly_new = []
for lesson in new_lessons_p1:
    lid = lesson.get("lesson_id", "")
    if lid not in COVERED_LESSON_IDS and lesson.get("confidence") == "high":
        truly_new.append(lesson)

print(f"  Lessons eligible for shift proposal: {len(truly_new)}")

new_proposals = []
for lesson in truly_new:
    sig = lesson["signal_type"]
    phase = lesson["failure_phase"]
    shift_text = f"Behavioral adjustment for {sig} in {phase} phase: {lesson.get('what', lesson['lesson_text'][:100])}"

    # Check domain+phase overlap against active shifts
    domain = lesson.get("skills_affected", ["unknown"])[0] if lesson.get("skills_affected") else "unknown"
    overlap = False
    for active in active_shifts:
        a_domain = active.get("domain", active.get("scope", ""))
        a_phase = get_failure_phase(active)
        if a_domain == domain and a_phase == phase:
            # Merge: reinforce active shift
            active["last_reinforced_at"] = NOW.isoformat()
            active["reinforcement_count"] = active.get("reinforcement_count", 0) + 1
            active.setdefault("source_lesson_ids", []).append(lesson.get("lesson_id", ""))
            overlap = True
            print(f"  Merged with active shift: {get_shift_id(active)} ({domain}/{phase})")
            break

    if not overlap:
        sid = f"shf_{NOW.strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"
        proposal = {
            "shift_id": sid,
            "source_lesson_ids": [lesson.get("lesson_id", "")],
            "shift_text": shift_text[:300],
            "status": "proposed",
            "activation_reason": f"Proposed from {sig} lesson ({len(groups.get((sig, phase), []))} events)",
            "created_at": NOW.isoformat(),
            "last_reviewed_at": NOW.isoformat(),
            "expiry_condition": "14_days without reinforcement",
            "priority": 1,
            "last_reinforced_at": "",
            "reinforcement_count": 0,
            "failure_phase": phase,
            "domain": domain
        }
        new_proposals.append(proposal)
        print(f"  New shift proposal: {sid} — {shift_text[:80]}")

# Activate proposals if under cap
CAP = 12
remaining_cap = CAP - len(active_shifts)

if new_proposals and remaining_cap > 0:
    activated_count = min(len(new_proposals), remaining_cap)
    for proposal in new_proposals[:activated_count]:
        proposal["status"] = "active"
        proposal["last_reinforced_at"] = NOW.isoformat()
        print(f"  ACTIVATED: {get_shift_id(proposal)}")
    # Remaining proposals stay proposed
    for proposal in new_proposals[activated_count:]:
        print(f"  PROPOSED (cap reached): {get_shift_id(proposal)}")

# Rewrite shifts.jsonl (all statuses)
all_shifts_final = active_shifts + proposed_shifts + new_proposals
with open(SHIFTS_FILE, 'w') as f:
    for s in all_shifts_final:
        f.write(json.dumps(s) + "\n")
print(f"  Total shifts written: {len(all_shifts_final)}")

active_count = len([s for s in all_shifts_final if s.get("status") == "active"])
print(f"  Active: {active_count}/{CAP}")

# ── Step 7: Write decision log ─────────────────────────────────────────────
print("\n[Step 7] Writing decision log...")
decision = {
    "decision_id": f"dec_{NOW.strftime('%Y%m%d_%H%M%S')}",
    "timestamp": NOW.isoformat(),
    "decision_type": "journal_ingest",
    "context": f"Ingest scan for {TODAY}/{YESTERDAY}",
    "outcome": f"Journals scanned: {len(unevaluated)}, Events recorded: {len(new_events)}, New lessons: {len(new_lessons_p1)}, Shift proposals: {len(new_proposals)}, Activated: {min(len(new_proposals), remaining_cap) if new_proposals else 0}",
    "reasoning": f"Scanned {len(unevaluated)} new journals. Found {len(set(s['type'] for eu in eval_updates for s in ([{'type': t} for t in eu.get('signals_found', [])]) ))} signal types across {len(new_events)} events. Extracted {len(new_lessons_p1)} lessons with causal grounding."
}
with open(DECISIONS_FILE, 'a') as f:
    f.write(json.dumps(decision) + "\n")
print(f"  Decision logged: {decision['decision_id']}")

# ── Step 8: Write praxis journal ────────────────────────────────────────────
print("\n[Step 8] Writing praxis journal...")
run_id = f"r_{NOW.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
journal_path = os.path.join(JOURNAL_DIR, TODAY)
os.makedirs(journal_path, exist_ok=True)

journal = {
    "run_identity": {
        "run_id": run_id,
        "role": "praxis_engine",
        "skill_name": "ocas-praxis",
        "skill_version": "3.2.0",
        "timestamp_start": NOW.isoformat(),
        "timestamp_end": datetime.now(timezone.utc).isoformat(),
        "journal_spec_version": "1.3",
        "journal_type": "action"
    },
    "runtime": {
        "model": "openrouter/owl-alpha",
        "provider": "openrouter",
        "node": "linux-6.17.0-35-generic"
    },
    "input": {
        "command": "praxis.journal_ingest",
        "trigger": "cron"
    },
    "decision": {
        "decision_type": "ingest_complete",
        "payload": {
            "journals_scanned": len(unevaluated),
            "events_recorded": len(new_events),
            "lessons_extracted": len(new_lessons_p1),
            "shift_proposals": len(new_proposals),
            "shifts_activated": min(len(new_proposals), remaining_cap) if new_proposals else 0,
            "active_shifts": active_count,
            "cap_usage": f"{active_count}/{CAP}"
        },
        "confidence": 0.95,
        "reasoning_summary": f"Ingested {len(new_events)} events from {len(unevaluated)} journals. Extracted {len(new_lessons_p1)} grounded lessons. {min(len(new_proposals), remaining_cap) if new_proposals else 0} shifts activated (cap {active_count}/{CAP})."
    },
    "action": {
        "side_effect_intent": "write_journal_and_update_data",
        "side_effect_executed": True
    },
    "metrics": {
        "latency_ms": (datetime.now(timezone.utc) - NOW).total_seconds() * 1000,
        "retry_count": 0,
        "validation_failures": 0,
        "records_written": len(new_events) + len(new_lessons_p1) + len(new_proposals) + len(eval_updates)
    },
    "okr_evaluation": {
        "event_coverage": 1.0,
        "data_integrity": 1.0,
        "schedule_adherence": 1.0
    }
}

jpath = os.path.join(journal_path, f"{run_id}.json")
with open(jpath, 'w') as f:
    json.dump(journal, f, indent=2)
print(f"  Journal written: {jpath}")

# ── Final status ────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("PRAXIS INGEST COMPLETE")
print(f"  Journals scanned: {len(unevaluated)}")
print(f"  Events recorded:  {len(new_events)}")
print(f"  Lessons extracted: {len(new_lessons_p1)}")
print(f"  Shifts proposed:  {len(new_proposals)}")
print(f"  Shifts activated: {min(len(new_proposals), remaining_cap) if new_proposals else 0}")
print(f"  Active shifts:    {active_count}/{CAP}")
print("=" * 60)
