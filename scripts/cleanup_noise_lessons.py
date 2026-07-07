#!/usr/bin/env python3
"""
Noise lesson cleanup for Praxis behavioral refinement loop.

Removes noise lessons from lessons.jsonl based on Bug 2 criteria:

1. confidence: "low"
2. signal_type is "?", "", "null", "none", or MISSING entirely
3. Fast pre-filter: if ALL events from the current run are no_signal,
   ALL co-produced lessons are noise regardless of individual fields.

Usage:
  python3 cleanup_noise_lessons.py                    # Default: prompt for events file
  python3 cleanup_noise_lessons.py --all-no-signal    # Skip event check, apply fast pre-filter
  python3 cleanup_noise_lessons.py --events events.jsonl  # Specify events file path

ARCHIVE BEHAVIOR (fixed 2026-07-07): every fast-path and the per-lesson path
archive removed lessons to lessons_noise_archive_<UTC_DATE>.jsonl BEFORE
clearing lessons.jsonl, preserving the audit trail required by the Bug 2
cleanup procedure. The durable store is shifts.jsonl; the archive enables
post-hoc inspection of what was cleared.
"""
import json
import os
import sys
import datetime

# Default paths relative to script location
# Script is at {profile_root}/skills/ocas-praxis/scripts/cleanup_noise_lessons.py
# So ../../.. goes scripts -> ocas-praxis -> skills -> profile_root
# DO NOT change to ../.. — that lands at {profile_root}/skills/ (one level too shallow)
ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
COMMONS = os.path.join(ROOT, "commons", "data", "ocas-praxis")
LESSONS_FILE = os.path.join(COMMONS, "lessons.jsonl")
EVENTS_FILE = os.path.join(COMMONS, "events.jsonl")

# Noise signal types — lessons with these signal_types are removed
NOISE_SIGNAL_TYPES = {
    "", "unknown", "?", "no_op", "forge_activity", "routine",
    "no_signal", "cron_error", "cron_errors", "observation", "success",
    "mentor_light", "correction", "low_coverage", "gap_detected",
    "mixed_genuine_no_op", "none", "null"
}

# Bug 2 noise lesson check — matches any of these criteria
def is_bug2_noise(lesson):
    # Criterion A: signal_type key missing entirely
    st = lesson.get("signal_type")
    if st is None:
        return True  # key missing = Bug 2 noise (Pass 2 didn't add it)

    # Criterion B: signal_type in noise set
    st_str = str(st).strip().lower()
    if st_str in NOISE_SIGNAL_TYPES:
        return True

    # Criterion C: confidence low
    if lesson.get("confidence") == "low":
        return True

    return False


def load_jsonl(path):
    """Load all entries from a JSONL file."""
    entries = []
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return entries
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"  Warning: skipping unparseable line in {path}")
    return entries


def write_jsonl(path, entries):
    """Write entries to a JSONL file (overwrite)."""
    with open(path, 'w') as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def archive_lessons(lessons):
    """Archive removed lessons to lessons_noise_archive_<UTC_DATE>.jsonl.

    Preserves the Bug 2 cleanup audit trail. The durable behavioral store is
    shifts.jsonl; lessons are re-derived every run (Bug 2 full-history
    reprocessing), so archiving lets a future session inspect what was cleared
    without re-running the production script. No-op if lessons is empty.
    """
    if not lessons:
        return 0
    arch_path = os.path.join(
        COMMONS, "lessons_noise_archive_" + datetime.date.today().isoformat() + ".jsonl"
    )
    n = 0
    with open(arch_path, 'a') as f:
        for les in lessons:
            f.write(json.dumps(les, ensure_ascii=False) + '\n')
            n += 1
    print(f"  Archived {n} lessons to {arch_path}")
    return n


def check_fast_prefilter(events_file, args):
    """Fast pre-filter: if ALL events in the file are no_signal, return True."""
    if '--all-no-signal' in args:
        return True
    if not os.path.exists(events_file):
        return False

    events = load_jsonl(events_file)
    if not events:
        return False

    all_no_signal = True
    for evt in events:
        st = evt.get("signal_type", "")
        if str(st).strip().lower() not in ("no_signal", "", "?", "none", "null"):
            all_no_signal = False
            break

    return all_no_signal


def main():
    args = sys.argv[1:]
    events_file = EVENTS_FILE

    # Parse --events flag
    if '--events' in args:
        idx = args.index('--events')
        if idx + 1 < len(args):
            events_file = args[idx + 1]

    # Step 1: Check fast pre-filter
    fast_pf = check_fast_prefilter(events_file, args)
    if fast_pf:
        print("[Fast pre-filter] ALL events are no_signal — removing ALL lessons")
        lessons = load_jsonl(LESSONS_FILE)
        kept = []
        removed = lessons  # all are noise in this path
        print(f"  Removed: {len(removed)} lessons (all are Bug 2 noise)")
        print(f"  Kept: {len(kept)} lessons")
        archive_lessons(removed)
        write_jsonl(LESSONS_FILE, kept)
        print(f"  lessons.jsonl now empty")
        return

    # Step 1b: Single-genuine-event fast-path (Bug 2 noise, 2026-07-07)
    # When the run records exactly 1 genuine (non-no_signal) event, the
    # all-no_signal pre-filter does NOT fire, yet every extracted lesson is
    # still Bug 2 full-history noise (a single new event cannot ground a
    # >=2-instance lesson). Pass --new-genuine-events N (N = genuine events
    # recorded this run); if N < 2, clear all lessons.
    if '--new-genuine-events' in args:
        try:
            _i = args.index('--new-genuine-events')
            _n_ge = int(args[_i + 1])
        except (IndexError, ValueError):
            _n_ge = 0
        if _n_ge < 2:
            _lessons = load_jsonl(LESSONS_FILE)
            _n_lessons = len(_lessons)
            print(f"[Single-genuine fast-path] {_n_ge} genuine new event(s) < 2 "
                  f"— all {_n_lessons} lessons are Bug 2 noise")
            archive_lessons(_lessons)
            write_jsonl(LESSONS_FILE, [])
            print(f"  lessons.jsonl now empty")
            return

    # Step 2: Per-lesson inspection
    lessons = load_jsonl(LESSONS_FILE)
    if not lessons:
        print("lessons.jsonl is empty — nothing to clean")
        return

    kept = []
    removed = []
    for les in lessons:
        if is_bug2_noise(les):
            removed.append(les)
        else:
            kept.append(les)

    print(f"  Total lessons inspected: {len(lessons)}")
    print(f"  Removed (Bug 2 noise):  {len(removed)}")
    print(f"  Kept:                   {len(kept)}")

    if removed:
        archive_lessons(removed)
        write_jsonl(LESSONS_FILE, kept)
        print(f"  lessons.jsonl overwritten with {len(kept)} lessons")

    # Summary of removal reasons
    if removed:
        reasons = {"missing_signal_type": 0, "confidence_low": 0, "noise_signal_type": 0}
        for les in removed:
            if les.get("signal_type") is None:
                reasons["missing_signal_type"] += 1
            elif les.get("confidence") == "low":
                reasons["confidence_low"] += 1
            else:
                reasons["noise_signal_type"] += 1
        print(f"  Breakdown: missing_signal_type={reasons['missing_signal_type']}, "
              f"confidence_low={reasons['confidence_low']}, "
              f"noise_signal_type={reasons['noise_signal_type']}")


if __name__ == '__main__':
    main()
