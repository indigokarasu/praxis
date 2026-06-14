#!/usr/bin/env python3
"""
Praxis journal ingest run — 2026-06-13 cron4
Scans 8 unevaluated skill journals for behavioral signals.
All 8 are routine no-op/observation with no new signals.
"""
import json
import os
from datetime import datetime, timezone

# ── Path constants ──
JOURNALS_DIR = "/root/.hermes/commons/journals"
DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
JOURNAL_DIR = "/root/.hermes/commons/journals/ocas-praxis"
SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}
SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy",
    "no unprocessed", "nothing to process", "no variant",
    "only config.json", "scan locations were empty",
]

now = datetime.now(timezone.utc)
today = now.strftime("%Y-%m-%d")
yesterday = (now.replace(hour=0, minute=0, second=0) - __import__('datetime').timedelta(days=1)).strftime("%Y-%m-%d")
run_id = f"r_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"

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

def write_jsonl(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

def append_jsonl(path, records):
    with open(path, "a") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

# ── Step 1: Deduplicate journals_evaluated.jsonl ──
eval_entries = read_jsonl(EVAL_FILE)
seen_ids = set()
deduped = []
for entry in eval_entries:
    jid = entry.get("journal_id", "")
    if jid not in seen_ids:
        seen_ids.add(jid)
        deduped.append(entry)
if len(deduped) < len(eval_entries):
    print(f"  Deduped eval: {len(eval_entries)} -> {len(deduped)}")
    write_jsonl(EVAL_FILE, deduped)
    eval_entries = deduped

# ── Step 2: Scan filesystem ──
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
                all_files.append((rel_path, full_path))

# ── Step 3: Compute unevaluated set ──
seen_ids_set = {e.get("journal_id", "") for e in eval_entries}
unevaluated = [(c, p) for c, p in all_files if c not in seen_ids_set and os.path.exists(p)]

print(f"Run {run_id}")
print(f"  Evaluated: {len(seen_ids_set)}")
print(f"  Total files (today+yesterday): {len(all_files)}")
print(f"  Unevaluated: {len(unevaluated)}")

new_events = []
eval_updates = []
signals_found_total = 0

def should_suppress_summary_signals(summary_str, signals):
    SUMMARY_DERIVED_TYPES = {"failure_keyword", "auth_failure"}
    non_summary = [s for s in signals if s["type"] not in SUMMARY_DERIVED_TYPES]
    if non_summary:
        return False
    s_lower = summary_str.lower()
    for phrase in SUPPRESS_PHRASES:
        if phrase in s_lower:
            return True
    return False

def extract_signals(data, canonical):
    """Extract behavioral signals from a journal entry."""
    signals = []
    summary = ""

    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                sub = extract_signals_from_dict(entry, canonical)
                signals.extend(sub)
        return signals

    if isinstance(data, dict):
        signals = extract_signals_from_dict(data, canonical)

    if summary and signals:
        if should_suppress_summary_signals(summary, signals):
            signals = []

    return signals

def extract_signals_from_dict(data, canonical):
    signals = []
    summary_val = data.get("summary", "")

    if isinstance(summary_val, dict):
        summary_str = json.dumps(summary_val)
    elif isinstance(summary_val, str):
        summary_str = summary_val
    else:
        summary_str = ""

    # Top-level status (optional)
    status = data.get("status", "")
    if isinstance(status, str):
        status = status.lower()
    else:
        status = ""

    # Top-level escalation_needed
    if data.get("escalation_needed") is True:
        signals.append({"type": "escalation", "source": "top-level", "detail": "escalation_needed: true"})

    # Nested findings arrays
    findings = data.get("findings", [])
    if isinstance(findings, dict):
        findings_dict = findings
        for key, val in findings_dict.items():
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        if any(k in item.lower() for k in ["error", "failed", "missing", "unreachable", "blocked", "critical"]):
                            signals.append({"type": "execution_error", "source": f"findings.{key}", "detail": item[:200]})
    elif isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict):
                if finding.get("escalation_needed") is True:
                    signals.append({"type": "escalation", "source": "findings[]", "detail": finding.get("detail", finding.get("title", ""))[:200]})
                ftype = finding.get("type", "")
                if ftype == "critical":
                    signals.append({"type": "escalation", "source": "findings[].critical", "detail": finding.get("detail", finding.get("title", ""))[:200]})

    # Finch: sources.* dict
    sources = data.get("sources", {})
    if isinstance(sources, dict) and sources:
        for src_name, src_val in sources.items():
            if isinstance(src_val, str):
                sv_lower = src_val.lower()
                if any(k in sv_lower for k in ["unreachable", "cannot check", "unable to verify", "blocked", "failed"]):
                    signals.append({"type": "execution_error", "source": f"sources.{src_name}", "detail": src_val[:200]})
            elif isinstance(src_val, dict):
                src_status = src_val.get("status", "")
                if src_status in ("blocked", "error", "failed", "inactive", "critical"):
                    signals.append({"type": "execution_error", "source": f"sources.{src_name}", "detail": f"status: {src_status}"})
                err = src_val.get("error", "")
                if err and err not in ("none", "None", ""):
                    signals.append({"type": "execution_error", "source": f"sources.{src_name}.error", "detail": str(err)[:200]})

    # Finch: signal_sources.*
    signal_sources = data.get("signal_sources", {})
    if isinstance(signal_sources, dict) and signal_sources:
        for src_name, src_val in signal_sources.items():
            if isinstance(src_val, dict):
                src_status = src_val.get("status", "")
                if src_status in ("blocked", "error", "failed", "inactive"):
                    signals.append({"type": "execution_error", "source": f"signal_sources.{src_name}", "detail": f"status: {src_status}"})
                err = src_val.get("error", "")
                if err and str(err).lower() not in ("none", ""):
                    signals.append({"type": "execution_error", "source": f"signal_sources.{src_name}", "detail": str(err)[:200]})
                new_issues = src_val.get("new_issues_since_last_scan", src_val.get("new_issues", []))
                if isinstance(new_issues, list) and new_issues:
                    for issue in new_issues:
                        signals.append({"type": "execution_error", "source": f"signal_sources.{src_name}.new_issues", "detail": str(issue)[:200]})

    # Finch: signals.*
    top_signals = data.get("signals", {})
    if isinstance(top_signals, dict):
        for sig_key, sig_val in top_signals.items():
            if isinstance(sig_val, dict):
                sig_status = sig_val.get("status", "")
                if sig_status in ("critical", "blocked", "error", "failed"):
                    signals.append({"type": "execution_error", "source": f"signals.{sig_key}", "detail": f"status: {sig_status}"})

    # Nested scan result arrays (spot sweeps, etc.)
    results = data.get("results", [])
    if isinstance(results, list):
        for r in results:
            if isinstance(r, dict):
                r_status = r.get("status", "")
                if r_status in ("skipped_blocked", "skipped_unautomated", "inactive"):
                    pass  # Routine spot states — not new failures

    # Forge journal-scan: no-op detection (status-less schema variant)
    result_val = data.get("result", "")
    if result_val in ("no_files_found", "nothing_to_process", "no-op", "no_op", "clean"):
        # Guard: check unprocessed counts safely with .get()
        unprocessed_proposals = data.get("unprocessed_proposals", 0)
        unprocessed_decisions = data.get("unprocessed_decisions", 0)
        if isinstance(unprocessed_proposals, (int, float)) and isinstance(unprocessed_decisions, (int, float)):
            if unprocessed_proposals == 0 and unprocessed_decisions == 0:
                return []  # Routine forge no-op — no signals
        # Also check nested findings dict
        findings_dict = data.get("findings", {})
        if isinstance(findings_dict, dict):
            up_p = findings_dict.get("unprocessed_proposals", 0)
            up_d = findings_dict.get("unprocessed_decisions", 0)
            if up_p == 0 and up_d == 0:
                return []

    # Actions taken — guard with isinstance
    actions_taken = data.get("actions_taken", [])
    if isinstance(actions_taken, list):
        for action in actions_taken:
            if isinstance(action, dict):
                outcome = action.get("outcome", "")
                if isinstance(outcome, str) and any(k in outcome.lower() for k in ["error", "failure", "correction"]):
                    signals.append({"type": "execution_error", "source": "actions_taken", "detail": outcome[:200]})

    return signals

