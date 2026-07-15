#!/usr/bin/env python3
"""Shift activation from valid lessons — merge-before-cap, noise filter, quality validation."""
import json
import os
from datetime import datetime, timezone

from praxis_common import (
    DATA_DIR, SHIFTS_FILE, LESSONS_FILE, EVENTS_FILE,
    load_jsonl, append_jsonl, now_iso, generate_id,
)

NOISE_SIGNAL_TYPES = {
    "", "unknown", "?", "no_op", "forge_activity", "routine",
    "no_signal", "cron_error", "cron_errors", "observation", "success",
    "task_resolved", "low_signal_precision", "task_improvement", "new_tasks_found",
    "failure", "directive", "security_alert", "no_active_watches", "anomaly_detected",
    "coverage_gap", "calendar_conflict", "mentor_light",
}

def main():
    print(f"=== Shift Activation — {now_iso()} ===\n")

    # Load valid lessons (already cleaned up)
    lessons = load_jsonl(LESSONS_FILE)
    print(f"Available lessons: {len(lessons)}")

    # Filter for high-confidence, valid lessons
    candidates = []
    for l in lessons:
        domain = l.get('domain')
        phase = l.get('failure_phase')
        signal_type = l.get('signal_type') or l.get('pattern_key')
        confidence = l.get('confidence', 'low')

        reasons = []
        if not domain or domain in ('None', 'null', 'unknown', ''):
            reasons.append('missing_domain')
        if not phase or phase in ('None', 'null', 'unknown', '', None):
            reasons.append('missing_phase')
        if not signal_type or signal_type in ('None', 'null', 'unknown', '?', ''):
            reasons.append('missing_signal_type')
        if signal_type in NOISE_SIGNAL_TYPES:
            reasons.append(f'noise_signal_type:{signal_type}')
        if confidence != 'high':
            reasons.append(f'low_confidence:{confidence}')

        if not reasons:
            candidates.append(l)
        else:
            print(f"  SKIP: {l.get('lesson_id')} — {'; '.join(reasons)}")

    print(f"\nHigh-confidence valid candidates: {len(candidates)}")

    # Load existing active shifts
    shifts = load_jsonl(SHIFTS_FILE)
    active = [s for s in shifts if s.get('status') == 'active']
    print(f"Current active shifts: {len(active)}")

    # Merge-before-cap: check domain+phase overlap
    activated = 0
    for lesson in candidates:
        domain = lesson['domain']
        phase = lesson['failure_phase'].lower() if lesson['failure_phase'] else 'execution'
        signal_type = lesson.get('signal_type') or lesson.get('pattern_key')

        # Check overlap with existing active
        overlap = None
        for s in active:
            s_domain = s.get('domain', '').lower()
            s_phase = s.get('failure_phase', '').lower()
            if s_domain == domain.lower() and s_phase == phase:
                overlap = s
                break

        if overlap:
            # Reinforce existing
            overlap['reinforcement_count'] = overlap.get('reinforcement_count', 0) + 1
            overlap['last_reinforced_at'] = now_iso()
            overlap['last_reinforced_lesson'] = lesson.get('lesson_id')
            print(f"  REINFORCED: {overlap['shift_id']} ({domain}/{phase}) — now {overlap['reinforcement_count']} reinforcements")
            activated += 1
            continue

        # Check cap
        if len(active) >= 12:
            print(f"  CAP REACHED: skipping {domain}/{phase} - {signal_type}")
            continue

        # Create new shift
        shift = {
            'shift_id': generate_id('shf'),
            'created_at': now_iso(),
            'status': 'active',
            'domain': domain,
            'failure_phase': phase,
            'signal_type': signal_type,
            'shift_text': f"In {domain} during {phase}: {signal_type} recurs (n={lesson.get('event_count', 0)}). {lesson.get('why', 'Root cause pending.')}",
            'source_lesson_id': lesson.get('lesson_id'),
            'source_event_ids': lesson.get('source_event_ids', []),
            'reinforcement_count': 1,
            'last_reinforced_at': now_iso(),
        }
        active.append(shift)
        shifts.append(shift)
        activated += 1
        print(f"  ACTIVATED: {shift['shift_id']} — {domain}/{phase} - {signal_type}")

    # Rewrite shifts file
    with open(SHIFTS_FILE, 'w') as f:
        for s in shifts:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')

    # Evidence
    append_jsonl(os.path.join(DATA_DIR, 'evidence.jsonl'), [{
        'evidence_id': generate_id('evid'),
        'recorded_at': now_iso(),
        'run_type': 'shift_activation',
        'candidates_considered': len(candidates),
        'shifts_activated': activated,
        'active_shifts_total': len(active),
    }])

    print(f"\nDone. Activated: {activated}, Total active: {len(active)}/12")
    for s in active:
        if s.get('status') == 'active':
            print(f"  {s['shift_id']}: {s['domain']}/{s['failure_phase']} - {s['signal_type']} (reinf: {s.get('reinforcement_count', 0)})")

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(
        description="Shift activation from valid lessons — merge-before-cap, noise filter, quality validation.",
        usage="python3 shift_activate_20260617.py")
    p.parse_args()
    main()