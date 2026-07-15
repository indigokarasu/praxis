#!/usr/bin/env python3
"""Shift cleanup — expire malformed shifts, merge overlaps, enforce cap.
Run after ingest to fix data quality issues.
"""
import json
import os
from datetime import datetime, timezone, timedelta

from praxis_common import (
    DATA_DIR, SHIFTS_FILE, LESSONS_FILE, EVENTS_FILE,
    load_jsonl, append_jsonl, now_iso, generate_id,
)

NOISE_SIGNAL_TYPES = {
    "", "unknown", "?", "no_op", "forge_activity", "routine",
    "no_signal", "cron_error", "cron_errors", "observation", "success",
    "task_resolved", "low_signal_precision", "task_improvement", "new_tasks_found",
    "failure", "directive", "security_alert", "no_active_watches", "anomaly_detected",
    "coverage_gap", "calendar_conflict",
}

FORGE_NO_OP_PREFIXES = {"no_op", "clean", "no-op", "no_unprocessed_files", "no unprocessed"}

def is_forge_no_op(result_val):
    if not result_val:
        return False
    r = str(result_val).lower().strip()
    return any(r.startswith(prefix) for prefix in FORGE_NO_OP_PREFIXES)

def main():
    print(f"=== Shift Cleanup — {now_iso()} ===\n")

    # Load current shifts
    shifts = load_jsonl(SHIFTS_FILE)
    active = [s for s in shifts if s.get('status') == 'active']
    print(f"Active shifts before cleanup: {len(active)}")

    # Identify shifts to expire
    to_expire = []
    for s in active:
        domain = s.get('domain')
        signal_type = s.get('signal_type', '')
        phase = s.get('failure_phase', '')

        reasons = []
        if not domain or domain in ('None', 'null', 'unknown', ''):
            reasons.append('missing_domain')
        if signal_type in NOISE_SIGNAL_TYPES:
            reasons.append(f'noise_signal_type:{signal_type}')
        if not signal_type or signal_type in ('unknown', '?', '', None):
            reasons.append('empty_signal_type')
        if phase in ('null', 'None', '', None):
            reasons.append('invalid_phase')

        if reasons:
            to_expire.append((s, '; '.join(reasons)))

    # Also check for domain+phase overlap (merge before cap)
    overlap_map = {}
    for s in active:
        if any(s is se[0] for se in to_expire):
            continue
        key = (s.get('domain', 'unknown'), s.get('failure_phase', 'unknown'))
        overlap_map.setdefault(key, []).append(s)

    for key, group in overlap_map.items():
        if len(group) > 1:
            # Keep the one with highest reinforcement, expire others
            group.sort(key=lambda x: x.get('reinforcement_count', 0), reverse=True)
            for s in group[1:]:
                to_expire.append((s, f'overlap_merge:{key[0]}/{key[1]}'))

    # Expire identified shifts
    expired_count = 0
    for s, reason in to_expire:
        s['status'] = 'expired'
        s['expired_at'] = now_iso()
        s['expire_reason'] = reason
        expired_count += 1
        print(f"  EXPIRED: {s.get('shift_id')} — {reason}")

    # Rewrite shifts file
    with open(SHIFTS_FILE, 'w') as f:
        for s in shifts:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')

    # Also clean up malformed lessons
    lessons = load_jsonl(LESSONS_FILE)
    print(f"\nTotal lessons: {len(lessons)}")

    valid_lessons = []
    removed_lessons = 0
    for l in lessons:
        signal_type = l.get('pattern_key') or l.get('signal_type') or ''
        domain = l.get('domain')
        phase = l.get('failure_phase')

        reasons = []
        if not domain or domain in ('None', 'null', 'unknown', ''):
            reasons.append('missing_domain')
        if not signal_type or signal_type in ('None', 'null', 'unknown', '?', ''):
            reasons.append('empty_signal_type')
        if signal_type in NOISE_SIGNAL_TYPES:
            reasons.append(f'noise_signal_type:{signal_type}')
        if phase in ('null', 'None', '', None):
            reasons.append('invalid_phase')

        if reasons:
            removed_lessons += 1
            print(f"  REMOVED LESSON: {l.get('lesson_id')} — {'; '.join(reasons)}")
        else:
            valid_lessons.append(l)

    if removed_lessons > 0:
        with open(LESSONS_FILE, 'w') as f:
            for l in valid_lessons:
                f.write(json.dumps(l, ensure_ascii=False) + '\n')
        print(f"\nRemoved {removed_lessons} malformed lessons. Valid lessons: {len(valid_lessons)}")

    # Evidence
    append_jsonl(os.path.join(DATA_DIR, 'evidence.jsonl'), [{
        'evidence_id': generate_id('evid'),
        'recorded_at': now_iso(),
        'run_type': 'shift_cleanup',
        'active_shifts_before': len(active),
        'shifts_expired': expired_count,
        'lessons_removed': removed_lessons,
        'active_shifts_after': len(active) - expired_count,
    }])

    print(f"\nDone. Active shifts now: {len(active) - expired_count}/12")
    print(f"Valid lessons: {len(valid_lessons)}")

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(
        description="Shift cleanup — expire malformed shifts, merge overlaps, enforce 12-shift cap.",
        usage="python3 shift_cleanup_20260617.py")
    p.parse_args()
    main()