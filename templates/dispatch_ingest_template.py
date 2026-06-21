#!/usr/bin/env python3
"""
Dispatch-triggered Praxis journal ingest template.

Copy this file and adapt for each dispatch run. Usage:
  1. Copy: cp templates/dispatch_ingest_template.py scripts/dispatch_ingest_YYYYMMDD.py
  2. Modify the constants if needed (DATA_DIR, JOURNALS_DIRS)
  3. Run: python3 scripts/dispatch_ingest_YYYYMMDD.py

This template implements all mandatory gotcha filters:
  - Mixed-format eval file handling (plain strings + JSON dicts)
  - Mtime-based journal discovery (workaround for broken dedup)
  - Mentor-light noise filters (failure_keyword, gap_detected, low_coverage)
  - Forge no-op filter (startswith matching)
  - Custodian action journal filter (error mentions in summary)
  - (source_journal, signal_type) dedup
  - Null-phase event filtering
  - NOISE_SIGNAL_TYPES gate
"""

import json
import os
from datetime import timezone, datetime

# --- CONFIGURATION ---
DATA_DIR = "/root/.hermes/profiles/indigo/commons/data/ocas-praxis"
JOURNALS_DIRS = [
    "/root/.hermes/commons/journals/",
    "/root/.hermes/profiles/indigo/commons/journals/",
]
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
STATE_FILE = os.path.join(DATA_DIR, "ingest_state.json")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")

# --- NOISE CONSTANTS ---
NOISE_SIGNAL_TYPES = {
    "", "unknown", "?", "no_op", "forge_activity", "routine",
    "no_signal", "cron_error", "cron_errors", "observation", "success", "mentor_light"
}
FORGE_NO_OP_PREFIXES = {"no_op", "clean", "no-op", "no_unprocessed_files", "no unprocessed"}

# --- HELPER FUNCTIONS ---
def get_signal_type(evt):
    return evt.get("signal_type") or evt.get("outcome_type") or "unknown"

def is_forge_no_op(data):
    """Check if a forge journal is a routine no-op."""
    result = data.get("result", "")
    action = data.get("action", {})
    if isinstance(action, dict):
        action_result = action.get("result", "")
        if isinstance(action_result, str):
            ar = action_result.lower().strip()
            if any(ar.startswith(p) for p in FORGE_NO_OP_PREFIXES):
                return True
    if isinstance(result, str):
        r = result.lower().strip()
        if any(r.startswith(p) for p in FORGE_NO_OP_PREFIXES):
            return True
    actions_taken = data.get("actions_taken", "")
    if isinstance(actions_taken, str):
        at = actions_taken.lower().strip()
        if any(at.startswith(p) for p in FORGE_NO_OP_PREFIXES):
            return True
    if isinstance(actions_taken, list) and len(actions_taken) == 0:
        findings = data.get("findings", {})
        if isinstance(findings, dict) and findings.get("unprocessed_proposals", 0) == 0:
            return True
    return False

def has_custodian_action_error_mention(data, journal_id):
    """Check if a custodian action journal mentions errors in summary (routine operational report)."""
    if "ocas-custodian" not in journal_id:
        return False
    jtype = data.get("type", "")
    if jtype != "action":
        return False
    summary = data.get("summary", "") or ""
    if not isinstance(summary, str):
        return False
    summary_lower = summary.lower()
    error_keywords = ["error job", "error", "failed", "failure"]
    has_error_mention = any(kw in summary_lower for kw in error_keywords)
    if not has_error_mention:
        return False
    findings = data.get("findings", {})
    if isinstance(findings, dict):
        severity = findings.get("severity", "")
        if severity == "critical":
            return False
    return True

