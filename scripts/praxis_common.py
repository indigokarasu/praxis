#!/usr/bin/env python3
"""praxis_common.py — Shared constants, paths, and utilities for Praxis ingest scripts.
Extracted from 20+ duplicated daily ingest runs (June 8-15 2026).
Single source of truth for paths, constants, and helper functions.

DUAL-JOURNAL FIX (2026-06-21): find_all_journals() now walks BOTH journal directories.
Previously only walked JOURNALS_DIR (legacy path), missing 8,335 journals in the indigo
profile path. JOURNALS_DIRS list added; JOURNALS_DIR kept for backward compat.
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta

# Paths
AGENT_ROOT = "/root/.hermes/profiles/indigo"

# DUAL-JOURNAL FIX: JOURNALS_DIR kept for backward compat; JOURNALS_DIRS is the
# canonical list. find_all_journals() walks both.
JOURNALS_DIR = "/root/.hermes/commons/journals"
JOURNALS_DIRS = [
    "/root/.hermes/profiles/indigo/commons/journals",
    "/root/.hermes/commons/journals",
]
DATA_DIR = os.path.join(AGENT_ROOT, "commons/data/ocas-praxis")
EVAL_FILE = os.path.join(DATA_DIR, "journals_evaluated.jsonl")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.jsonl")
SHIFTS_FILE = os.path.join(DATA_DIR, "shifts.jsonl")
DEBRIEF_FILE = os.path.join(DATA_DIR, "debriefs.jsonl")
EVIDENCE_FILE = os.path.join(DATA_DIR, "evidence.jsonl")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.jsonl")
JOURNAL_DIR = os.path.join(DATA_DIR, "journals", "ocas-praxis")

SKIP_DIRS = {"ocas-praxis"}
ACTIVE_SHIFT_CAP = 12
SHIFT_DECAY_DAYS = 14

SUPPRESS_PHRASES = [
    "all clean", "system healthy", "no new actionable", "no tier 1 fixes",
    "transient", "self-resolving", "no action needed", "no intervention",
    "stable at", "all errors transient", "consecutive_failures=0",
    "stale counter", "stale failure", "known pattern", "already tracked",
    "operational", "healthy",
]

FAILURE_KEYWORDS = [
    "error", "fail", "failed", "failure", "crash", "exception",
    "timeout", "broken", "unreachable", "denied", "refused",
    "corrupt", "invalid", "missing", "expired", "revoked",
    "unauthorized", "forbidden", "conflict", "abort",
]

AUTH_KEYWORDS = [
    "oauth", "token", "auth", "401", "403", "credential",
    "permission denied", "unauthorized", "expired token",
    "revoked", "calendar oauth",
]

MEANINGFUL_SIGNAL_TYPES = {
    "auth_failure", "escalation", "execution_error", "correction",
    "cron_errors", "failure_keyword", "platform_failure",
    "rate_limit", "timeout", "parse_error", "config_error",
    "permission_denied", "disk_full", "memory_error",
}

FORGE_NO_OP_RESULTS = {"no_op", "clean", "no-op", "no_unprocessed_files", "no unprocessed"}
SUMMARY_DERIVED_TYPES = {"failure_keyword", "auth_failure"}
ROUTINE_SIGNAL_TYPES = {"routine", "no_op", "clean"}

SPOT_NO_OP_PHRASES = [
    "all watches inactive", "zero active watches", "all skipped",
    "all deactivated", "no active automatable", "all 4 watch records are inactive",
]

SPOT_SKIP_PHRASES = [
    "skipped", "permanently broken", "dead watch", "expired",
    "no new availability", "already past",
]

FAILURE_STATUSES = {"error", "partial", "completed_with_errors", "scope_failure", "auth_failure"}

NOISE_SIGNAL_TYPES = {
    "", "unknown", "?", "no_op", "forge_activity", "routine", "no_signal",
    "cron_error", "cron_errors", "observation", "success", "mentor_light",
}

_id_counter = int(time.time() * 1000) % 100000


def generate_id(prefix):
    global _id_counter
    _id_counter += 1
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}-{ts}-{_id_counter:04d}"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def append_jsonl(path, records):
    """Append records to a JSONL file. `records` must be a list of dicts.
    
    SAFETY: If a single dict is passed accidentally, wrap it in a list
    instead of iterating over its keys (which would write bare strings).
    """
    if isinstance(records, dict):
        records = [records]
    with open(path, "a") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_journal(fp):
    try:
        with open(fp) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return None
    except (json.JSONDecodeError, OSError):
        return None


def find_all_journals():
    """Walk BOTH journal directories and return (full_path, canonical_id) tuples.

    DUAL-JOURNAL FIX (2026-06-21): Previously only walked JOURNALS_DIR (legacy path),
    missing 8,335 journals in the indigo profile path. Now walks JOURNALS_DIRS.
    Deduplicates by canonical ID to avoid evaluating the same journal twice.
    """
    journals = []
    seen = set()
    for jdir in JOURNALS_DIRS:
        if not os.path.exists(jdir):
            continue
        for root, dirs, files in os.walk(jdir):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fn in files:
                if not fn.endswith(".json"):
                    continue
                fp = os.path.join(root, fn)
                canonical = os.path.relpath(fp, jdir)
                if canonical not in seen:
                    seen.add(canonical)
                    journals.append((fp, canonical))
    return journals


def dedup_eval_file():
    """Deduplicate journals_evaluated.jsonl and return dict of {id: record}."""
    if not os.path.exists(EVAL_FILE):
        return {}
    records = {}
    with open(EVAL_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if isinstance(entry, dict):
                    jid = entry.get("journal_id", "")
                    if jid:
                        records[jid] = entry
                elif isinstance(entry, str) and entry:
                    records[entry] = {"journal_id": entry, "evaluated_at": now_iso()}
            except json.JSONDecodeError:
                pass
    with open(EVAL_FILE, "w") as f:
        for jid, rec in records.items():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return records


def dedup_events_file(new_event_ids):
    """Deduplicate events.jsonl by (source_journal, signal_type). Returns count removed."""
    if not os.path.exists(EVENTS_FILE):
        return 0
    events = load_jsonl(EVENTS_FILE)
    seen = {}
    kept = []
    removed = 0
    for evt in events:
        key = (evt.get("source_journal", ""), evt.get("signal_type", ""))
        if key in seen and evt.get("event_id", "") in new_event_ids:
            removed += 1
            continue
        seen[key] = evt.get("event_id", "")
        kept.append(evt)
    if removed:
        with open(EVENTS_FILE, "w") as f:
            for evt in kept:
                f.write(json.dumps(evt, ensure_ascii=False) + "\n")
    return removed


def determine_domain(canonical_id):
    parts = canonical_id.split("/")
    if parts:
        skill = parts[0]
        if skill and skill not in (".", ""):
            return skill
    return "unknown"


def determine_failure_phase(signals):
    phases = [s.get("phase", "execution") for s in signals if s.get("phase")]
    if not phases:
        return "execution"
    from collections import Counter
    return Counter(phases).most_common(1)[0][0]


def check_disk_space(min_free_gb=1.0):
    try:
        stat = os.statvfs(DATA_DIR)
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        if free_gb < min_free_gb:
            print(f"  WARNING: Low disk space ({free_gb:.1f}GB free). Aborting.")
            return False
        return True
    except OSError:
        return True


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(
        description="praxis_common.py — shared constants, paths, and helpers for Praxis ingest scripts. "
                    "Library module; import from ingest/shift scripts rather than running directly.",
        usage="python3 praxis_common.py [--show-paths]")
    p.add_argument("--show-paths", action="store_true",
                   help="Print the resolved DATA_DIR / JOURNALS_DIRS paths and exit.")
    args = p.parse_args()
    if args.show_paths:
        print("DATA_DIR:", DATA_DIR)
        print("JOURNALS_DIRS:", JOURNALS_DIRS)
        print("EVAL_FILE:", EVAL_FILE)
        print("EVENTS_FILE:", EVENTS_FILE)
    else:
        print("praxis_common is a library module. Use --show-paths to inspect resolved paths, "
              "or import its helpers from another script. Run with -h for details.")
