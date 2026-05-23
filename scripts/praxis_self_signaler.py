#!/usr/bin/env python3
"""
praxis_self_signaler.py — Generate Praxis events from system state.

Scans:
1. Cron job registry for errors, stale runs, and missed schedules
2. Skill journal files for failure/success patterns
3. Session transcripts for user corrections

Outputs JSON lines to stdout, one event per line.
Each event follows the Praxis v3 event schema.

Usage:
  python3 praxis_self_signaler.py [--since-hours 24] [--dry-run]
"""

import json
import os
import sys
import glob
import sqlite3
import subprocess
from datetime import datetime, timezone, timedelta

DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
JOURNALS_DIR = "/root/.hermes/commons/journals"
SESSIONS_DIR = "/root/.hermes/sessions"
NOW = datetime.now(timezone.utc)

# ── Helpers ──────────────────────────────────────────────────────────

def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except:
                        pass
    return rows

def event_id(prefix="self"):
    ts = NOW.strftime("%Y%m%d%H%M%S")
    return f"evt-{prefix}-{ts}"

def make_event(source, category, confidence, severity, context, impact="", domain="system"):
    return {
        "id": event_id(source),
        "timestamp": NOW.isoformat(),
        "source": source,
        "signal_id": None,
        "pattern": "",
        "pattern_category": category,
        "domain": domain,
        "context_summary": context[:200],
        "outcome_summary": context[:300],
        "outcome_type": "observation",
        "confidence": confidence,
        "severity": severity,
        "evidence": [],
        "user_visible_impact": impact
    }

# ── Source 1: Cron job scan ──────────────────────────────────────────

