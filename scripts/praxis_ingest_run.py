#!/usr/bin/env python3
"""Praxis journal ingest — complete pipeline, safe for re-execution.
Handles already-partially-run state by skipping already-evaluated journals.
v3.1.0 — imports shared helpers from praxis_common (extracted June 2026).
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# ── Shared helpers ─────────────────────────────────────────────────────
from praxis_common import (
    DATA_DIR, JOURNALS_DIR, EVAL_FILE, EVENTS_FILE, LESSONS_FILE,
    SHIFTS_FILE, EVIDENCE_FILE, DECISIONS_FILE,
    load_jsonl, append_jsonl, now_iso, generate_id,
    dedup_eval_file, dedup_events_file, find_all_journals, read_journal,
    determine_domain, determine_failure_phase, check_disk_space,
)


NOISE_SIGNAL_TYPES = {"", "unknown", "?", "no_op", "forge_activity", "routine",
                      "no_signal", "cron_error", "cron_errors", "observation", "success",
                      "mentor_light", "correction", "low_coverage", "gap_detected"}

def is_false_positive_journal(journal_data, journal_path):
    """Check if this journal is a known false-positive source. Returns True to skip."""
    journal_name = os.path.basename(journal_path).lower()
    # Extract skill directory: path is skill/YYYY-MM-DD/filename.json or skill/filename.json
    path_parts = journal_path.split('/')
    skill_dir = path_parts[0] if path_parts else ''
    jtype = journal_data.get('type', '')
    outcome = str(journal_data.get('outcome', '')).lower().strip()
    summary = str(journal_data.get('summary', '')).lower()

    # Mentor-light: outcome=success or no outcome + no explicit failure → skip generic extraction
    if 'mentor-light' in journal_name or 'mentor-light' in journal_path:
        if outcome in ('success', '', 'none', 'null'):
            metrics = journal_data.get('metrics', {})
            errors = metrics.get('errors', 0) if isinstance(metrics, dict) else 0
            gap = journal_data.get('gap_detected', False)
            if errors == 0 and not gap:
                return True

    # Custodian observation: routine scan, no behavioral signal
    if skill_dir == 'ocas-custodian' and jtype == 'observation':
        return True

    # Custodian light-scan action with error mentions in summary (known/tracked issues)
    if skill_dir == 'ocas-custodian' and jtype == 'action':
        if 'error' in summary and 'escalation_needed' not in journal_data:
            return True

    # Custodian light-scan without type field — routine operational report
    # Some custodian journals (esp. post-2026-06-22) lack a `type` key entirely.
    # Check by run_id pattern + no escalation_needed + no persistent_failures.
    if skill_dir == 'ocas-custodian' and not jtype:
        run_id = journal_data.get('run_id', '')
        if 'light-scan' in run_id.lower() or 'deep-scan' in run_id.lower():
            escalation = journal_data.get('escalation_needed')
            persistent = journal_data.get('cron_registry', {}).get('persistent_errors', 0)
            if not escalation and not persistent:
                return True

    return False

def extract_signals(journal_data, journal_path):
    """Extract behavioral signals from a journal entry. Core Praxis logic."""
    signals = []
    if not journal_data:
        return signals

    # MANDATORY: Apply false-positive filters BEFORE any signal extraction
    if is_false_positive_journal(journal_data, journal_path):
        signals.append({'type': 'no_signal', 'severity': 'none', 'summary': 'Filtered: routine/healthy journal', 'phase': 'execution'})
        return signals

    if journal_data.get('escalation_needed') is True:
        signals.append({
            'type': 'escalation', 'severity': 'high',
            'summary': journal_data.get('escalation_reason', 'Escalation signaled'),
            'phase': 'planning',
            'fingerprint': journal_data.get('escalation_fingerprint', ''),
        })

    escalations = journal_data.get('escalations', [])
    if isinstance(escalations, list):
        for esc in escalations:
            if isinstance(esc, dict):
                esc_type = esc.get('type', '')
                signals.append({
                    'type': 'escalation',
                    'severity': 'high' if esc_type in ('new_item', 'critical') else 'medium',
                    'summary': f"{esc.get('title', 'Unknown')} — {esc.get('description', '')[:200]}",
                    'phase': 'planning', 'fingerprint': esc.get('id', ''),
                })

    decision = journal_data.get('decision', {})
    exec_result = None
    if isinstance(decision, dict):
        exec_result = decision.get('execution_result', {})
        if isinstance(exec_result, dict) and exec_result.get('status') in ('error', 'partial'):
            summary = decision.get('summary', '')
            if isinstance(summary, dict):
                summary = json.dumps(summary)
            signals.append({
                'type': 'execution_error',
                'severity': 'high' if exec_result['status'] == 'error' else 'medium',
                'summary': str(summary) if summary else f"Execution {exec_result['status']}",
                'phase': 'execution', 'error_type': exec_result['status'],
            })

    if not exec_result:
        exec_result = journal_data.get('execution_result', {})
        if isinstance(exec_result, dict) and exec_result.get('status') in ('error', 'partial'):
            signals.append({
                'type': 'execution_error',
                'severity': 'high' if exec_result['status'] == 'error' else 'medium',
                'summary': f"Execution {exec_result['status']}",
                'phase': 'execution', 'error_type': exec_result['status'],
            })

    summary_obj = journal_data.get('summary', None)
    if summary_obj is None and isinstance(decision, dict):
        summary_obj = decision.get('summary', None)

    if isinstance(summary_obj, str) and summary_obj.strip():
        sl = summary_obj.lower()
        fkw = ['failed', 'error', 'blocked', 'timeout', 'exception', 'unavailable', 'expired', 'degraded']
        ckw = ['fixed', 'corrected', 'adjusted', 'resolved']
        if any(k in sl for k in fkw) and not any(s['type'] == 'execution_error' for s in signals):
            signals.append({'type': 'failure_keyword', 'severity': 'medium', 'summary': summary_obj[:200], 'phase': 'execution'})
        if any(k in sl for k in ckw):
            signals.append({'type': 'correction', 'severity': 'low', 'summary': summary_obj[:200], 'phase': 'execution'})
    elif isinstance(summary_obj, dict) and not any(s['type'] == 'execution_error' for s in signals):
        top_status = journal_data.get('status', '')
        top_type = journal_data.get('type', '')
        if top_status not in ('ok', 'success', 'completed') and top_type != 'observation':
            ss = json.dumps(summary_obj).lower()
            if any(k in ss for k in ['fail', 'error', 'block', 'degrad']):
                signals.append({'type': 'failure_keyword', 'severity': 'medium', 'summary': str(summary_obj)[:200], 'phase': 'execution'})

    actions_taken = journal_data.get('actions_taken', [])
    if isinstance(actions_taken, int):
        actions_taken = []
    for action in actions_taken:
        if isinstance(action, dict):
            outcome = str(action.get('outcome', '')).lower()
            if outcome in ('error', 'failed', 'failure', 'blocked'):
                signals.append({'type': 'action_failure', 'severity': 'high', 'summary': f"Action failed: {outcome}", 'phase': 'execution'})

    active_blockers = journal_data.get('active_blockers', [])
    if isinstance(active_blockers, int):
        active_blockers = []
    for blocker in active_blockers:
        if isinstance(blocker, dict):
            bid = blocker.get('id', '')
            impact = blocker.get('impact', '')
            fresh = blocker.get('fresh_consent_urls_issued', False)
            if fresh or 'oauth' in bid.lower() or 'auth' in bid.lower():
                signals.append({'type': 'auth_failure', 'severity': 'high', 'summary': f"Active blocker: {bid} — {impact[:100]}", 'phase': 'execution', 'fingerprint': bid})
            elif bid:
                signals.append({'type': 'platform_failure', 'severity': 'medium', 'summary': f"Active blocker: {bid} — {impact[:100]}", 'phase': 'execution', 'fingerprint': bid})

    new_findings = journal_data.get('new_findings', [])
    if isinstance(new_findings, int):
        new_findings = []
    for finding in new_findings:
        if isinstance(finding, dict) and finding.get('severity') in ('critical', 'error', 'high'):
            signals.append({'type': 'new_finding', 'severity': 'high', 'summary': finding.get('title', 'Unknown'), 'phase': 'planning'})

    return signals


def main():
    print(f"=== Praxis Journal Ingest — {now_iso()} ===\n")

    if not check_disk_space():
        append_jsonl(EVIDENCE_FILE, [{
            'evidence_id': generate_id('evid'), 'recorded_at': now_iso(),
            'run_type': 'journal_ingest', 'not_activity_reason': 'aborted: disk_full',
            'journals_total': 0, 'journals_new_processed': 0, 'events_recorded': 0,
            'lessons_extracted': 0, 'active_shifts': 0,
        }])
        return

    # Step 1: Dedup eval file
    print("[1/7] Deduplicating journals_evaluated.jsonl...")
    eval_records = dedup_eval_file()
    eval_ids = set(eval_records.keys())

    # Step 2: Scan filesystem
    print("[2/7] Scanning filesystem...")
    all_journals = find_all_journals()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')

    unevaluated_recent = []
    for full_path, cid in all_journals:
        lookup = cid if cid.endswith('.json') else cid + '.json'
        if lookup not in eval_ids and cid not in eval_ids:
            if today in cid or yesterday in cid:
                unevaluated_recent.append((full_path, lookup))

    print(f"  Found {len(all_journals)} total journals, {len(unevaluated_recent)} new from today/yesterday")

    # Step 3: Process new journals
    new_events = []
    new_eval_entries = []

    if unevaluated_recent:
        print(f"\n[3/7] Processing {len(unevaluated_recent)} new journals...")
        for full_path, canonical_id_str in sorted(unevaluated_recent):
            journal_data = read_journal(full_path)
            if not journal_data:
                new_eval_entries.append({'journal_id': canonical_id_str, 'evaluated_at': now_iso(), 'action_taken': 'unreadable'})
                continue

            signals = extract_signals(journal_data, canonical_id_str)
            if signals:
                priority = {'escalation': 0, 'execution_error': 1, 'action_failure': 2, 'new_finding': 3, 'failure_keyword': 4, 'correction': 5}
                signals.sort(key=lambda s: priority.get(s['type'], 99))
                primary = signals[0]
                domain = determine_domain(canonical_id_str)

                if domain in ('unknown', None, '', 'null'):
                    new_eval_entries.append({'journal_id': canonical_id_str, 'evaluated_at': now_iso(), 'action_taken': 'skipped_unknown_domain'})
                    continue

                event = {
                    'event_id': generate_id('evt'), 'recorded_at': now_iso(),
                    'source_journal': canonical_id_str, 'domain': domain,
                    'failure_phase': determine_failure_phase(signals),
                    'signal_type': primary['type'], 'severity': primary['severity'],
                    'summary': primary['summary'][:300],
                    'all_signals': json.dumps([{'type': s['type'], 'phase': s['phase'], 'severity': s['severity']} for s in signals]),
                }
                new_events.append(event)
                action = 'event_recorded'
            else:
                action = 'no_signal'

            new_eval_entries.append({'journal_id': canonical_id_str, 'evaluated_at': now_iso(), 'action_taken': action})

        if new_events:
            append_jsonl(EVENTS_FILE, new_events)
            print(f"  Recorded {len(new_events)} events")
        if new_eval_entries:
            append_jsonl(EVAL_FILE, new_eval_entries)
            print(f"  Marked {len(new_eval_entries)} journals evaluated")

    # Step 4: Post-write event dedup
    print(f"\n[4/7] Post-write event dedup...")
    new_event_ids = set(e['event_id'] for e in new_events)
    removed_count = dedup_events_file(new_event_ids)
    print(f"  {'Removed ' + str(removed_count) + ' duplicates' if removed_count else 'No duplicate events found'}")

    # Step 5: Lesson extraction
    print(f"\n[5/7] Running lesson extraction...")
    all_events = load_jsonl(EVENTS_FILE)
    pattern_groups = {}
    valid_event_ids = set()
    for evt in all_events:
        eid = evt.get('event_id', '')
        if eid:
            valid_event_ids.add(eid)
        domain = evt.get('domain', 'unknown')
        phase = evt.get('failure_phase', 'null')
        sig_type = evt.get('signal_type', 'unknown')
        if domain in ('unknown', None, '', 'null') or phase in ('null', None, ''):
            continue
        if sig_type in NOISE_SIGNAL_TYPES:
            continue
        key = (domain, phase, sig_type)
        pattern_groups.setdefault(key, []).append(evt)

    existing_lessons = load_jsonl(LESSONS_FILE)
    existing_lesson_keys = set((l.get('domain', ''), l.get('failure_phase', ''), l.get('pattern_key', '')) for l in existing_lessons)

    new_lessons = []
    for (domain, phase, signal_type), group in pattern_groups.items():
        if signal_type in ('unknown', '?', None, ''):
            continue
        if (domain, phase, signal_type) in existing_lesson_keys:
            continue
        min_count = 2 if phase != 'null' else 3
        if len(group) >= min_count:
            why_map = {
                'execution_error': f"Tool execution or parameter errors recurring in {domain} during {phase}",
                'action_failure': f"Tool execution or parameter errors recurring in {domain} during {phase}",
                'escalation': f"Escalation-severity findings in {domain} indicating systemic issue",
                'failure_keyword': f"Repeated failure indicators in {domain} {phase} phase",
            }
            why = why_map.get(signal_type)
            confidence = 'high' if (why and phase != 'null' and domain != 'unknown') else 'low'
            if confidence == 'low' and len(group) < 3:
                continue
            source_eids = [e['event_id'] for e in group[:10] if e.get('event_id', '') in valid_event_ids]
            lesson = {
                'lesson_id': generate_id('les'), 'extracted_at': now_iso(),
                'domain': domain, 'failure_phase': phase, 'pattern_key': signal_type,
                'event_count': len(group), 'source_event_ids': source_eids,
                'what': f"{len(group)} events of type '{signal_type}' in {domain} during {phase} phase",
                'why': why or 'Pattern detected - causal mechanism requires further evidence',
                'when': f"In {domain} skill execution during {phase} phase",
                'lesson_text': f"In {domain} during {phase}: {signal_type} errors recur (n={len(group)}). {'Root cause: ' + why if why else 'Root cause pending.'}",
                'confidence': confidence, 'status': 'extracted',
            }
            new_lessons.append(lesson)
            existing_lesson_keys.add((domain, phase, signal_type))

    if new_lessons:
        append_jsonl(LESSONS_FILE, new_lessons)
        print(f"  Extracted {len(new_lessons)} new lessons")
    else:
        print(f"  No new patterns detected")

    # Step 6: Evidence
    print(f"\n[6/7] Writing evidence and summary...")
    active_count = sum(1 for s in load_jsonl(SHIFTS_FILE) if s.get('status') == 'active')
    append_jsonl(EVIDENCE_FILE, [{
        'evidence_id': generate_id('evid'), 'recorded_at': now_iso(),
        'run_type': 'journal_ingest', 'journals_total': len(all_journals),
        'journals_new_processed': len(new_eval_entries), 'events_recorded': len(new_events),
        'events_deduped': removed_count, 'lessons_extracted': len(new_lessons),
        'active_shifts': active_count,
        **({'not_activity_reason': 'No new journals; lesson extraction only'} if not unevaluated_recent else {}),
    }])

    # Summary
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
        print(f"\n  Domains affected: {', '.join(sorted(set(e['domain'] for e in new_events)))}")
        print(f"  Phases affected:  {', '.join(sorted(set(e['failure_phase'] for e in new_events)))}")
    if new_lessons:
        print(f"\n  NEW LESSONS:")
        for les in new_lessons:
            print(f"    [{les['confidence']}] {les['domain']}/{les['failure_phase']}: {les['lesson_text'][:120]}")


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(
        description="Praxis journal ingest — complete re-execution-safe pipeline.",
        usage="python3 praxis_ingest_run.py [--mode {cron,dispatch,single}]")
    p.add_argument("--mode", choices=["cron", "dispatch", "single"], default="cron",
                   help="Run context: cron (default), dispatch, or single-skill. "
                        "NOTE: this script MUTATES state and writes journals — never "
                        "invoke as a no-op/inspection call.")
    args = p.parse_args()
    main()  # mode currently informational; full pipeline runs regardless
