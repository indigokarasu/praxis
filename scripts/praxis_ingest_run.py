#!/usr/bin/env python3
"""Praxis journal ingest — complete pipeline, safe for re-execution.
Handles already-partially-run state by skipping already-evaluated journals.
v3.0.2 — fixes: escalations array support (finch schema), dict-summary noise filter for success-status scans, batch ID collision (monotonic_ns), post-write event dedup before lesson extraction."""
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

AGENT_ROOT = "/root/.hermes"
JOURNALS_DIR = os.path.join(AGENT_ROOT, "commons/journals")
DATA_DIR = os.path.join(AGENT_ROOT, "commons/data/ocas-praxis")
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
DEBRIEF_FILE = os.path.join(DATA_DIR, "debriefs.jsonl")
EVIDENCE_FILE = os.path.join(DATA_DIR, "evidence.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")

SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}

# Global sequence counter for unique IDs within a single process run
_id_counter = 0

def load_jsonl(path):
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

def append_jsonl(path, records):
    with open(path, 'a') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def generate_id(prefix):
    """Generate a unique ID using monotonic_ns() to avoid microsecond collision in tight loops."""
    global _id_counter
    _id_counter += 1
    return f"{prefix}-{time.monotonic_ns():020d}-{_id_counter:04d}"

def dedup_eval_file():
    records = load_jsonl(EVAL_FILE)
    seen = {}
    duplicates = 0
    for r in records:
        jid = r.get('journal_id', '')
        canonical = jid if jid.endswith('.json') else jid + '.json'
        if canonical not in seen:
            seen[canonical] = r
        else:
            duplicates += 1
    if duplicates > 0:
        with open(EVAL_FILE, 'w') as f:
            for r in seen.values():
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        print(f"  Dedup eval file: removed {duplicates} duplicates -> {len(seen)} unique")
    return seen

def dedup_events_file(new_event_ids):
    """Dedup events.jsonl by event_id after append. Returns count removed."""
    all_events = load_jsonl(EVENTS_FILE)
    if not all_events:
        return 0
    seen_ids = {}
    deduped = []
    removed = 0
    for evt in all_events:
        eid = evt.get('event_id', '')
        if eid not in seen_ids:
            seen_ids[eid] = True
            deduped.append(evt)
        else:
            removed += 1
            if eid in new_event_ids:
                print(f"  Removed duplicate event: {eid}")
    if removed > 0:
        with open(EVENTS_FILE, 'w') as f:
            for evt in deduped:
                f.write(json.dumps(evt, ensure_ascii=False) + '\n')
    return removed

def find_all_journals():
    journals = []
    for skill_dir in os.listdir(JOURNALS_DIR):
        skill_path = os.path.join(JOURNALS_DIR, skill_dir)
        if not os.path.isdir(skill_path):
            continue
        if skill_dir in SKIP_DIRS:
            continue
        for root, dirs, files in os.walk(skill_path):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fname in files:
                if not fname.endswith('.json'):
                    continue
                full_path = os.path.join(root, fname)
                rel = os.path.relpath(full_path, JOURNALS_DIR)
                parts = rel.split(os.sep)
                if len(parts) >= 3:
                    skill, date_dir, filename = parts[0], parts[1], parts[-1]
                    cid = f"{skill}/{date_dir}/{filename}"
                    journals.append((full_path, cid))
                elif len(parts) == 2:
                    cid = f"{parts[0]}/no-date/{parts[1]}"
                    journals.append((full_path, cid))
    return journals

def read_journal(path):
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 0:
            return data[-1]
        elif isinstance(data, dict):
            return data
    except (json.JSONDecodeError, IOError, OSError):
        pass
    return None