def scan_cron_jobs(since_hours=24):
    """Scan cron job registry for errors and stale runs."""
    events = []
    since = NOW - timedelta(hours=since_hours)
    
    # Try reading the jobs.json file directly
    json_paths = [
        "/root/.hermes/cron/jobs.json",
        os.path.expanduser("~/.hermes/cron/jobs.json"),
    ]
    jobs = []
    for json_path in json_paths:
        if os.path.exists(json_path):
            try:
                with open(json_path) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    jobs = data.get("jobs", data.get("data", []))
                elif isinstance(data, list):
                    jobs = data
                break
            except:
                continue
    
    if not jobs:
        # Fallback: try hermes CLI (no --json flag; parse table output)
        try:
            result = subprocess.run(
                ["hermes", "cron", "list"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                # Try to find JSON in output
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if line.startswith("[") or line.startswith("{"):
                        try:
                            parsed = json.loads(line)
                            if isinstance(parsed, list):
                                jobs = parsed
                            elif isinstance(parsed, dict):
                                jobs = parsed.get("jobs", parsed.get("data", []))
                            break
                        except:
                            continue
        except:
            pass
    
    if not jobs:
        return events
    
    error_jobs = []
    stale_jobs = []
    healthy_count = 0
    
    for job in jobs:
        name = job.get("name", job.get("job_name", "unknown"))
        last_status = job.get("last_status", "")
        last_run = job.get("last_run_at", job.get("last_run", ""))
        next_run = job.get("next_run_at", job.get("next_run", ""))
        enabled = job.get("enabled", True)
        
        if not enabled:
            continue
        
        # Check for errors
        if last_status == "error":
            error_jobs.append(name)
            # Parse last_run time
            try:
                if isinstance(last_run, str):
                    last_run_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                else:
                    last_run_dt = None
            except:
                last_run_dt = None
            
            events.append(make_event(
                source="self",
                category="cron_drift",
                confidence=0.85,
                severity="high",
                context=f"Cron job '{name}' last run failed with status=error. Last run: {last_run}",
                impact=f"Scheduled task '{name}' is not completing successfully.",
                domain="cron"
            ))
        
        # Check for stale runs (no run in 2x expected interval)
        # Heuristic: if next_run is in the past, the job is overdue
        if next_run:
            try:
                if isinstance(next_run, str):
                    next_run_dt = datetime.fromisoformat(next_run.replace("Z", "+00:00"))
                else:
                    next_run_dt = None
                
                if next_run_dt and next_run_dt < NOW - timedelta(hours=2):
                    stale_jobs.append(name)
                    events.append(make_event(
                        source="self",
                        category="execution_stalled",
                        confidence=0.75,
                        severity="medium",
                        context=f"Cron job '{name}' is overdue. Scheduled for {next_run}, now {NOW.isoformat()}",
                        domain="cron"
                    ))
            except:
                pass
    
    if error_jobs:
        events.append(make_event(
            source="self",
            category="cron_drift",
            confidence=0.9,
            severity="high",
            context=f"Batch: {len(error_jobs)} cron jobs with error status: {', '.join(error_jobs[:5])}",
            domain="cron"
        ))
    
    return events

# ── Source 2: Skill journal scan ─────────────────────────────────────

def scan_skill_journals(since_hours=24):
    """Scan skill journal files for failure/success patterns."""
    events = []
    since = NOW - timedelta(hours=since_hours)
    
    if not os.path.isdir(JOURNALS_DIR):
        return events
    
    for skill_name in sorted(os.listdir(JOURNALS_DIR)):
        skill_dir = os.path.join(JOURNALS_DIR, skill_name)
        if not os.path.isdir(skill_dir):
            continue
        
        # Find recent journal entries
        recent_failures = []
        recent_successes = []
        
        for date_dir in sorted(os.listdir(skill_dir), reverse=True)[:3]:
            date_path = os.path.join(skill_dir, date_dir)
            if not os.path.isdir(date_path):
                continue
            
            for jfile in sorted(os.listdir(date_path), reverse=True)[:20]:
                if not jfile.endswith(".json"):
                    continue
                jpath = os.path.join(date_path, jfile)
                
                try:
                    with open(jpath) as f:
                        journal = json.load(f)
                except:
                    continue
                
                # Check file mtime
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(jpath), tz=timezone.utc)
                    if mtime < since:
                        continue
                except:
                    continue
                
                # Look for failure indicators — check multiple schema variants
                decision = journal.get("decision", {})
                metrics = journal.get("metrics", {})
                okr = journal.get("okr_evaluation", {})
                stats = journal.get("stats", {})
                summary = journal.get("summary", "")
                
                # Merge stats into metrics for unified checking
                if stats and not metrics:
                    metrics = stats
                
                # High failure count
                validation_failures = metrics.get("validation_failures", 0)
                records_failed = metrics.get("records_failed", 0)
                retry_count = metrics.get("retry_count", 0)
                errors = metrics.get("errors", 0)
                failed = metrics.get("failed", 0)
                
                # Check summary for failure keywords
                summary_lower = str(summary).lower()
                has_failure_keywords = any(kw in summary_lower for kw in [
                    "fail", "error", "blocked", "stalled", "timeout", "exception",
                    "crash", "broken", "unavailable", "denied", "refused"
                ])
                
                if validation_failures > 2 or records_failed > 2 or errors > 2 or failed > 2 or has_failure_keywords:
                    recent_failures.append({
                        "skill": skill_name,
                        "file": jfile,
                        "validation_failures": validation_failures,
                        "records_failed": records_failed,
                        "errors": errors,
                        "context": str(decision.get("reasoning_summary", decision.get("payload", {}).get("action", summary)))[:100]
                    })
                
                # Low OKR scores
                success_rate = okr.get("success_rate", None)
                if success_rate is None:
                    success_rate = metrics.get("success_rate", stats.get("success_rate", None))
                if success_rate is not None and success_rate < 0.5:
                    recent_failures.append({
                        "skill": skill_name,
                        "file": jfile,
                        "success_rate": success_rate,
                        "context": f"OKR success_rate={success_rate}"
                    })
                
                # High success
                if success_rate is not None and success_rate >= 0.95:
                    recent_successes.append({
                        "skill": skill_name,
                        "file": jfile,
                        "success_rate": success_rate
                    })
        
        # Generate events for patterns
        if len(recent_failures) >= 2:
            events.append(make_event(
                source="self",
                category="skill_dormancy" if "dormant" in str(recent_failures) else "execution_stalled",
                confidence=0.8,
                severity="medium",
                context=f"Skill '{skill_name}' has {len(recent_failures)} recent journal entries with failures. Latest: {recent_failures[0].get('context', 'N/A')[:100]}",
                domain=skill_name
            ))
        
        if len(recent_successes) >= 3:
            events.append(make_event(
                source="self",
                category="quality_improvement",
                confidence=0.85,
                severity="low",
                context=f"Skill '{skill_name}' has {len(recent_successes)} high-success journal entries (success_rate>=0.95)",
                domain=skill_name
            ))
    
    return events

# ── Source 3: Session transcript scan ────────────────────────────────

def scan_session_transcripts(since_hours=24):
    """Scan recent session transcripts for user corrections and failures."""
    events = []
    since = NOW - timedelta(hours=since_hours)
    
    # Look for session files
    session_paths = [
        os.path.expanduser("~/.hermes/sessions"),
        "/root/.hermes/sessions",
        os.path.expanduser("~/.hermes/data/sessions"),
    ]
    
    sessions_dir = None
    for sp in session_paths:
        if os.path.isdir(sp):
            sessions_dir = sp
            break
    
    if not sessions_dir:
        return events
    
    # Find recent session files
    recent_files = []
    for ext in [".json", ".jsonl", ".txt"]:
        pattern = os.path.join(sessions_dir, f"*{ext}")
        for fpath in glob.glob(pattern):
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath), tz=timezone.utc)
                if mtime >= since:
                    recent_files.append((mtime, fpath))
            except:
                pass
    
    # Also check subdirectories
    for subdir in glob.glob(os.path.join(sessions_dir, "*")):
        if os.path.isdir(subdir):
            for ext in [".json", ".jsonl"]:
                pattern = os.path.join(subdir, f"*{ext}")
                for fpath in glob.glob(pattern):
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(fpath), tz=timezone.utc)
                        if mtime >= since:
                            recent_files.append((mtime, fpath))
                    except:
                        pass
    
    recent_files.sort(reverse=True)
    
    correction_keywords = [
        "wrong", "incorrect", "don't do that", "stop", "never", "always",
        "you should", "you need to", "fix this", "that's not right",
        "actually", "no,", "wrong,", "incorrect,", "not correct",
        "hallucinat", "fabricat", "bullshit", "nonsense",
    ]
    
    corrections_found = []
    
    for mtime, fpath in recent_files[:30]:
        try:
            with open(fpath, errors="replace") as f:
                content = f.read(5000)  # First 5KB
            
            content_lower = content.lower()
            for keyword in correction_keywords:
                if keyword in content_lower:
                    # Extract context around the keyword
                    idx = content_lower.find(keyword)
                    start = max(0, idx - 50)
                    end = min(len(content), idx + 100)
                    context = content[start:end].strip()
                    
                    corrections_found.append({
                        "file": os.path.basename(fpath),
                        "keyword": keyword,
                        "context": context[:150]
                    })
                    break  # One event per file
        except:
            continue
    
    if corrections_found:
        events.append(make_event(
            source="self",
            category="user_correction",
            confidence=0.85,
            severity="high",
            context=f"Detected {len(corrections_found)} potential user corrections in recent sessions. Latest: '{corrections_found[0]['context'][:80]}'",
            impact="User expressed dissatisfaction with agent behavior.",
            domain="user_interaction"
        ))
    
    return events

# ── Main ─────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Praxis self-signaler")
    parser.add_argument("--since-hours", type=int, default=24)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", choices=["cron", "journals", "sessions", "all"], default="all")
    args = parser.parse_args()
    
    all_events = []
    
    if args.source in ("cron", "all"):
        all_events.extend(scan_cron_jobs(args.since_hours))
    
    if args.source in ("journals", "all"):
        all_events.extend(scan_skill_journals(args.since_hours))
    
    if args.source in ("sessions", "all"):
        all_events.extend(scan_session_transcripts(args.since_hours))
    
    # Deduplicate by context_summary
    seen = set()
    unique = []
    for ev in all_events:
        key = ev["context_summary"][:100]
        if key not in seen:
            seen.add(key)
            unique.append(ev)
    
    if args.dry_run:
        print(f"[DRY RUN] Would generate {len(unique)} events:")
        for ev in unique:
            print(f"  {ev['id']}: {ev['pattern_category']} conf={ev['confidence']} — {ev['context_summary'][:80]}")
    else:
        for ev in unique:
            print(json.dumps(ev))
    
    return len(unique)

if __name__ == "__main__":
    count = main()
    sys.exit(0 if count >= 0 else 1)