# --- MAIN INGEST ---
def main():
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    state = {"last_ingest_run": "2020-01-01T00:00:00+00:00", "last_lesson_extraction_event_id": None}
    if os.path.exists(STATE_FILE):
        state = json.load(open(STATE_FILE))
    last_ingest_run = state.get("last_ingest_run", "2020-01-01T00:00:00+00:00")

    seen_ids = set()
    if os.path.exists(EVAL_FILE):
        with open(EVAL_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    entry = line
                if isinstance(entry, dict):
                    jid = entry.get("journal_id", "")
                elif isinstance(entry, str):
                    jid = entry
                else:
                    continue
                seen_ids.add(jid)
                seen_ids.add(jid + ".json")

    new_journals = []
    for jdir in JOURNALS_DIRS:
        if not os.path.isdir(jdir):
            continue
        for skill_dir in sorted(os.listdir(jdir)):
            skill_path = os.path.join(jdir, skill_dir)
            if not os.path.isdir(skill_path) or skill_dir == "ocas-praxis":
                continue
            for date_dir in sorted(os.listdir(skill_path)):
                date_path = os.path.join(skill_path, date_dir)
                if not os.path.isdir(date_path):
                    continue
                for jf in sorted(os.listdir(date_path)):
                    if not jf.endswith(".json"):
                        continue
                    full_path = os.path.join(date_path, jf)
                    journal_id = f"{skill_dir}/{date_dir}/{jf}"
                    if journal_id in seen_ids or journal_id + ".json" in seen_ids:
                        continue
                    try:
                        mtime = os.path.getmtime(full_path)
                        last_ingest_dt = datetime.fromisoformat(last_ingest_run.replace("Z", "+00:00"))
                        if datetime.fromtimestamp(mtime, tz=timezone.utc) > last_ingest_dt:
                            new_journals.append((full_path, journal_id, skill_dir))
                    except (OSError, ValueError):
                        pass

    print(f"Found {len(new_journals)} new journals since {last_ingest_run}")

    events = []
    eval_entries = []
    malformed = 0
    no_signal = 0

    for full_path, journal_id, skill_dir in new_journals:
        try:
            with open(full_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            malformed += 1
            eval_entries.append(json.dumps({"journal_id": journal_id, "action_taken": "malformed"}))
            continue

        if not isinstance(data, dict):
            eval_entries.append(json.dumps({"journal_id": journal_id, "action_taken": "skipped_non_dict"}))
            continue

        outcome = data.get("outcome") or data.get("result") or data.get("status")
        if isinstance(outcome, dict):
            outcome = outcome.get("result", "")

        is_mentor_light = "mentor-light" in journal_id or skill_dir == "ocas-mentor"

        if is_mentor_light:
            gap_detected = data.get("gap_detected", False)
            metrics = data.get("metrics", {})
            errors_count = metrics.get("errors", 0) if isinstance(metrics, dict) else 0
            if outcome in ("success", "", None) and not gap_detected and errors_count == 0:
                no_signal += 1
                eval_entries.append(json.dumps({"journal_id": journal_id, "action_taken": "no_signal_mentor_light"}))
                continue

        if skill_dir == "ocas-forge" and is_forge_no_op(data):
            no_signal += 1
            eval_entries.append(json.dumps({"journal_id": journal_id, "action_taken": "no_signal_forge_no_op"}))
            continue

        if skill_dir == "ocas-custodian" and data.get("type") == "observation":
            no_signal += 1
            eval_entries.append(json.dumps({"journal_id": journal_id, "action_taken": "no_signal_custodian_observation"}))
            continue

        if has_custodian_action_error_mention(data, journal_id):
            no_signal += 1
            eval_entries.append(json.dumps({"journal_id": journal_id, "action_taken": "no_signal_custodian_action_error_mention"}))
            continue

        signal_type = data.get("signal_type", "")
        if not signal_type:
            summary = data.get("summary", "") or ""
            if isinstance(summary, str) and "error" in summary.lower() and outcome in ("success", "", None):
                signal_type = "failure_keyword"
            else:
                signal_type = "no_signal"

        failure_phase = data.get("failure_phase", "execution") or "execution"
        if not failure_phase or str(failure_phase).lower() in ("none", "null", "", "missing"):
            failure_phase = "execution"

        if signal_type in NOISE_SIGNAL_TYPES:
            no_signal += 1
            eval_entries.append(json.dumps({"journal_id": journal_id, "action_taken": "no_signal_noise"}))
            continue

        if is_mentor_light and signal_type == "failure_keyword" and outcome in ("success", "", None):
            no_signal += 1
            eval_entries.append(json.dumps({"journal_id": journal_id, "action_taken": "no_signal_mentor_failure_keyword"}))
            continue

        event = {
            "event_id": f"evt-{now.strftime('%Y%m%d%H%M%S%f')}",
            "timestamp": now_iso,
            "source_journal": journal_id,
            "skill": skill_dir,
            "signal_type": signal_type,
            "failure_phase": failure_phase.lower(),
            "outcome": str(outcome).lower() if outcome else "unknown",
            "evidence": data.get("summary", "")[:200] if isinstance(data.get("summary"), str) else ""
        }
        events.append(event)
        eval_entries.append(json.dumps({"journal_id": journal_id, "action_taken": "event_recorded"}))

    events_added = 0
    if events:
        with open(EVENTS_FILE, "a") as f:
            for evt in events:
                f.write(json.dumps(evt) + "\n")
                events_added += 1

    if eval_entries:
        with open(EVAL_FILE, "a") as f:
            for entry in eval_entries:
                f.write(entry + "\n")

    state["last_ingest_run"] = now_iso
    state["last_run"] = now_iso
    state["journals_processed"] = state.get("journals_processed", 0) + len(new_journals)
    state["events_recorded"] = state.get("events_recorded", 0) + events_added
    state["last_ingest_events_added"] = events_added
    state["last_ingest_journals_evaluated"] = len(eval_entries)
    state["last_evaluated_count"] = state.get("last_evaluated_count", 0) + len(eval_entries)
    state["last_praxis_dispatch"] = now_iso
    state["note"] = f"Dispatch ingest: {len(new_journals)} journals, {events_added} events"
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

    evidence = {
        "timestamp": now_iso,
        "run_type": "dispatch_ingest",
        "journals_scanned": len(new_journals),
        "events_added": events_added,
        "malformed": malformed,
        "no_signal": no_signal,
        "eval_entries_added": len(eval_entries)
    }
    with open(DECISIONS_FILE, "a") as f:
        f.write(json.dumps(evidence) + "\n")

    print(f"Events recorded: {events_added}")
    print(f"No-signal: {no_signal}")
    print(f"Malformed: {malformed}")
    print(f"Eval entries added: {len(eval_entries)}")

if __name__ == "__main__":
    main()