def extract_signals(journal_data, journal_path):
    signals = []
    if not journal_data:
        return signals

    if journal_data.get('escalation_needed') is True:
        signals.append({
            'type': 'escalation',
            'severity': 'high',
            'summary': journal_data.get('escalation_reason', 'Escalation signaled'),
            'phase': 'planning',
            'fingerprint': journal_data.get('escalation_fingerprint', '')
        })

    # Finch and other skills may use `escalations` array instead of top-level boolean
    escalations = journal_data.get('escalations', [])
    if isinstance(escalations, list):
        for esc in escalations:
            if isinstance(esc, dict):
                esc_type = esc.get('type', '')
                esc_title = esc.get('title', 'Unknown escalation')
                esc_desc = esc.get('description', '')[:200]
                severity = 'high' if esc_type in ('new_item', 'critical') else 'medium'
                signals.append({
                    'type': 'escalation',
                    'severity': severity,
                    'summary': f"{esc_title} — {esc_desc}",
                    'phase': 'planning',
                    'fingerprint': esc.get('id', esc_title)
                })

    decision = journal_data.get('decision', {})
    exec_result = None
    if isinstance(decision, dict):
        exec_result = decision.get('execution_result', {})
        if isinstance(exec_result, dict):
            status = exec_result.get('status', '')
            if status in ('error', 'partial'):
                summary = decision.get('summary', '')
                if isinstance(summary, dict):
                    summary = json.dumps(summary)
                signals.append({
                    'type': 'execution_error',
                    'severity': 'high' if status == 'error' else 'medium',
                    'summary': str(summary) if summary else f'Execution {status}',
                    'phase': 'execution',
                    'error_type': status
                })

    if not exec_result:
        exec_result = journal_data.get('execution_result', {})
        if isinstance(exec_result, dict):
            status = exec_result.get('status', '')
            if status in ('error', 'partial'):
                signals.append({
                    'type': 'execution_error',
                    'severity': 'high' if status == 'error' else 'medium',
                    'summary': f'Execution {status}',
                    'phase': 'execution',
                    'error_type': status
                })

    summary_obj = journal_data.get('summary', None)
    if summary_obj is None and isinstance(decision, dict):
        summary_obj = decision.get('summary', None)

    if isinstance(summary_obj, str) and summary_obj.strip():
        summary_lower = summary_obj.lower()
        failure_keywords = ['failed', 'error', 'blocked', 'timeout', 'exception', 'unavailable', 'expired', 'degraded']
        correction_keywords = ['fixed', 'corrected', 'adjusted', 'resolved']
        has_failure = any(kw in summary_lower for kw in failure_keywords)
        has_correction = any(kw in summary_lower for kw in correction_keywords)
        if has_failure and not any(s['type'] == 'execution_error' for s in signals):
            signals.append({'type': 'failure_keyword', 'severity': 'medium', 'summary': summary_obj[:200], 'phase': 'execution'})
        if has_correction:
            signals.append({'type': 'correction', 'severity': 'low', 'summary': summary_obj[:200], 'phase': 'execution'})
    elif isinstance(summary_obj, dict) and not any(s['type'] == 'execution_error' for s in signals):
        # Dict-format summaries are structured scan results (e.g., finch, custodian light-scan).
        # Only extract failure signals if the top-level status/type doesn't indicate success.
        # Many scan journals have summary dicts containing failure counts/data for *other* systems
        # while the scan itself completed successfully.
        top_status = journal_data.get('status', '')
        top_type = journal_data.get('type', '')
        if top_status in ('ok', 'success', 'completed') or top_type == 'observation':
            # Scan reported success — keywords in its data describe external state, not skill failure
            pass
        else:
            summary_str = json.dumps(summary_obj).lower()
            if any(kw in summary_str for kw in ['fail', 'error', 'block', 'degrad']):
                signals.append({'type': 'failure_keyword', 'severity': 'medium', 'summary': str(summary_obj)[:200], 'phase': 'execution'})

    actions = journal_data.get('actions_taken', [])
    if isinstance(actions, list):
        for action in actions:
            if isinstance(action, dict):
                outcome = action.get('outcome', '')
                if isinstance(outcome, str) and outcome.lower() in ('error', 'failed', 'failure', 'blocked'):
                    signals.append({'type': 'action_failure', 'severity': 'high', 'summary': f"Action failed: {outcome}", 'phase': 'execution'})

    # Finch full rescan: active_blockers[] at top level
    active_blockers = journal_data.get('active_blockers', [])
    if isinstance(active_blockers, list):
        for blocker in active_blockers:
            if isinstance(blocker, dict):
                blocker_id = blocker.get('id', '')
                impact = blocker.get('impact', '')
                fresh_consent = blocker.get('fresh_consent_urls_issued', False)
                if fresh_consent or 'oauth' in blocker_id.lower() or 'auth' in blocker_id.lower():
                    signals.append({
                        'type': 'auth_failure',
                        'severity': 'high',
                        'summary': f"Active blocker: {blocker_id} — impacts: {impact[:100]}",
                        'phase': 'execution',
                        'fingerprint': blocker_id
                    })
                elif blocker_id:
                    signals.append({
                        'type': 'platform_failure',
                        'severity': 'medium',
                        'summary': f"Active blocker: {blocker_id} — {impact[:100]}",
                        'phase': 'execution',
                        'fingerprint': blocker_id
                    })

    findings = journal_data.get('new_findings', [])
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict):
                sev = finding.get('severity', '')
                if sev in ('critical', 'error', 'high'):
                    signals.append({'type': 'new_finding', 'severity': 'high', 'summary': finding.get('title', 'Unknown'), 'phase': 'planning'})

    return signals