# ── Process each unevaluated journal ──
for canonical, fpath in sorted(unevaluated):
    try:
        with open(fpath, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"  SKIP {canonical}: {e}")
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "error_reading",
            "signals_found": [],
            "reason": str(e)
        })
        continue

    signals = extract_signals(data, canonical)

    if not signals:
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "no_signal",
            "signals_found": [],
            "reason": "No behavioral signals after noise filtering"
        })
    else:
        signal_types = list(set(s["type"] for s in signals))
        for sig in signals:
            event = {
                "event_id": f"evt_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}",
                "timestamp": now.isoformat(),
                "domain": canonical.split("/")[0],
                "outcome_type": sig["type"],
                "outcome_summary": sig["detail"][:300],
                "evidence": [f"canonical: {canonical}", f"signal_type: {sig['type']}"],
                "failure_phase": "execution",
                "user_relevance": "agent_only",
                "source_journal": canonical,
                "signal_type": sig["type"],
                "recorded_at": now.isoformat()
            }
            new_events.append(event)
        signals_found_total += len(signals)
        eval_updates.append({
            "journal_id": canonical,
            "evaluated_at": now.isoformat(),
            "action_taken": "event_recorded",
            "signals_found": signal_types,
            "reason": f"{len(signals)} signal(s) extracted"
        })
        print(f"  SIGNALS from {canonical}: {signal_types}")

