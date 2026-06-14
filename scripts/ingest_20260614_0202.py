#!/usr/bin/env python3
"""
Praxis Journal Ingest Run — 2026-06-14 02:02 UTC
Scans all skill journals for new entries, extracts behavioral signals,
records events, extracts lessons, proposes/activates shifts.
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

# === PATHS (absolute literals — os.path.join strips leading dot) ===
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
    "operational", "healthy"
]
FORGE_NO_OP_RESULTS = {"no_op", "clean"}
SUMMARY_DERIVED_TYPES = {"failure_keyword", "auth_failure"}


def get_event_id(evt):
    return evt.get("event_id", evt.get("id", ""))


def get_lesson_id(les):
    return les.get("lesson_id", les.get("id", ""))


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
    non_summary_signals = [s for s in signals if s["type"] not in SUMMARY_DERIVED_TYPES]
    if non_summary_signals:
        return False
    summary_lower = summary_str.lower()
    for phrase in SUPPRESS_PHRASES:
        if phrase in summary_lower:
            return True
    return False


def _extract_finch_signals(data):
    signals = []
    signals_data = data.get("signals", {})
    if not isinstance(signals_data, dict):
        return signals

    cron_data = signals_data.get("cron", {})
    if isinstance(cron_data, dict):
        new_errors = cron_data.get("new_errors", [])
        if isinstance(new_errors, list) and len(new_errors) > 0:
            signals.append({"type": "cron_errors", "source": "finch_cron_new_errors", "count": len(new_errors)})

        error_breakdown = cron_data.get("error_breakdown", {})
        if isinstance(error_breakdown, dict):
            for err_type, count in error_breakdown.items():
                if isinstance(count, (int, float)) and count > 0:
                    signals.append({"type": "cron_errors", "source": "finch_error_breakdown", "error_type": err_type, "count": count})

    tasks_added = data.get("tasks_added", [])
    if isinstance(tasks_added, list):
        for task in tasks_added:
            if isinstance(task, str) and any(kw in task.lower() for kw in ["error", "fail", "missing", "blocked", "unreachable"]):
                signals.append({"type": "failure_keyword", "source": "finch_tasks_added", "task": task})

    return signals


def extract_signals(journal_data, canonical):
    signals = []
    summary = ""
    skill = canonical.split("/")[0] if "/" in canonical else ""

    if isinstance(journal_data, list):
        for entry in journal_data:
            if isinstance(entry, dict):
                sub = _extract_from_dict(entry, skill)
                signals.extend(sub)
        return _dedup_signals(signals)

    if isinstance(journal_data, dict):
        signals = _extract_from_dict(journal_data, skill)
        return _dedup_signals(signals)

    return []


def _dedup_signals(signals):
    seen_types = set()
    deduped = []
    for s in signals:
        st = s["type"]
        if st not in seen_types:
            seen_types.add(st)
            deduped.append(s)
    return deduped


def _extract_from_dict(data, skill):
    signals = []
    summary = ""

    # 1. Top-level escalation_needed
    if data.get("escalation_needed") is True:
        signals.append({"type": "escalation", "source": "top_level"})

    # 2. decision.execution_result.status
    decision = data.get("decision", {})
    if isinstance(decision, dict):
        exec_result = decision.get("execution_result", {})
        if isinstance(exec_result, dict):
            status = exec_result.get("status", "")
            if status in ("error", "partial", "completed_with_errors"):
                signals.append({"type": "execution_error", "source": "execution_result", "status": status})

        dec_summary = decision.get("summary", "")
        if isinstance(dec_summary, str) and dec_summary.strip():
            summary = dec_summary

    # 3. Top-level status
    top_status = data.get("status", "")
    if top_status in ("error", "partial", "completed_with_errors"):
        signals.append({"type": "execution_error", "source": "top_status", "status": top_status})

    # 4. Top-level summary
    if not summary:
        tl_summary = data.get("summary", "")
        if isinstance(tl_summary, str) and tl_summary.strip():
            summary = tl_summary
        elif isinstance(tl_summary, dict):
            summary = json.dumps(tl_summary)

    # 5. actions_taken
    actions = data.get("actions_taken", [])
    if isinstance(actions, list):
        for action in actions:
            if isinstance(action, dict):
                outcome = str(action.get("outcome", "")).lower()
                if any(kw in outcome for kw in ["error", "failure", "failed"]):
                    signals.append({"type": "execution_error", "source": "actions_taken"})
                if "fix" in outcome or "correct" in outcome:
                    signals.append({"type": "correction", "source": "actions_taken_fix"})

    # 6. fixes_applied
    fixes = data.get("fixes_applied", 0)
    if isinstance(fixes, (int, float)) and fixes > 0:
        signals.append({"type": "correction", "source": "fixes_applied"})

    checks = data.get("checks", {})
    if isinstance(checks, dict):
        nested_fixes = checks.get("fixes_applied", 0)
        if isinstance(nested_fixes, (int, float)) and nested_fixes > 0:
            signals.append({"type": "correction", "source": "checks_fixes"})

    # 7. findings arrays
    for findings_key in ["new_findings", "findings"]:
        findings = data.get(findings_key, [])
        if isinstance(findings, list):
            for finding in findings:
                if isinstance(finding, dict):
                    if finding.get("escalation_needed") is True:
                        signals.append({"type": "escalation", "source": f"{findings_key}_esc"})
                    f_status = finding.get("status", "")
                    if f_status in ("error", "failed"):
                        signals.append({"type": "execution_error", "source": f"{findings_key}_status"})
                    severity = finding.get("severity", "")
                    if severity in ("critical", "high"):
                        signals.append({"type": "escalation", "source": f"{findings_key}_severity"})
                    action_taken = str(finding.get("action_taken", "")).lower()
                    if any(kw in action_taken for kw in ["fix", "correction", "patched"]):
                        signals.append({"type": "correction", "source": f"{findings_key}_action"})

    # 8. Finch-specific signals via structured paths
    if skill == "ocas-finch":
        finch_signals = _extract_finch_signals(data)
        signals.extend(finch_signals)

    # 9. Forge no-op detection
    if skill == "ocas-forge":
        result_val = str(data.get("result", "")).lower().strip()
        if result_val in FORGE_NO_OP_RESULTS:
            return []  # no-op, suppress all signals
        if "result" not in data and "status" not in data and "decision" not in data:
            return []

    # 10. Spot observation no-op handler
    if skill == "ocas-spot":
        jtype = str(data.get("type", "")).lower()
        if jtype == "observation":
            summary_text = str(data.get("summary", "")).lower()
            obs_skip_phrases = ["skipped", "permanently broken", "dead watch", "expired", "no new availability"]
            if any(p in summary_text for p in obs_skip_phrases):
                if "all" in summary_text or "0 active" in summary_text or "no new" in summary_text:
                    return []

    # 11. Summary keyword scanning (only for non-ok contexts)
    if summary and isinstance(summary, str):
        sl = summary.lower()
        if top_status not in ("ok", "success", "complete", "completed", ""):
            for kw in ["error", "failure", "failed", "unreachable", "timeout", "broken", "crash"]:
                if kw in sl:
                    signals.append({"type": "failure_keyword", "source": "summary_keyword", "keyword": kw})
                    break
            for kw in ["oauth", "token", "401", "unauthorized", "revoked"]:
                if kw in sl:
                    signals.append({"type": "auth_failure", "source": "summary_keyword", "keyword": kw})
                    break

    # 12. Semantic suppression for summary-derived signals
    if summary and isinstance(summary, str):
        if should_suppress_summary_signals(summary, signals):
            signals = [s for s in signals if s["type"] not in SUMMARY_DERIVED_TYPES]

    return signals


def get_failure_phase_from_journal(data, signals):
    if not signals:
        return "null"

    summary = ""
    if isinstance(data, dict):
        decision = data.get("decision", {})
        if isinstance(decision, dict):
            ds = decision.get("summary", "")
            if isinstance(ds, str):
                summary = ds
        if not summary:
            s = data.get("summary", "")
            if isinstance(s, str):
                summary = s

    if isinstance(summary, str):
        sl = summary.lower()
        if any(kw in sl for kw in ["should have", "before", "wrong approach", "didn't check", "missing prerequisite", "forgot"]):
            return "planning"
        if any(kw in sl for kw in ["too verbose", "wrong format", "just give me", "make it concise", "don't explain"]):
            return "response"

    return "execution"


def main():
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    run_id = f"r_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    print(f"=== Praxis Journal Ingest Run {run_id} ===")
    print(f"Now: {now_iso()}")
    print(f"Scan window: {yesterday} to {today}")

    # === STEP 1: Load and deduplicate journals_evaluated.jsonl ===
    eval_entries = read_jsonl(EVAL_FILE)

    seen_eval_ids = set()
    deduped_eval = []
    for entry in eval_entries:
        jid = entry.get("journal_id", "")
        if jid and jid not in seen_eval_ids:
            seen_eval_ids.add(jid)
            deduped_eval.append(entry)

    if len(deduped_eval) < len(eval_entries):
        removed = len(eval_entries) - len(deduped_eval)
        print(f"  Deduped journals_evaluated.jsonl: removed {removed} duplicates")

    eval_entries = deduped_eval

    # Compact if >5000 entries
    if len(eval_entries) > 5000:
        cutoff = (now - timedelta(days=30)).isoformat()
        compacted = [e for e in eval_entries
                     if e.get("evaluated_at", "9999") > cutoff or not e.get("evaluated_at")]
        removed = len(eval_entries) - len(compacted)
        if removed > 0:
            eval_entries = compacted
            print(f"  Compacted: removed {removed} entries older than 30 days")

    write_jsonl(EVAL_FILE, eval_entries)
    seen_eval_ids = {e.get("journal_id", "") for e in eval_entries}

    # === STEP 2: Scan filesystem for journal files ===
    all_files = []
    for root_dir, dirs, files in os.walk(JOURNALS_DIR):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        parts = root_dir.replace(JOURNALS_DIR, "").strip('/').split('/')
        if parts and parts[0] in SKIP_DIRS:
            continue
        for fname in sorted(files):
            if fname.endswith('.json'):
                full_path = os.path.join(root_dir, fname)
                rel_path = os.path.relpath(full_path, JOURNALS_DIR)
                path_parts = rel_path.split('/')
                if len(path_parts) >= 3:
                    date_dir = path_parts[1]
                    if date_dir in (today, yesterday):
                        skill = path_parts[0]
                        canonical = f"{skill}/{date_dir}/{fname}"
                        all_files.append((canonical, full_path))

    print(f"  Total journal files found (today+yesterday): {len(all_files)}")

    # === STEP 3: Compute unevaluated set ===
    unevaluated = [(c, p) for c, p in all_files if c not in seen_eval_ids and os.path.exists(p)]
    unevaluated.sort(key=lambda x: x[0])

    print(f"  Unevaluated journals: {len(unevaluated)}")

    # === STEP 4: Process each unevaluated journal ===
    new_events = []
    eval_updates = []
    new_events_count = 0
    no_signal_count = 0
    truly_new = []
    remaining_proposals = []

    for canonical, fpath in unevaluated:
        try:
            with open(fpath, 'r') as f:
                journal_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  SKIP (read error): {canonical}: {e}")
            eval_updates.append({
                "journal_id": canonical,
                "evaluated_at": now_iso(),
                "action_taken": "skip_read_error",
                "signals_found": [],
                "reason": str(e)
            })
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
            no_signal_count += 1
            continue

        failure_phase = get_failure_phase_from_journal(journal_data, signals)
        signal_types = list(set(s["type"] for s in signals))
        journal_has_real_signal = False

        for sig in signals:
            if not sig["type"] or sig["type"] in ("unknown", "?", ""):
                continue
            if sig["type"] == "observation":
                continue

            event = {
                "event_id": f"evt_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
                "timestamp": now_iso(),
                "source_journal": canonical,
                "signal_type": sig["type"],
                "domain": canonical.split("/")[0],
                "failure_phase": failure_phase,
                "context_summary": json.dumps(sig),
                "evidence": [f"Journal: {canonical}", f"signal_type: {sig['type']}"],
                "user_relevance": "agent_only",
                "recorded_at": now_iso()
            }

            if isinstance(journal_data, dict):
                summary_val = journal_data.get("summary", "")
                if isinstance(summary_val, str) and summary_val.strip():
                    event["summary_excerpt"] = summary_val[:500]

            new_events.append(event)
            journal_has_real_signal = True

        if journal_has_real_signal:
            new_events_count += 1
            eval_updates.append({
                "journal_id": canonical,
                "evaluated_at": now_iso(),
                "action_taken": "event_recorded",
                "signals_found": signal_types,
                "reason": f"Extracted {len(signal_types)} signal type(s): {', '.join(sorted(signal_types))}"
            })
        else:
            eval_updates.append({
                "journal_id": canonical,
                "evaluated_at": now_iso(),
                "action_taken": "no_signal",
                "signals_found": [],
                "reason": "No behavioral signals after filtering"
            })
            no_signal_count += 1

    if new_events:
        append_jsonl(EVENTS_FILE, new_events)
        print(f"  Recorded {len(new_events)} new event(s) from {new_events_count} journal(s)")

    if eval_updates:
        append_jsonl(EVAL_FILE, eval_updates)
        print(f"  Evaluated {len(eval_updates)} journal(s): {new_events_count} with events, {no_signal_count} no-signal")

    # === STEP 4b: Continue to lesson extraction even if no new journals ===
    if not unevaluated:
        print("  No new journals to process.")

    # === STEP 5: Post-write dedup of events.jsonl ===
    all_events = read_jsonl(EVENTS_FILE)
    deduped_events = []
    seen_event_keys = {}
    dup_count = 0
    for evt in all_events:
        key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
        if key not in seen_event_keys:
            seen_event_keys[key] = evt
            deduped_events.append(evt)
        else:
            dup_count += 1

    if dup_count > 0:
        print(f"  Post-write dedup: removed {dup_count} duplicate event(s)")
        write_jsonl(EVENTS_FILE, deduped_events)

    # === STEP 6: Lesson extraction (two-pass inline) ===
    all_events = read_jsonl(EVENTS_FILE)
    meaningful_events = [e for e in all_events
                         if e.get("signal_type") and e["signal_type"] not in ("unknown", "?", "", None)]

    groups = {}
    for evt in meaningful_events:
        key = (evt.get("signal_type", ""), evt.get("failure_phase", ""))
        if key not in groups:
            groups[key] = []
        groups[key].append(evt)

    existing_lessons = read_jsonl(LESSONS_FILE)
    existing_groups = set()
    for l in existing_lessons:
        key = (l.get("signal_type", ""), l.get("failure_phase", ""))
        if key[0] and key[1]:
            existing_groups.add(key)

    existing_shifts = read_jsonl(SHIFTS_FILE)
    covered_lesson_ids = set()
    for s in existing_shifts:
        if s.get("status") in ("active", "proposed"):
            for field in ['lesson_id', 'lesson_ref', 'source_lesson']:
                val = s.get(field)
                if isinstance(val, str):
                    covered_lesson_ids.add(val)

    new_lessons = []
    for (sig_type, phase), events_in_group in groups.items():
        if len(events_in_group) < 2:
            continue
        if (sig_type, phase) in existing_groups:
            continue
        if not sig_type or sig_type in ("unknown", "?", ""):
            continue
        if not phase:
            continue

        domains = list(set(e.get("domain", "unknown") for e in events_in_group))
        lesson_text = (
            f"[LESSON] What: {len(events_in_group)} events of type '{sig_type}' in {phase} phase. "
            f"Why: Repeated pattern across {len(events_in_group)} occurrences in {', '.join(domains)}. "
            f"When: During {phase} phase of operations."
        )
        lesson = {
            "lesson_id": f"les_{uuid.uuid4().hex[:20]}",
            "signal_type": sig_type,
            "failure_phase": phase,
            "lesson_text": lesson_text,
            "confidence": "high",
            "event_count": len(events_in_group),
            "events_referenced": [get_event_id(e) for e in events_in_group],
            "causal_grounding": {
                "what": f"{len(events_in_group)} events of type '{sig_type}' in {phase} phase",
                "why": f"Repeated pattern across {len(events_in_group)} occurrences in {', '.join(domains)}",
                "when": f"During {phase} phase"
            },
            "domains_affected": domains,
            "recorded_at": now_iso()
        }
        new_lessons.append(lesson)

    if new_lessons:
        append_jsonl(LESSONS_FILE, new_lessons)
        print(f"  Extracted {len(new_lessons)} new lesson(s)")
        for l in new_lessons:
            print(f"    - {l['signal_type']} / {l['failure_phase']}: {l['event_count']} events")

    # === STEP 7: Shift proposal and activation ===
    all_lessons = read_jsonl(LESSONS_FILE)
    proposed_shifts = []
    activated_shifts = []
    active_count = sum(1 for s in existing_shifts if s.get("status") == "active")
    cap = 12

    for lesson in all_lessons:
        lid = get_lesson_id(lesson)
        sig_type = lesson.get("signal_type", "")
        phase = lesson.get("failure_phase", "")

        if not sig_type or sig_type in ("unknown", "?", ""):
            continue
        if not phase:
            continue
        if lesson.get("confidence") != "high":
            continue
        if lid in covered_lesson_ids:
            continue

        # Check domain+phase overlap with active shifts
        domain = None
        if lesson.get("domains_affected"):
            domain = lesson["domains_affected"][0]

        overlap = False
        for s in existing_shifts:
            if s.get("status") != "active":
                continue
            s_domain = s.get("domain", "")
            s_phase = s.get("failure_phase", s.get("phase", "execution"))
            if s_domain == domain and s_phase == phase:
                overlap = True
                s["reinforcement_count"] = s.get("reinforcement_count", 0) + 1
                break

        if overlap:
            continue

        shift = {
            "shift_id": f"shf_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            "status": "proposed",
            "shift_text": f"When {sig_type} occurs in {phase} phase ({domain}), apply lesson: {lesson.get('lesson_text', '')[:200]}",
            "lesson_id": lid,
            "signal_type": sig_type,
            "failure_phase": phase,
            "domain": domain or "unknown",
            "confidence": "high",
            "reinforcement_count": 0,
            "proposed_at": now_iso(),
            "activated_at": None
        }

        if active_count < cap:
            shift["status"] = "active"
            shift["activated_at"] = now_iso()
            activated_shifts.append(shift)
            active_count += 1
            covered_lesson_ids.add(lid)
            print(f"  Activated shift: {shift['shift_id']} ({sig_type}/{phase})")
        else:
            proposed_shifts.append(shift)
            print(f"  Proposed shift (at cap): {shift['shift_id']} ({sig_type}/{phase})")

    if activated_shifts or proposed_shifts:
        updated_shifts = existing_shifts + activated_shifts + proposed_shifts
        write_jsonl(SHIFTS_FILE, updated_shifts)
        print(f"  Shifts: {len(activated_shifts)} activated, {len(proposed_shifts)} proposed (active: {active_count}/{cap})")

    # === STEP 8: Record decisions ===
    decisions = []
    if new_events:
        decisions.append({
            "decision_id": f"dec_{now.strftime('%Y%m%d_%H%M%S')}_001",
            "timestamp": now_iso(),
            "type": "event_recording",
            "summary": f"Recorded {len(new_events)} new event(s) from {new_events_count} journal(s)",
            "evidence": [e.get("source_journal", "") for e in new_events[:5]],
            "run_id": run_id
        })
    if new_lessons:
        decisions.append({
            "decision_id": f"dec_{now.strftime('%Y%m%d_%H%M%S')}_002",
            "timestamp": now_iso(),
            "type": "lesson_extraction",
            "summary": f"Extracted {len(new_lessons)} new lesson(s) from event patterns",
            "evidence": [l.get("lesson_id", "") for l in new_lessons],
            "run_id": run_id
        })
    if decisions:
        append_jsonl(DECISIONS_FILE, decisions)

    # === STEP 9: Write Praxis journal ===
    journal_dir = os.path.join(JOURNAL_DIR, today)
    os.makedirs(journal_dir, exist_ok=True)
    journal_path = os.path.join(journal_dir, f"{run_id}.json")

    write_result = {
        "run_id": run_id,
        "timestamp": now_iso(),
        "type": "journal_ingest",
        "status": "completed",
        "not_activity_reason": None,
        "entities_observed": [],
        "relationships_observed": [
            {"type": "event_to_lesson", "count": len(new_lessons)},
            {"type": "lesson_to_shift", "count": len(activated_shifts) + len(proposed_shifts)}
        ],
        "preferences_observed": [],
        "data": {
            "journals_evaluated": len(eval_updates),
            "new_events": len(new_events),
            "new_lessons": len(new_lessons),
            "activated_shifts": len(activated_shifts),
            "proposed_shifts": len(proposed_shifts),
            "active_shift_count": active_count,
            "total_events": len(read_jsonl(EVENTS_FILE)),
            "total_lessons": len(read_jsonl(LESSONS_FILE)),
            "total_shifts": len(read_jsonl(SHIFTS_FILE))
        }
    }

    with open(journal_path, 'w') as f:
        json.dump(write_result, f, indent=2)

    print(f"\n=== Summary ===")
    print(f"  Run ID: {run_id}")
    print(f"  Journals evaluated: {len(eval_updates)}")
    print(f"  New events: {len(new_events)}")
    print(f"  New lessons: {len(new_lessons)}")
    print(f"  Activated shifts: {len(activated_shifts)}")
    print(f"  Proposed shifts: {len(proposed_shifts)}")
    print(f"  Active shifts: {active_count}/{cap}")
    print(f"  Total events in store: {write_result['data']['total_events']}")
    print(f"  Journal written: {journal_path}")


if __name__ == "__main__":
    main()