def determine_domain(journal_id):
    parts = journal_id.split('/')
    return parts[0] if parts else 'unknown'

def determine_failure_phase(signals):
    for s in signals:
        phase = s.get('phase', 'null')
        if phase in ('planning', 'execution', 'response'):
            return phase
    return 'null'

def main():
    print(f"=== Praxis Journal Ingest — {now_iso()} ===\n")

    # Step 1: Dedup eval file
    print("[1/6] Deduplicating journals_evaluated.jsonl...")
    eval_records = dedup_eval_file()
    eval_ids = set(eval_records.keys())

    # Step 2: Find all journals, diff against eval
    print("[2/6] Scanning filesystem...")
    all_journals = find_all_journals()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')

    unevaluated_recent = []
    for full_path, canonical_id_str in all_journals:
        lookup_id = canonical_id_str if canonical_id_str.endswith('.json') else canonical_id_str + '.json'
        if lookup_id not in eval_ids and canonical_id_str not in eval_ids:
            if today in canonical_id_str or yesterday in canonical_id_str:
                unevaluated_recent.append((full_path, lookup_id))

    print(f"  Found {len(all_journals)} total journals, {len(unevaluated_recent)} new from today/yesterday")

    if not unevaluated_recent:
        print("\nNo new journals. Running lesson extraction on existing events...")

    # Step 3: Process new journals - extract signals and record events
    new_events = []
    new_eval_entries = []
    processed_sources = set()

    if unevaluated_recent:
        print(f"\n[3/6] Processing {len(unevaluated_recent)} new journals...")
        for full_path, canonical_id_str in sorted(unevaluated_recent):
            journal_data = read_journal(full_path)
            if not journal_data:
                new_eval_entries.append({'journal_id': canonical_id_str, 'evaluated_at': now_iso(), 'action_taken': 'unreadable'})
                continue

            signals = extract_signals(journal_data, full_path)
            if signals:
                priority_order = {'escalation': 0, 'execution_error': 1, 'action_failure': 2, 'new_finding': 3, 'failure_keyword': 4, 'correction': 5}
                signals.sort(key=lambda s: priority_order.get(s['type'], 99))
                primary = signals[0]
                domain = determine_domain(canonical_id_str)

                if domain in ('unknown', None, '', 'null'):
                    new_eval_entries.append({'journal_id': canonical_id_str, 'evaluated_at': now_iso(), 'action_taken': 'skipped_unknown_domain'})
                    processed_sources.add(canonical_id_str)
                    continue

                failure_phase = determine_failure_phase(signals)
                event = {
                    'event_id': generate_id('evt'),
                    'recorded_at': now_iso(),
                    'source_journal': canonical_id_str,
                    'domain': domain,
                    'failure_phase': failure_phase,
                    'signal_type': primary['type'],
                    'severity': primary['severity'],
                    'summary': primary['summary'][:300],
                    'all_signals': json.dumps([{'type': s['type'], 'phase': s['phase'], 'severity': s['severity']} for s in signals])
                }
                new_events.append(event)
                action = 'event_recorded'
            else:
                action = 'no_signal'

            new_eval_entries.append({'journal_id': canonical_id_str, 'evaluated_at': now_iso(), 'action_taken': action})
            processed_sources.add(canonical_id_str)

        if new_events:
            append_jsonl(EVENTS_FILE, new_events)
            print(f"  Recorded {len(new_events)} events")
        if new_eval_entries:
            append_jsonl(EVAL_FILE, new_eval_entries)
            print(f"  Marked {len(new_eval_entries)} journals evaluated")

    # Step 4: Post-write event dedup (MANDATORY - before lesson extraction)
    print(f"\n[4/6] Post-write event dedup...")
    new_event_ids = set(e['event_id'] for e in new_events)
    removed_count = dedup_events_file(new_event_ids)
    if removed_count > 0:
        print(f"  Removed {removed_count} duplicate events from events.jsonl")
    else:
        print(f"  No duplicate events found")

    # Step 5: Lesson extraction (AFTER dedup - source_event_ids will be valid)
    print(f"\n[5/6] Running lesson extraction...")
    all_events = load_jsonl(EVENTS_FILE)
    pattern_groups = {}
    valid_event_ids = set()
    for evt in all_events:
        eid = evt.get('event_id', '')
        if eid:
            valid_event_ids.add(eid)
        domain = evt.get('domain', 'unknown')
        phase = evt.get('failure_phase', 'null')
        if domain in ('unknown', None, '', 'null'):
            continue
        if phase in ('null', None, ''):
            continue
        key = (domain, phase, evt.get('signal_type', 'unknown'))
        if key not in pattern_groups:
            pattern_groups[key] = []
        pattern_groups[key].append(evt)

    existing_lessons = load_jsonl(LESSONS_FILE)
    existing_lesson_keys = set()
    for les in existing_lessons:
        k = (les.get('domain', ''), les.get('failure_phase', ''), les.get('pattern_key', ''))
        existing_lesson_keys.add(k)

    new_lessons = []
    for (domain, phase, signal_type), group_events in pattern_groups.items():
        if signal_type in ('unknown', '?', None, ''):
            continue
        lesson_key = (domain, phase, signal_type)
        if lesson_key in existing_lesson_keys:
            continue
        min_count = 2 if phase != 'null' else 3
        if len(group_events) >= min_count:
            why = None
            if signal_type in ('execution_error', 'action_failure'):
                why = f"Tool execution or parameter errors recurring in {domain} during {phase}"
            elif signal_type == 'escalation':
                why = f"Escalation-severity findings in {domain} indicating systemic issue"
            elif signal_type == 'failure_keyword':
                why = f"Repeated failure indicators in {domain} {phase} phase"

            when = f"In {domain} skill execution during {phase} phase"
            confidence = 'high' if (why and phase != 'null' and domain and domain != 'unknown') else 'low'
            if confidence == 'low' and len(group_events) < 3:
                continue

            # Filter source_event_ids to only include valid (post-dedup) event IDs
            source_eids = [e.get('event_id', '') for e in group_events[:10] if e.get('event_id', '') in valid_event_ids]

            lesson = {
                'lesson_id': generate_id('les'),
                'extracted_at': now_iso(),
                'domain': domain,
                'failure_phase': phase,
                'pattern_key': signal_type,
                'event_count': len(group_events),
                'source_event_ids': source_eids,
                'what': f"{len(group_events)} events of type '{signal_type}' in {domain} during {phase} phase",
                'why': why or 'Pattern detected - causal mechanism requires further evidence',
                'when': when,
                'lesson_text': f"In {domain} during {phase}: {signal_type} errors recur (n={len(group_events)}). {'Root cause: ' + why if why else 'Root cause pending.'}",
                'confidence': confidence,
                'status': 'extracted'
            }
            new_lessons.append(lesson)
            existing_lesson_keys.add(lesson_key)

    if new_lessons:
        append_jsonl(LESSONS_FILE, new_lessons)
        print(f"  Extracted {len(new_lessons)} new lessons")
    else:
        print(f"  No new patterns detected")

    # Step 6: Summary + evidence
    print(f"\n[6/6] Writing evidence and summary...")
    all_shifts = load_jsonl(SHIFTS_FILE)
    active_count = sum(1 for s in all_shifts if s.get('status') == 'active')

    evidence = {
        'evidence_id': generate_id('evid'),
        'recorded_at': now_iso(),
        'run_type': 'journal_ingest',
        'journals_total': len(all_journals),
        'journals_new_processed': len(new_eval_entries),
        'events_recorded': len(new_events),
        'events_deduped': removed_count,
        'lessons_extracted': len(new_lessons),
        'active_shifts': active_count,
        **({'not_activity_reason': 'No new journals; lesson extraction only'} if not unevaluated_recent else {})
    }
    append_jsonl(EVIDENCE_FILE, [evidence])

    print(f"\n{'='*50}")
    print(f"  Journals on disk:       {len(all_journals)}")
    print(f"  New journals processed:  {len(new_eval_entries)}")
    print(f"  Events recorded:         {len(new_events)}")
    print(f"  Events deduped:          {removed_count}")
    print(f"  Lessons extracted:       {len(new_lessons)}")
    print(f"  Active shifts:           {active_count}/12")
    print(f"  Total events in store:   {len(all_events)}")
    print(f"  Total lessons in store:  {len(existing_lessons) + len(new_lessons)}")
    print(f"{'='*50}")

    if new_events:
        print(f"\n  NEW EVENTS:")
        for e in new_events:
            print(f"    [{e['severity']}] {e['domain']}/{e['failure_phase']} - {e['signal_type']}: {e['summary'][:100]}")
    if new_lessons:
        print(f"\n  NEW LESSONS:")
        for les in new_lessons:
            print(f"    [{les['confidence']}] {les['domain']}/{les['failure_phase']}: {les['lesson_text'][:120]}")

    if new_events:
        domains_affected = set(e['domain'] for e in new_events)
        phases = set(e['failure_phase'] for e in new_events)
        print(f"\n  Domains affected: {', '.join(sorted(domains_affected))}")
        print(f"  Phases affected:  {', '.join(sorted(phases))}")

if __name__ == '__main__':
    main()