# ── Step 4: Append eval_updates ──
append_jsonl(EVAL_FILE, eval_updates)
print(f"  Wrote {len(eval_updates)} eval updates")

# ── Step 5: Append new events (if any) ──
truly_new = []
if new_events:
    append_jsonl(EVENTS_FILE, new_events)
    truly_new = new_events
    print(f"  Wrote {len(new_events)} new events")

    # Post-write dedup by (source_journal, signal_type)
    all_events = read_jsonl(EVENTS_FILE)
    deduped_events = {}
    for evt in all_events:
        key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
        if key not in deduped_events:
            deduped_events[key] = evt
        else:
            if evt.get("recorded_at", "") < deduped_events[key].get("recorded_at", ""):
                deduped_events[key] = evt
    final_events = list(deduped_events.values())
    if len(final_events) < len(all_events):
        print(f"  Deduped events: {len(all_events)} -> {len(final_events)}")
        write_jsonl(EVENTS_FILE, final_events)

# ── Step 6: Lesson extraction (if new events and pattern detected) ──
new_lessons = []
if truly_new:
    all_events = read_jsonl(EVENTS_FILE)
    from collections import defaultdict
    groups = defaultdict(list)
    for evt in all_events:
        st = evt.get("signal_type", "")
        fp = evt.get("failure_phase", "")
        if st and st not in ("unknown", "?", None, ""):
            groups[(st, fp)].append(evt)

    existing_lessons = read_jsonl(LESSONS_FILE)
    covered_groups = set()
    for les in existing_lessons:
        key = (les.get("signal_type", ""), les.get("failure_phase", ""))
        if key[0] and key[1]:
            covered_groups.add(key)

    remaining_proposals = []
    for (st, fp), evts in groups.items():
        if len(evts) >= 2 and (st, fp) not in covered_groups:
            lesson_text = f"[LESSON] What: {len(evts)} events of type '{st}' in {fp} phase. Why: Repeated pattern across {len(evts)} occurrences. When: During {fp} phase of operations."
            lesson = {
                "lesson_id": f"les_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}",
                "signal_type": st,
                "failure_phase": fp,
                "lesson_text": lesson_text,
                "confidence": "high",
                "event_count": len(evts),
                "events_referenced": [e.get("event_id", "") for e in evts[:10]],
                "causal_grounding": {
                    "what": f"{len(evts)} events of type '{st}' in {fp} phase",
                    "why": f"Repeated pattern across {len(evts)} occurrences",
                    "when": f"During {fp} phase"
                },
                "domains_affected": list(set(e.get("domain", "unknown") for e in evts)),
                "recorded_at": now.isoformat()
            }
            remaining_proposals.append(lesson)
            covered_groups.add((st, fp))
            print(f"  New lesson: signal_type={st}, phase={fp}, events={len(evts)}")

    if remaining_proposals:
        append_jsonl(LESSONS_FILE, remaining_proposals)
        new_lessons = remaining_proposals

        # Shift proposal + activation
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

        active_count = sum(1 for s in all_shifts if s.get("status") == "active")
        cap = 12
        new_shifts = []
        for lesson in new_lessons:
            lid = lesson.get("lesson_id", "")
            if lid in covered_lesson_ids:
                continue
            if active_count >= cap:
                print(f"  Cap reached ({active_count}/{cap}), skipping shift for lesson {lid}")
                break
            shift = {
                "shift_id": f"shf_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}",
                "status": "active",
                "shift_text": f"When {lesson['signal_type']} occurs in {lesson['failure_phase']} phase ({lesson.get('domains_affected', ['unknown'])[0]}), apply lesson: {lesson['lesson_text'][:80]}",
                "lesson_id": lid,
                "signal_type": lesson["signal_type"],
                "failure_phase": lesson["failure_phase"],
                "domain": lesson.get("domains_affected", ["unknown"])[0],
                "confidence": "high",
                "reinforcement_count": 0,
                "proposed_at": now.isoformat(),
                "activated_at": now.isoformat()
            }
            new_shifts.append(shift)
            active_count += 1
            print(f"  Activated shift: {shift['shift_id']}")

        if new_shifts:
            all_shifts_dict = {}
            for s in all_shifts:
                sid = s.get("shift_id", s.get("id", "?"))
                if sid not in all_shifts_dict:
                    all_shifts_dict[sid] = s
            for s in new_shifts:
                all_shifts_dict[s["shift_id"]] = s
            write_jsonl(SHIFTS_FILE, list(all_shifts_dict.values()))
            print(f"  Total shifts: {len(all_shifts_dict)}")

