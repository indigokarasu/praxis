#!/usr/bin/env python3
"""
Praxis Debrief Generator — manual run template.

Usage:
  python3 scripts/praxis_debrief.py

This script generates a plain-language debrief of recent Praxis behavior:
1. Loads active shifts, checks reinforcement and decay
2. Scans for overlapping shifts (consolidation candidates)
3. Counts recent events by signal_type
4. Checks cap headroom
5. Writes structured debrief to debriefs.jsonl

NEVER use write_file on JSONL — this script uses open(..., 'a').
"""

import json
import os
import glob
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

# Profile-aware path
PROFILE = os.environ.get("HERMES_PROFILE", "indigo")
AGENT_ROOT = f"/root/.hermes/profiles/{PROFILE}"
DATA_DIR = os.path.join(AGENT_ROOT, "commons/data/ocas-praxis")
JOURNALS_DIR = os.path.join(AGENT_ROOT, "commons/journals")

EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
DEBRIEFS_FILE = os.path.join(DATA_DIR, "debriefs.jsonl")
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
INGEST_STATE_FILE = os.path.join(DATA_DIR, "ingest_state.json")

CONFIG = {
    "max_active_shifts": 12,
    "decay_ttl_days": 14,
    "approaching_decay_days": 10,
    "approaching_cap_threshold": 10,
}


def load_jsonl(path):
    records = []
    if not os.path.exists(path):
        return records
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def get_signal_type(evt):
    return evt.get("signal_type") or evt.get("outcome_type") or "unknown"


def get_shift_id(s):
    return s.get("shift_id") or s.get("id", "?")


def get_failure_phase(s):
    return s.get("failure_phase") or s.get("phase", "execution")


def main():
    now = datetime.now(timezone.utc)

    # Load data
    all_shifts = load_jsonl(SHIFTS_FILE)
    all_events = load_jsonl(EVENTS_FILE)
    all_lessons = load_jsonl(LESSONS_FILE)

    # Active shifts
    active_shifts = [s for s in all_shifts if s.get("status") == "active"]
    active_count = len(active_shifts)
    cap = CONFIG["max_active_shifts"]

    # Decay analysis
    approaching_decay = []
    for s in active_shifts:
        last_reinforced = s.get("last_reinforced_at") or s.get("activated_at") or s.get("created_at")
        if last_reinforced:
            try:
                lr = datetime.fromisoformat(last_reinforced.replace("Z", "+00:00"))
                days_since = (now - lr).days
            except:
                days_since = 0
        else:
            days_since = 0
        reinforces = s.get("reinforcement_count", 0)
        if days_since >= CONFIG["approaching_decay_days"] and reinforces == 0:
            approaching_decay.append({
                "id": get_shift_id(s),
                "domain": s.get("domain", "?"),
                "phase": get_failure_phase(s),
                "days_since": days_since,
                "reinforces": reinforces,
            })

    # Overlap scan
    overlaps = []
    for i, s1 in enumerate(active_shifts):
        for j, s2 in enumerate(active_shifts):
            if j <= i:
                continue
            if get_failure_phase(s1).lower() == get_failure_phase(s2).lower():
                words1 = set(s1.get("shift_text", "").lower().split())
                words2 = set(s2.get("shift_text", "").lower().split())
                shared = words1 & words2
                if len(shared) > 3:
                    overlaps.append({
                        "shift_a": get_shift_id(s1)[:30],
                        "shift_b": get_shift_id(s2)[:30],
                        "shared_words": list(shared)[:8],
                    })

    # Recent events (last 200)
    recent_events = all_events[-200:]
    sig_counts = Counter()
    for e in recent_events:
        sig_counts[f"{e.get('skill', '?')}/{get_signal_type(e)}"] += 1

    # Cap headroom
    at_cap = active_count >= cap
    approaching_cap = active_count >= CONFIG["approaching_cap_threshold"]

    # Weakest shift for potential expiry
    weakest = None
    if approaching_cap:
        unreinforced = [s for s in active_shifts if s.get("reinforcement_count", 0) == 0]
        if unreinforced:
            weakest = get_shift_id(unreinforced[0])

    # Build debrief
    debrief = {
        "debrief_id": f"debrief-{now.strftime('%Y%m%dT%H%M%S')}",
        "generated_at": now.isoformat(),
        "period": f"{(now - timedelta(days=1)).strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}",
        "active_shift_count": active_count,
        "cap_usage": f"{active_count}/{cap}" + (" (at cap)" if at_cap else ""),
        "new_shifts": 0,
        "expired_shifts": 0,
        "new_lessons": 0,
        "summary": "",
        "shifts_approaching_decay": approaching_decay,
        "overlapping_shifts": overlaps,
        "recent_signal_counts": dict(sig_counts.most_common(10)),
        "findings": [],
        "recommendations": [],
        "events_ingested": 0,
        "lessons_extracted": 0,
        "shifts_proposed": 0,
        "shifts_activated": 0,
        "shifts_expired": 0,
    }

    # Generate summary
    summary_parts = []
    if at_cap:
        summary_parts.append(f"Cap at {active_count}/{cap}. All new shift proposals blocked.")
    if approaching_decay:
        summary_parts.append(f"{len(approaching_decay)} shifts approaching decay (>{CONFIG['approaching_decay_days']}d unreinforced).")
    if overlaps:
        summary_parts.append(f"{len(overlaps)} potential shift overlaps detected.")
    if not summary_parts:
        summary_parts.append(f"System healthy. {active_count}/{cap} shifts active.")
    debrief["summary"] = " ".join(summary_parts)

    # Write debrief — APPEND, never overwrite
    with open(DEBRIEFS_FILE, "a") as f:
        f.write(json.dumps(debrief) + "\n")

    # Print summary
    print(f"=== Praxis Debrief ({now.strftime('%Y-%m-%d %H:%M')}) ===")
    print(f"Active shifts: {active_count}/{cap}")
    print(f"Approaching decay: {len(approaching_decay)}")
    print(f"Overlaps: {len(overlaps)}")
    print(f"Recent signals: {len(recent_events)} events")
    print(f"Debrief written to {DEBRIEFS_FILE}")


if __name__ == "__main__":
    main()
