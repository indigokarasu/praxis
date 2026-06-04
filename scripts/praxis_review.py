#!/usr/bin/env python3
"""
praxis_review.py — Praxis v3.0 automated review pass.

Usage:
    python3 praxis_review.py [--since-hours 24]

Scans all skill journals for new entries since the last evaluation,
extracts behavioral signals, records events/lessons, generates a debrief.

Data directory: /root/.hermes/commons/data/ocas-praxis/
Journals directory: /root/.hermes/commons/journals/
"""
import json, os, glob, argparse
from datetime import datetime, timezone, timedelta

DATA_DIR = '/root/.hermes/commons/data/ocas-praxis'
JOURNALS_DIR = '/root/.hermes/commons/journals'


def load_jsonl(path):
    items = []
    if not os.path.exists(path):
        return items
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                pass
    return items


def append_jsonl(path, item):
    with open(path, 'a') as f:
        f.write(json.dumps(item, default=str) + '\n')


def get_next_id(prefix, existing_ids):
    ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')
    new_id = '{}-{}'.format(prefix, ts)
    while new_id in existing_ids:
        ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')
        new_id = '{}-{}'.format(prefix, ts)
    return new_id


def main():
    parser = argparse.ArgumentParser(description='Praxis review pass')
    parser.add_argument('--since-hours', type=int, default=24,
                        help='Hours to look back for recent events (default: 24)')
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=args.since_hours)

    # Load existing data
    events = load_jsonl('{}/events.jsonl'.format(DATA_DIR))
    lessons = load_jsonl('{}/lessons.jsonl'.format(DATA_DIR))
    shifts = load_jsonl('{}/shifts.jsonl'.format(DATA_DIR))
    debriefs = load_jsonl('{}/debriefs.jsonl'.format(DATA_DIR))
    evaluated = load_jsonl('{}/journals_evaluated.jsonl'.format(DATA_DIR))

    # Build evaluated set
    evaluated_ids = set()
    for e in evaluated:
        jid = e.get('journal_id', '')
        if jid:
            evaluated_ids.add(jid)

    existing_event_ids = set(e.get('event_id', '') for e in events)

    # Find all journal files (skip praxis self-journals)
    all_journals = []
    for skill_dir in glob.glob('{}/**/'.format(JOURNALS_DIR)):
        skill_name = os.path.basename(skill_dir.rstrip('/'))
        if skill_name == 'ocas-praxis':
            continue
        for json_file in glob.glob(os.path.join(skill_dir, '**', '*.json'), recursive=True):
            rel = os.path.relpath(json_file, JOURNALS_DIR)
            all_journals.append((skill_name, rel, json_file))

    # Filter to unevaluated
    unevaluated = []
    for skill_name, rel, full_path in all_journals:
        parts = rel.split('/')
        if len(parts) >= 3 and len(parts[1]) == 10 and parts[1][4] == '-':
            normalized = '{}/{}/{}'.format(parts[0], parts[1], parts[2])
        else:
            normalized = rel
        if normalized not in evaluated_ids:
            unevaluated.append((skill_name, normalized, full_path))

    print('Praxis Review Pass — {}'.format(now.isoformat()))
    print('Unevaluated journals: {}'.format(len(unevaluated)))

    # Process each unevaluated journal
    new_events = []
    new_eval_entries = []

    for skill_name, journal_id, full_path in unevaluated:
        if not os.path.exists(full_path):
            new_eval_entries.append({
                'journal_id': journal_id,
                'evaluated_at': now.isoformat(),
                'action_taken': 'skipped',
                'reason': 'File not found'
            })
            continue

        try:
            with open(full_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception):
            new_eval_entries.append({
                'journal_id': journal_id,
                'evaluated_at': now.isoformat(),
                'action_taken': 'skipped',
                'reason': 'JSON parse error'
            })
            continue

        if not isinstance(data, dict):
            new_eval_entries.append({
                'journal_id': journal_id,
                'evaluated_at': now.isoformat(),
                'action_taken': 'skipped',
                'reason': 'Non-dict journal format'
            })
            continue

        # Extract signals
        signals = []
        failure_phase = 'null'
        signal_type = 'observed'

        summary_obj = data.get('summary', {})
        decision_obj = data.get('decision', {})

        # summary may be a dict or a string — guard accordingly
        if isinstance(summary_obj, dict):
            checked = summary_obj.get('checked', 0)
            successful = summary_obj.get('successful', 0)
            blocked = summary_obj.get('blocked', 0)

            if isinstance(blocked, (int, float)) and blocked > 0:
                signals.append('blocked_operations')
            if isinstance(checked, (int, float)) and checked > 0 and isinstance(successful, (int, float)):
                rate = successful / max(checked, 1)
                if rate < 0.5:
                    signals.append('low_success_rate')
            if summary_obj.get('new_availability') is False and isinstance(checked, (int, float)) and checked > 0:
                signals.append('no_new_availability')
            blockers_active = summary_obj.get('blockers_active', 0)
            if isinstance(blockers_active, (int, float)) and blockers_active > 0:
                signals.append('blockers:{}'.format(blockers_active))
            blockers_list = summary_obj.get('blockers_list', [])
            if isinstance(blockers_list, list):
                for b in blockers_list:
                    if isinstance(b, str):
                        signals.append('blocker:{}'.format(b[:50]))

        if isinstance(decision_obj, dict):
            payload = decision_obj.get('payload', {})
            if isinstance(payload, dict):
                anomalies = payload.get('anomalies_detected', 0)
                if isinstance(anomalies, (int, float)) and anomalies > 0:
                    signals.append('anomalies:{}'.format(anomalies))
                    signal_type = 'escalation'
                    failure_phase = 'planning'

        if data.get('escalation_needed') or data.get('escalation'):
            signals.append('escalation_flagged')
            signal_type = 'escalation'
            failure_phase = 'execution'

        er = data.get('execution_result', {})
        if isinstance(er, dict):
            status = er.get('status', '')
            if status and status not in ['success', 'completed', 'ok']:
                signals.append('exec_status:{}'.format(status))
                signal_type = 'failure'
                failure_phase = 'execution'

        actions = data.get('actions_taken', [])
        if isinstance(actions, list):
            for a in actions:
                if isinstance(a, dict):
                    outcome = a.get('outcome', '')
                    if outcome and outcome not in ['success', 'ok', 'completed']:
                        signals.append('action_outcome:{}'.format(outcome))
                        if signal_type == 'observed':
                            signal_type = 'failure'
                            failure_phase = 'execution'

        if data.get('correction') or data.get('user_correction'):
            signal_type = 'correction'
            failure_phase = 'response'
            signals.append('user_correction')

        # Determine if we should record an event
        should_record = len(signals) > 0 and signal_type != 'observed'

        if should_record:
            summary_parts = []
            if isinstance(summary_obj, dict):
                summary_parts.append('checked={} successful={} blocked={}'.format(
                    summary_obj.get('checked', '?'),
                    summary_obj.get('successful', '?'),
                    summary_obj.get('blocked', '?')))
            if isinstance(decision_obj, dict):
                dt = decision_obj.get('decision_type', '')
                if dt:
                    summary_parts.append('decision_type={}'.format(dt))

            summary_text = ' | '.join(summary_parts) if summary_parts else str(signals[:3])

            eid = get_next_id('evt', existing_event_ids)

            if 'escalation' in str(signals).lower() or 'escalation_flagged' in signals:
                failure_phase = 'planning'
            elif any('block' in s.lower() for s in signals):
                failure_phase = 'execution'
            elif any('action_outcome' in s for s in signals):
                failure_phase = 'execution'

            event = {
                'event_id': eid,
                'recorded_at': now.isoformat(),
                'signal_type': signal_type,
                'failure_phase': failure_phase if failure_phase != 'null' else 'execution',
                'source_journal': journal_id,
                'summary': summary_text[:300],
                'signals': signals,
                'skill': skill_name,
            }
            new_events.append(event)
            existing_event_ids.add(eid)

            action_taken = 'event_recorded'
            reason = 'Signals: {}'.format(signals[:3])
        else:
            action_taken = 'skipped'
            reason = 'Routine/no significant signals'

        new_eval_entries.append({
            'journal_id': journal_id,
            'evaluated_at': now.isoformat(),
            'action_taken': action_taken,
            'reason': reason
        })

    # Persist
    for event in new_events:
        append_jsonl('{}/events.jsonl'.format(DATA_DIR), event)
    for entry in new_eval_entries:
        append_jsonl('{}/journals_evaluated.jsonl'.format(DATA_DIR), entry)

    # Decision log
    append_jsonl('{}/decisions.jsonl'.format(DATA_DIR), {
        'timestamp': now.isoformat(),
        'command': 'praxis_review',
        'decision': '{} new events from {} journal evaluations.'.format(len(new_events), len(new_eval_entries)),
        'events_recorded': len(new_events),
        'journals_evaluated': len(new_eval_entries),
    })

    # Evidence
    append_jsonl('{}/evidence.jsonl'.format(DATA_DIR), {
        'timestamp': now.isoformat(),
        'command': 'praxis_review',
        'side_effects': {
            'events_appended': len(new_events),
            'eval_entries_appended': len(new_eval_entries),
            'decision_appended': True
        },
        'not_activity_reason': None if new_events else 'No new signals'
    })

    # Debrief generation
    all_events = events + new_events
    active_shifts = [s for s in shifts if s.get('status') == 'active']
    proposed_shifts = [s for s in shifts if s.get('status') == 'proposed']

    recent_events = []
    for e in all_events:
        ts = e.get('recorded_at', '')
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                if dt >= cutoff:
                    recent_events.append(e)
            except Exception:
                pass

    exec_failures = [e for e in recent_events if e.get('failure_phase') == 'execution']
    plan_failures = [e for e in recent_events if e.get('failure_phase') == 'planning']
    resp_failures = [e for e in recent_events if e.get('failure_phase') == 'response']
    corrections = [e for e in recent_events if e.get('signal_type') == 'correction']
    escalations = [e for e in recent_events if e.get('signal_type') == 'escalation']
    failures = [e for e in recent_events if e.get('signal_type') == 'failure']

    # Shift decay check
    shifts_to_expire = []
    for s in active_shifts:
        lr = s.get('last_reinforced_at', '')
        if lr:
            try:
                lr_dt = datetime.fromisoformat(lr.replace('Z', '+00:00'))
                days_since = (now - lr_dt).days
                if days_since >= 14:
                    shifts_to_expire.append((s.get('shift_id', '?'), days_since,
                                             s.get('shift_text', '')[:80]))
            except Exception:
                pass

    skill_counts = {}
    for e in recent_events:
        sk = e.get('skill', 'unknown')
        skill_counts[sk] = skill_counts.get(sk, 0) + 1

    debrief_id = 'debrief-{}'.format(now.strftime('%Y%m%d-review'))
    debrief = {
        'id': debrief_id,
        'timestamp': now.isoformat(),
        'type': 'review_pass',
        'events_recorded': len(new_events),
        'total_events': len(all_events),
        'events_24h': len(recent_events),
        'active_shifts': len(active_shifts),
        'cap': 12,
        'proposed_shifts': len(proposed_shifts),
        'shifts_expired': len(shifts_to_expire),
        'phase_breakdown': {
            'execution': len(exec_failures),
            'planning': len(plan_failures),
            'response': len(resp_failures),
        },
        'signal_breakdown': {
            'failure': len(failures),
            'correction': len(corrections),
            'escalation': len(escalations),
        },
        'skill_breakdown': skill_counts,
        'shifts_to_expire': [{'shift_id': sid, 'days': d, 'text': t} for sid, d, t in shifts_to_expire],
        'summary': 'Praxis review ({}): {} new events, {} events in last {}h. Active: {}/12. Phase: exec={} plan={} resp={}. Signals: fail={} corr={} esc={}. {} shifts past decay.'.format(
            now.strftime('%Y-%m-%d %H:%M'),
            len(new_events),
            len(recent_events), args.since_hours,
            len(active_shifts),
            len(exec_failures), len(plan_failures), len(resp_failures),
            len(failures), len(corrections), len(escalations),
            len(shifts_to_expire),
        ),
        'open_questions': [
            '{} shifts proposed — should any be activated?'.format(len(proposed_shifts)) if proposed_shifts else None,
            '{} active shifts approaching decay (14d without reinforcement).'.format(len(shifts_to_expire)) if shifts_to_expire else None,
        ],
        'generated_at': now.isoformat(),
        'trigger': 'praxis_review_script',
    }
    debrief['open_questions'] = [q for q in debrief['open_questions'] if q]

    append_jsonl('{}/debriefs.jsonl'.format(DATA_DIR), debrief)

    # Journal entry
    run_id = 'praxis-review-{}'.format(now.strftime('%Y%m%dT%H%M%S'))
    journal_dir = '{}/journals/ocas-praxis/{}/'.format(
        DATA_DIR[:DATA_DIR.rfind('/data')], now.strftime('%Y-%m-%d'))
    os.makedirs(journal_dir, exist_ok=True)

    journal = {
        'run_id': run_id,
        'timestamp': now.isoformat(),
        'type': 'review_pass',
        'events_recorded': len(new_events),
        'journals_evaluated': len(new_eval_entries),
        'active_shifts': len(active_shifts),
        'debrief_id': debrief_id,
        'skills_scanned': list(skill_counts.keys()),
    }

    with open('{}/{}.json'.format(journal_dir, run_id), 'w') as f:
        json.dump(journal, f, indent=2, default=str)

    # Mark own journal as evaluated
    append_jsonl('{}/journals_evaluated.jsonl'.format(DATA_DIR), {
        'journal_id': 'ocas-praxis/{}/{}.json'.format(now.strftime('%Y-%m-%d'), run_id),
        'evaluated_at': now.isoformat(),
        'action_taken': 'skipped',
        'reason': 'Self-journal from ocas-praxis. Skip.'
    })

    # Final report
    print('')
    print('=== REVIEW COMPLETE ===')
    print('New events: {}'.format(len(new_events)))
    print('Journals evaluated: {}'.format(len(new_eval_entries)))
    print('Active shifts: {}/12'.format(len(active_shifts)))
    print('Proposed shifts: {}'.format(len(proposed_shifts)))
    print('Events in last {}h: {}'.format(args.since_hours, len(recent_events)))
    print('Phase breakdown: exec={} plan={} resp={}'.format(
        len(exec_failures), len(plan_failures), len(resp_failures)))
    print('Signal types: fail={} corr={} esc={}'.format(
        len(failures), len(corrections), len(escalations)))
    print('Shifts past decay: {}'.format(len(shifts_to_expire)))
    print('Debrief: {}'.format(debrief_id))

    if new_events:
        print('')
        print('New events:')
        for e in new_events:
            print('  [{}] {} ({}): {}'.format(
                e['signal_type'], e['event_id'], e['skill'],
                e.get('summary', '')[:80]))


if __name__ == '__main__':
    main()