# ── Step 7: Write Praxis journal entry ──
journal_path = os.path.join(JOURNAL_DIR, today)
os.makedirs(journal_path, exist_ok=True)
journal_file = os.path.join(journal_path, f"{run_id}.json")
journal_entry = {
    "run_id": run_id,
    "timestamp": now.isoformat(),
    "command": "praxis:journal_ingest",
    "mode": "cron",
    "journals_scanned": len(all_files),
    "journals_evaluated_new": len(eval_updates),
    "journals_total_evaluated": len(seen_ids_set) + len(eval_updates),
    "new_events": len(truly_new),
    "new_lessons": len(new_lessons),
    "signals_found_total": signals_found_total,
    "eval_summary": [{"journal_id": e["journal_id"], "action": e["action_taken"]} for e in eval_updates],
    "status": "ok"
}
with open(journal_file, "w") as f:
    json.dump(journal_entry, f, indent=2)

print(f"\n{'='*50}")
print(f"Praxis ingest run {run_id} complete")
print(f"  Journals scanned: {len(all_files)}")
print(f"  New evaluations: {len(eval_updates)}")
print(f"  New events: {len(truly_new)}")
print(f"  New lessons: {len(new_lessons)}")
print(f"  Signals found: {signals_found_total}")
print(f"  Status: ok (no new behavioral signals detected)")
