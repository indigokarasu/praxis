#!/usr/bin/env python3
"""Daily debrief generator — production template from debrief_templates.md."""
import json
import os
from datetime import datetime, timezone, timedelta

from praxis_common import (
    DATA_DIR, SHIFTS_FILE, LESSONS_FILE, EVENTS_FILE, EVIDENCE_FILE, DEBRIEF_FILE,
    load_jsonl, append_jsonl, now_iso, generate_id,
)

def main():
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    print(f"=== Praxis Debrief — {today} ===\n")

    # Load data
    shifts = load_jsonl(SHIFTS_FILE)
    lessons = load_jsonl(LESSONS_FILE)
    events = load_jsonl(EVENTS_FILE)
    evidence = load_jsonl(EVIDENCE_FILE)

    # Today's events
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_events = []
    for e in events:
        recorded = e.get('recorded_at', '')
        if recorded and recorded >= today_start.isoformat().replace('+00:00', 'Z'):
            today_events.append(e)

    # Today's lessons
    today_lessons = []
    for l in lessons:
        extracted = l.get('extracted_at', '') or l.get('created_at', '') or l.get('timestamp', '')
        if extracted and extracted >= today_start.isoformat().replace('+00:00', 'Z'):
            today_lessons.append(l)

    # Today's evidence (ingest runs)
    today_evidence = [e for e in evidence if e.get('recorded_at', '') >= today_start.isoformat().replace('+00:00', 'Z')]

    # Active shifts
    active_shifts = [s for s in shifts if s.get('status') == 'active']

    # Shift decay check
    stale_shifts = []
    for s in active_shifts:
        last_reinf = s.get('last_reinforced_at') or s.get('created_at', '')
        if last_reinf:
            try:
                last_dt = datetime.fromisoformat(last_reinf.replace('Z', '+00:00'))
                days = (datetime.now(timezone.utc) - last_dt).days
                if days >= 10:
                    stale_shifts.append((s, days))
            except:
                pass

    # Shifts activated/reinforced today (only active ones)
    today_active_shifts = []
    for s in active_shifts:
        created = s.get('created_at', '')
        last_reinf = s.get('last_reinforced_at', '')
        if (created and created >= today_start.isoformat().replace('+00:00', 'Z')) or \
           (last_reinf and last_reinf >= today_start.isoformat().replace('+00:00', 'Z')):
            today_active_shifts.append(s)
        for e in today_events:
            key = (e.get('domain', 'unknown'), e.get('failure_phase', 'unknown'))
            by_domain_phase.setdefault(key, []).append(e)
        for (domain, phase), evts in sorted(by_domain_phase.items()):
            lines.append(f"  - {domain}/{phase}: {len(evts)} events ({', '.join(set(e.get('signal_type', '?') for e in evts))})")
    else:
        lines.append("  - No new events recorded today")
    lines.append("")

    # Lessons extracted
    lines.append(f"## Lessons extracted: {len(today_lessons)}")
    for l in today_lessons:
        domain = l.get('domain', 'unknown')
        phase = l.get('failure_phase', 'unknown')
        signal = l.get('signal_type', '?')
        conf = l.get('confidence', '?')
        grounding = "Full" if l.get('why') and l.get('when') and l.get('what') else "Partial" if l.get('why') else "Minimal"
        lines.append(f"  - [LESSON] {domain}/{phase} - {signal} [confidence: {conf}] [grounding: {grounding}]")
        lines.append(f"    What: {l.get('what', 'N/A')[:120]}")
        lines.append(f"    Why: {l.get('why', 'N/A')[:120]}")
        lines.append(f"    When: {l.get('when', 'N/A')[:120]}")
    if not today_lessons:
        lines.append("  - No new lessons extracted today")
    lines.append("")

    # Behavior shifts activated
    # Find shifts created or reinforced today
    today_shifts = []
    for s in shifts:
        created = s.get('created_at', '')
        last_reinf = s.get('last_reinforced_at', '')
        if (created and created >= today_start.isoformat().replace('+00:00', 'Z')) or \
           (last_reinf and last_reinf >= today_start.isoformat().replace('+00:00', 'Z')):
            today_shifts.append(s)

    lines.append(f"## Behavior shifts activated/reinforced: {len(today_shifts)}")
    for s in today_shifts:
        domain = s.get('domain', 'unknown')
        phase = s.get('failure_phase', 'unknown')
        signal = s.get('signal_type', '?')
        reinf = s.get('reinforcement_count', 1)
        lines.append(f"  - [SHIFT] {domain}/{phase} - {signal} [reinforcement: {reinf}]")
        lines.append(f"    Targets: {s.get('shift_text', '')[:120]}")
    if not today_shifts:
        lines.append("  - No shifts activated or reinforced today")
    lines.append("")

    # Shift decay
    lines.append(f"## Shift decay status")
    expired_today = [s for s in shifts if s.get('status') == 'expired' and s.get('expired_at', '') >= today_start.isoformat().replace('+00:00', 'Z')]
    if expired_today:
        lines.append(f"  - Expired today: {len(expired_today)}")
        for s in expired_today:
            lines.append(f"    - [EXPIRED] {s.get('domain', '?')}/{s.get('failure_phase', '?')} - {s.get('signal_type', '?')} Reason: {s.get('expire_reason', 'unknown')}")
    else:
        lines.append("  - No shifts expired today")

    if stale_shifts:
        lines.append(f"  - Approaching decay (10+ days): {len(stale_shifts)}")
        for s, days in stale_shifts:
            lines.append(f"    - [STALE] {s.get('domain', '?')}/{s.get('failure_phase', '?')} - {s.get('signal_type', '?')} — no reinforcement for {days} days")
    else:
        lines.append("  - No shifts approaching decay")
    lines.append("")

    # Active shift summary
    consolidated = sum(1 for s in active_shifts if s.get('reinforcement_count', 0) >= 3)
    provisional = sum(1 for s in active_shifts if 1 <= s.get('reinforcement_count', 0) < 3)
    stale = len(stale_shifts)
    lines.append("## Active shift summary")
    lines.append(f"  {len(active_shifts)}/12 active shifts. {consolidated} consolidated (3+ reinforcements). {provisional} provisional (1-2). {stale} stale (approaching expiry).")
    lines.append("")

    # Open questions
    lines.append("## Open questions")
    if today_events:
        lines.append("  - What causal mechanisms drive the cross-skill failure_keyword pattern in execution phase?")
    if any(l.get('confidence') == 'low' for l in today_lessons):
        lines.append("  - Several low-confidence lessons need boundary conditions to upgrade causal grounding.")
    if not today_events and not today_lessons:
        lines.append("  - No new behavioral signals today — system operating in routine mode.")
    lines.append("")

    debrief_text = "\n".join(lines)

    # Save debrief
    debrief_record = {
        'debrief_id': generate_id('deb'),
        'generated_at': now_iso(),
        'date': today,
        'content': debrief_text,
        'events_count': len(today_events),
        'lessons_count': len(today_lessons),
        'shifts_activated': len(today_shifts),
        'active_shifts_total': len(active_shifts),
    }
    append_jsonl(DEBRIEF_FILE, [debrief_record])

    # Evidence
    append_jsonl(EVIDENCE_FILE, [{
        'evidence_id': generate_id('evid'),
        'recorded_at': now_iso(),
        'run_type': 'debrief',
        'debrief_id': debrief_record['debrief_id'],
        'events_included': len(today_events),
        'lessons_included': len(today_lessons),
        'shifts_included': len(today_shifts),
    }])

    print(debrief_text)

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(
        description="Daily Praxis debrief generator — prints and writes a plain-language debrief.",
        usage="python3 debrief_20260617.py [--since-hours N] [--no-write]")
    p.add_argument("--since-hours", type=int, default=24,
                   help="Lookback window for the debrief (default 24).")
    p.add_argument("--no-write", action="store_true",
                   help="Print the debrief but do not append to debriefs.jsonl/evidence.jsonl.")
    args = p.parse_args()
    main()