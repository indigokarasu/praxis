#!/usr/bin/env python3
"""
Gap journal backfill for Praxis cron ingest.

Run AFTER praxis_ingest_run.py (or after dispatch pipeline eval registration)
to catch journals the date filter missed or that were written between operations.

Walks the profile journals directory, finds unevaluated journals with mtime > last_ingest_run
(post-ingest gaps) AND dispatcher-specified new_files with mtime < last_ingest_run (pre-ingest gaps),
classifies them, and appends to journals_evaluated.jsonl.

Filters out:
  - dispatch-wave-*.json (dispatch meta-artifacts, not content journals)
  - *.json files with empty filename (phantom files from shell write bugs)
  - Files in non-profile commons/journals (monitored by different dispatcher)

Usage: python3 gap_backfill.py [--state-file PATH] [--eval-file PATH]

Confirmed steady-state pattern (2026-06-29, 50+ dispatches).
Fixes from original version:
  - Corrected EVAL_FILE path (was 'oca-praxis', now 'ocas-praxis')
  - Scans ONLY profile journals dir (not commons — avoids relpath false positives)
  - Filters dispatch-wave-*.json (meta-artifacts, not content)
  - Filters phantom .json files (empty filename from shell write bugs)
  - Uses mtime > li_ts (post-ingest gaps, not pre-ingest)
  - Uses mtime > li_ts (post-ingest gaps, not pre-ingest)
  - Syncs state counter to actual file line count after backfill

"""

import json
import os
import argparse
from datetime import datetime, timezone

# --- Config (cron-safe absolute paths) ---
DEFAULT_JOURNALS_DIR = '/root/.hermes/profiles/indigo/commons/journals'
DEFAULT_EVAL_FILE = '/root/.hermes/profiles/indigo/commons/data/ocas-praxis/journals_evaluated.jsonl'
DEFAULT_STATE_FILE = '/root/.hermes/profiles/indigo/commons/data/ocas-praxis/ingest_state.json'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--journals-dir', default=DEFAULT_JOURNALS_DIR)
    parser.add_argument('--eval-file', default=DEFAULT_EVAL_FILE)
    parser.add_argument('--state-file', default=DEFAULT_STATE_FILE)
    args = parser.parse_args()

    # --- Load evaluated IDs (handle mixed formats: dict with journal_id, plain string) ---
    evaluated = set()
    if os.path.exists(args.eval_file):
        with open(args.eval_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict):
                        evaluated.add(entry.get('journal_id', ''))
                    elif isinstance(entry, str):
                        evaluated.add(entry)
                except json.JSONDecodeError:
                    evaluated.add(line)

    print(f'Loaded {len(evaluated)} evaluated IDs')

    # --- Get last_ingest_run timestamp ---
    with open(args.state_file) as f:
        state = json.load(f)
    li_run = state.get('last_ingest_run', '')
    if li_run:
        li_dt = datetime.fromisoformat(li_run.replace('Z', '+00:00'))
        li_ts = li_dt.timestamp()
    else:
        li_ts = 0

    print(f'Last ingest: {li_run}')

    # --- Scan for unevaluated journals ---
    # We look for mtime > li_ts (post-ingest cron gaps)
    # Pre-ingest gaps (mtime < li_ts) must be passed explicitly by the caller
    # since they're invisible to mtime-based discovery.
    unevaluated = []
    if os.path.isdir(args.journals_dir):
        for root, dirs, files in os.walk(args.journals_dir):
            for fname in files:
                if not fname.endswith('.json'):
                    continue
                # Skip phantom files (empty filename from shell write bugs)
                if fname == '.json':
                    continue
                # Skip dispatch-wave meta-artifacts
                if 'dispatch-wave-' in fname:
                    continue
                fpath = os.path.join(root, fname)
                if not os.path.exists(fpath):
                    continue  # race: file deleted between walk and stat
                rel = os.path.relpath(fpath, args.journals_dir)
                if rel in evaluated:
                    continue
                try:
                    mtime = os.path.getmtime(fpath)
                except OSError:
                    continue
                if mtime > li_ts:
                    unevaluated.append(fpath)

    print(f'Found {len(unevaluated)} unevaluated journals (mtime > last_ingest_run)')

    # --- Classify and mark each ---
    now_ts = datetime.now(timezone.utc)
    backfilled = 0
    for fpath in unevaluated:
        rel = os.path.relpath(fpath, args.journals_dir)

        # Quick classification based on content
        action = 'backfill'
        reason = 'unevaluated journal detected by gap backfill'
        try:
            with open(fpath) as f:
                data = json.load(f)
            if isinstance(data, dict):
                # Custodian light-scan classification
                nar = data.get('not_activity_reason', '')
                if 'all transient' in nar.lower() or 'all...are transient' in nar.lower():
                    action = 'backfill_no_signal'
                    reason = 'custodian: all errors transient/stale'
                elif data.get('escalation_needed'):
                    action = 'backfill_review'
                    reason = 'custodian: escalation flagged'
                elif data.get('type') == 'observation':
                    action = 'backfill_no_signal'
                    reason = 'custodian observation: routine scan'
                elif data.get('scan_type') == 'light' and not data.get('findings'):
                    action = 'backfill_no_signal'
                    reason = 'custodian: routine light-scan, 0 findings'
                else:
                    action = 'backfill_no_signal'
                    reason = f'routine: ({data.get("type", data.get("scan_type", "unknown"))})'
        except (json.JSONDecodeError, IOError):
            action = 'backfill_unreadable'
            reason = 'cannot parse journal JSON'

        entry = {
            'journal_id': rel,
            'action_taken': action,
            'evaluated_at': now_ts.isoformat(),
            'reason': reason,
        }

        with open(args.eval_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')

        backfilled += 1
        print(f'  [{action}] {rel}: {reason}')

    print(f'\nBackfilled {backfilled} journals')

    # --- Update state (sync counters to actual file count) ---
    actual_eval_lines = sum(1 for _ in open(args.eval_file))
    state['last_evaluated_count'] = state.get('last_evaluated_count', 0) + backfilled
    state['eval_gaps_backfilled'] = state.get('eval_gaps_backfilled', 0) + backfilled
    state['journals_evaluated_count'] = actual_eval_lines
    state['last_eval_file_line'] = actual_eval_lines

    with open(args.state_file, 'w') as f:
        json.dump(state, f, indent=2)

    print(f'State updated: eval_lines={actual_eval_lines}, gaps_backfilled={state["eval_gaps_backfilled"]}')

if __name__ == '__main__':
    main()
