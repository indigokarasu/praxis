#!/usr/bin/env python3
"""
praxis_review.py — Full Praxis review pass (v3.0).

This script:
1. Runs the self-signaler to generate events from system state
2. Processes any unprocessed Corvus signals
3. Extracts lessons using tiered thresholds
4. Proposes and activates shifts
5. Expires stale shifts
6. Generates debriefs
7. Outputs a summary report

Usage:
  python3 praxis_review.py [--dry-run] [--since-hours 24]
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta

DATA_DIR = "/root/.hermes/commons/data/ocas-praxis"
SIGNALS_DIR = "/root/.hermes/commons/data/ocas-corvus/signals"
JOURNALS_DIR = "/root/.hermes/commons/journals/ocas-praxis"
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

def append_jsonl(path, row):
    with open(path, "a") as f:
        f.write(json.dumps(row) + "\n")

def count_jsonl(path):
    return len(load_jsonl(path))

# ── Step 1: Self-signal generation ───────────────────────────────────

def run_self_signaler(since_hours, dry_run=False):
    """Run the self-signaler script and ingest its output."""
    script = "/root/.hermes/scripts/praxis_self_signaler.py"
    if not os.path.exists(script):
        print(f"  [WARN] Self-signaler not found at {script}")
        return []
    
    cmd = [sys.executable, script, "--since-hours", str(since_hours)]
    # NOTE: do NOT pass --dry-run here — we need JSON output to ingest events.
    # The dry_run flag is handled at the review script level (steps 3-6).
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    
    if result.returncode != 0:
        print(f"  [ERROR] Self-signaler failed: {result.stderr[:200]}")
        return []
    
    events = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("["):
            continue
        try:
            ev = json.loads(line)
            events.append(ev)
        except:
            pass
    
    return events

# ── Step 2: Corvus signal processing ────────────────────────────────

def assign_category(desc, target="", subtype=""):
    combined = (desc + " " + target).lower()
    
    subtype_map = {
        "config_drift": "config_blocked",
        "auth_cascade_failure": "auth_failure",
        "execution_blocked": "config_blocked",
        "system_health": "skill_dormancy",
    }
    if subtype in subtype_map:
        return subtype_map[subtype]
    
    if any(w in combined for w in ["hallucinat", "fabricat", "bullshit", "content accuracy"]):
        return "content_accuracy"
    if any(w in combined for w in ["bypass", "safety", "restriction"]):
        return "safety_bypass"
    if any(w in combined for w in ["timezone", "tz-", "time zone", "pacific", "utc"]):
        return "timezone_handling"
    if any(w in combined for w in ["auth", "credential", "token", "401", "403", "oauth"]):
        return "auth_failure"
    if any(w in combined for w in ["blocked", "stalled", "pending", "restart"]):
        return "execution_stalled"
    if any(w in combined for w in ["config", "zombie", "unused", "nvidia", "provider"]):
        return "zombie_config"
    if any(w in combined for w in ["dormant", "gap", "not running", "inactive"]):
        return "skill_dormancy"
    if any(w in combined for w in ["cron", "drift", "schedule", "every minute"]):
        return "cron_drift"
    if any(w in combined for w in ["degrad", "rate limit", "429", "free tier", "pivot"]):
        return "adaptive_degradation"
    if any(w in combined for w in ["improv", "resolv", "reduced", "faster", "optimized"]):
        return "quality_improvement"
    return ""

def process_corvus_signals(evaluated_ids):
    """Process unprocessed Corvus signals into events."""
    if not os.path.isdir(SIGNALS_DIR):
        return []
    
    new_events = []
    for fname in sorted(os.listdir(SIGNALS_DIR)):
        if not fname.endswith(".json"):
            continue
        
        fpath = os.path.join(SIGNALS_DIR, fname)
        try:
            with open(fpath) as f:
                sig = json.loads(f.read())
        except:
            continue
        
        sid = sig.get("signal_id", "")
        if not sid or sid in evaluated_ids:
            continue
        
        desc = sig.get("description", sig.get("content", "No description"))
        target = sig.get("target_region", sig.get("target_skill", ""))
        subtype = sig.get("signal_subtype", "")
        category = assign_category(desc, target, subtype)
        
        conf = sig.get("confidence_score", sig.get("confidence", 0.5))
        sev = sig.get("severity", sig.get("priority_score", "medium"))
        if isinstance(sev, (int, float)):
            sev = "high" if sev >= 0.85 else ("medium" if sev >= 0.6 else "low")
        
        event = {
            "id": f"evt-sig-{sid[:25]}",
            "timestamp": sig.get("timestamp", NOW.isoformat()),
            "source": "ocas-corvus",
            "signal_id": sid,
            "pattern": sig.get("pattern", ""),
            "pattern_category": category,
            "domain": target or "system",
            "context_summary": desc[:200],
            "outcome_summary": desc[:300],
            "outcome_type": "observation",
            "confidence": conf,
            "severity": sev,
            "evidence": [fname],
            "user_visible_impact": ""
        }
        new_events.append(event)
        evaluated_ids.add(sid)
    
    return new_events

# ── Step 3: Lesson extraction ───────────────────────────────────────

def extract_lessons(all_events, existing_lessons):
    """Extract lessons using tiered thresholds."""
    new_lessons = []
    existing_categories = {l.get("pattern_category", "") for l in existing_lessons}
    
    # Cluster by category
    category_events = {}
    for ev in all_events:
        cat = ev.get("pattern_category", "")
        if cat:
            category_events.setdefault(cat, []).append(ev)
    
    lesson_counter = len(existing_lessons) + 1
    
    # Tier 1: High-confidence single events (>= 0.9, high severity)
    for ev in all_events:
        conf = ev.get("confidence", 0)
        sev = ev.get("severity", "")
        cat = ev.get("pattern_category", "")
        
        if conf >= 0.9 and sev == "high" and cat not in existing_categories:
            lesson = {
                "id": f"lsn-{lesson_counter:04d}",
                "event_ids": [ev["id"]],
                "lesson_text": f"High-confidence event: {ev['context_summary'][:150]}",
                "confidence": "high",
                "scope": cat or "system",
                "pattern_category": cat,
                "status": "accepted",
                "created_at": NOW.isoformat(),
                "activation_threshold_met": "high_confidence"
            }
            new_lessons.append(lesson)
            existing_categories.add(cat)
            lesson_counter += 1
    
    # Tier 2: User corrections (conf >= 0.85)
    for ev in all_events:
        cat = ev.get("pattern_category", "")
        conf = ev.get("confidence", 0)
        
        if cat == "user_correction" and conf >= 0.85 and cat not in existing_categories:
            lesson = {
                "id": f"lsn-{lesson_counter:04d}",
                "event_ids": [ev["id"]],
                "lesson_text": f"User correction: {ev['context_summary'][:150]}",
                "confidence": "high",
                "scope": "user_interaction",
                "pattern_category": cat,
                "status": "accepted",
                "created_at": NOW.isoformat(),
                "activation_threshold_met": "user_correction"
            }
            new_lessons.append(lesson)
            existing_categories.add(cat)
            lesson_counter += 1
    
    # Tier 3: Pattern categories with 2+ events
    for cat, evts in category_events.items():
        if cat in existing_categories:
            continue
        if len(evts) >= 2:
            event_ids = [e["id"] for e in evts]
            descriptions = [e.get("context_summary", "")[:80] for e in evts[:3]]
            
            lesson = {
                "id": f"lsn-{lesson_counter:04d}",
                "event_ids": event_ids,
                "lesson_text": f"Pattern in '{cat}' ({len(evts)} events): {'; '.join(descriptions)}",
                "confidence": "high" if len(evts) >= 3 else "medium",
                "scope": cat,
                "pattern_category": cat,
                "status": "accepted",
                "created_at": NOW.isoformat(),
                "activation_threshold_met": "pattern_count"
            }
            new_lessons.append(lesson)
            existing_categories.add(cat)
            lesson_counter += 1
    
    return new_lessons

# ── Step 4: Shift activation ────────────────────────────────────────

def lesson_to_shift(lesson, shift_counter):
    """Convert a lesson to a behavior shift."""
    cat = lesson.get("pattern_category", "")
    conf = lesson.get("confidence", "medium")
    
    if cat == "user_correction":
        priority = 10
    elif cat in ("content_accuracy", "safety_bypass"):
        priority = 9
    elif conf == "high":
        priority = 8
    elif conf == "medium":
        priority = 6
    else:
        priority = 4
    
    templates = {
        "content_accuracy": "Never fabricate content in briefings or emails. If data is unavailable, say so explicitly.",
        "timezone_handling": "Always display times in America/Los_Angeles (Pacific) unless user explicitly requests otherwise.",
        "execution_stalled": "When work is blocked by an external dependency, surface the blocker to the user in the same session.",
        "auth_failure": "On auth failure, report immediately and stop retrying.",
        "config_blocked": "When config blocks execution, report the specific blocker and suggest a fix.",
        "cron_drift": "Flag cron drift in review passes and suggest schedule corrections.",
        "adaptive_degradation": "When in degraded mode, inform the user what capabilities are reduced.",
        "zombie_config": "Remove or disable unused config entries that cause failures.",
        "skill_dormancy": "Flag skills with 7+ days of no output in review passes.",
        "safety_bypass": "Never bypass tool-level restrictions. Log and report any bypass attempt.",
        "quality_improvement": "Document before/after metrics when performance improvements are achieved.",
        "user_correction": lesson["lesson_text"][:150],
    }
    
    shift_text = templates.get(cat, f"Address '{cat}': {lesson['lesson_text'][:120]}")
    
    return {
        "id": f"shf-{shift_counter:04d}",
        "source_lesson_ids": [lesson["id"]],
        "shift_text": shift_text,
        "status": "active",
        "priority": priority,
        "pattern_category": cat,
        "activation_reason": f"Auto-activated: {lesson['activation_threshold_met']}",
        "created_at": NOW.isoformat(),
        "activated_at": NOW.isoformat(),
        "last_reviewed_at": NOW.isoformat(),
        "last_reinforced_at": NOW.isoformat(),
        "expiry_condition": None,
        "expired_at": None
    }

def activate_shifts(new_lessons, existing_shifts, dry_run=False):
    """Propose and activate shifts from new lessons."""
    active_shifts = [s for s in existing_shifts if s.get("status") == "active"]
    new_shifts = []
    shift_counter = len(existing_shifts) + 1
    
    for lesson in new_lessons:
        if len(active_shifts) + len(new_shifts) < 12:
            shift = lesson_to_shift(lesson, shift_counter)
            shift_counter += 1
            new_shifts.append(shift)
            active_shifts.append(shift)
        else:
            # At cap — check if we can replace a lower-priority shift
            lowest = min(active_shifts, key=lambda s: s.get("priority", 0))
            new_priority = 10 if lesson.get("pattern_category") == "user_correction" else (
                8 if lesson.get("confidence") == "high" else 6
            )
            if new_priority > lowest.get("priority", 0):
                lowest["status"] = "expired"
                lowest["expiry_condition"] = "replaced by higher-priority shift"
                lowest["expired_at"] = NOW.isoformat()
                active_shifts.remove(lowest)
                
                shift = lesson_to_shift(lesson, shift_counter)
                shift_counter += 1
                new_shifts.append(shift)
                active_shifts.append(shift)
    
    return new_shifts

# ── Step 5: Stale shift expiry ───────────────────────────────────────

def expire_stale_shifts(shifts):
    """Expire shifts with no reinforcement in 14 days."""
    expired = []
    for shift in shifts:
        if shift.get("status") != "active":
            continue
        
        last_reinforced = shift.get("last_reinforced_at", shift.get("activated_at", ""))
        if last_reinforced:
            try:
                reinforced_dt = datetime.fromisoformat(last_reinforced.replace("Z", "+00:00"))
                if reinforced_dt < NOW - timedelta(days=14):
                    shift["status"] = "expired"
                    shift["expiry_condition"] = "stale: no reinforcement"
                    shift["expired_at"] = NOW.isoformat()
                    expired.append(shift["id"])
            except:
                pass
    
    return expired

# ── Step 6: Debrief generation ──────────────────────────────────────

def generate_debrief(new_events, new_lessons, new_shifts, expired_shifts, all_events, all_lessons, all_shifts):
    """Generate a debrief if material changes occurred."""
    if not new_shifts and not expired_shifts and len(new_lessons) < 3:
        return None
    
    active_count = len([s for s in all_shifts if s.get("status") == "active"])
    
    return {
        "id": f"dbf-{NOW.strftime('%Y%m%d%H%M%S')}",
        "timestamp": NOW.isoformat(),
        "related_event_ids": [e["id"] for e in new_events],
        "related_lesson_ids": [l["id"] for l in new_lessons],
        "related_shift_ids": [s["id"] for s in new_shifts],
        "summary": f"Praxis review: {len(new_events)} new events, {len(new_lessons)} lessons, {len(new_shifts)} shifts activated, {len(expired_shifts)} expired. Active: {active_count}/12.",
        "accepted_changes": [s["shift_text"] for s in new_shifts],
        "rejected_changes": [],
        "expired_shifts": expired_shifts,
        "open_questions": [],
        "generated_at": NOW.isoformat(),
        "trigger": "batch_review"
    }

# ── Main ─────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Praxis v3.0 review pass")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--since-hours", type=int, default=24)
    args = parser.parse_args()
    
    print(f"=== Praxis v3.0 Review Pass ===")
    print(f"Time: {NOW.isoformat()}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()
    
    # Load current state
    events = load_jsonl(os.path.join(DATA_DIR, "events.jsonl"))
    lessons = load_jsonl(os.path.join(DATA_DIR, "lessons.jsonl"))
    shifts = load_jsonl(os.path.join(DATA_DIR, "shifts.jsonl"))
    debriefs = load_jsonl(os.path.join(DATA_DIR, "debriefs.jsonl"))
    evaluated = load_jsonl(os.path.join(DATA_DIR, "signals_evaluated.jsonl"))
    evaluated_ids = {e["signal_id"] for e in evaluated}
    
    print(f"Starting state: {len(events)} events, {len(lessons)} lessons, {len(shifts)} shifts ({len([s for s in shifts if s.get('status')=='active'])} active), {len(debriefs)} debriefs")
    print()
    
    # Step 1: Self-signal generation
    print("Step 1: Running self-signaler...")
    self_events = run_self_signaler(args.since_hours, args.dry_run)
    print(f"  Generated {len(self_events)} self-signals")
    
    # Step 2: Corvus signal processing
    print("Step 2: Processing Corvus signals...")
    corvus_events = process_corvus_signals(evaluated_ids)
    print(f"  Processed {len(corvus_events)} new Corvus signals")
    
    all_new_events = self_events + corvus_events
    
    if not args.dry_run and all_new_events:
        for ev in all_new_events:
            append_jsonl(os.path.join(DATA_DIR, "events.jsonl"), ev)
        for ev in corvus_events:
            if ev.get("signal_id"):
                append_jsonl(os.path.join(DATA_DIR, "signals_evaluated.jsonl"), {
                    "signal_id": ev["signal_id"],
                    "evaluated_at": NOW.isoformat()
                })
        events.extend(all_new_events)
    
    # Step 3: Lesson extraction
    print("Step 3: Extracting lessons...")
    new_lessons = extract_lessons(events, lessons)
    print(f"  Extracted {len(new_lessons)} new lessons")
    
    if not args.dry_run and new_lessons:
        for lsn in new_lessons:
            append_jsonl(os.path.join(DATA_DIR, "lessons.jsonl"), lsn)
        lessons.extend(new_lessons)
    
    # Step 4: Shift activation
    print("Step 4: Activating shifts...")
    new_shifts = activate_shifts(new_lessons, shifts, args.dry_run)
    print(f"  Activated {len(new_shifts)} new shifts")
    
    if not args.dry_run and new_shifts:
        for shf in new_shifts:
            append_jsonl(os.path.join(DATA_DIR, "shifts.jsonl"), shf)
        shifts.extend(new_shifts)
    
    # Step 5: Stale shift expiry
    print("Step 5: Expiring stale shifts...")
    expired = expire_stale_shifts(shifts)
    print(f"  Expired {len(expired)} stale shifts: {expired}")
    
    # Step 6: Debrief generation
    print("Step 6: Generating debrief...")
    debrief = generate_debrief(all_new_events, new_lessons, new_shifts, expired, events, lessons, shifts)
    
    if debrief and not args.dry_run:
        append_jsonl(os.path.join(DATA_DIR, "debriefs.jsonl"), debrief)
        print(f"  Debrief: {debrief['id']}")
    elif debrief:
        print(f"  [DRY RUN] Would generate debrief: {debrief['id']}")
    else:
        print("  No material changes — no debrief needed")
    
    # Step 7: Decision log
    decision = {
        "timestamp": NOW.isoformat(),
        "decision_type": "review_complete",
        "context": "praxis.review v3.0",
        "reasoning": f"Processed {len(all_new_events)} events ({len(self_events)} self, {len(corvus_events)} corvus), extracted {len(new_lessons)} lessons, activated {len(new_shifts)} shifts, expired {len(expired)}.",
        "outcome": f"events={len(events)}, lessons={len(lessons)}, active_shifts={len([s for s in shifts if s.get('status')=='active'])}/12",
        "entities_observed": [],
        "relationships_observed": [],
        "preferences_observed": []
    }
    
    if not args.dry_run:
        append_jsonl(os.path.join(DATA_DIR, "decisions.jsonl"), decision)
    
    # Summary
    active_count = len([s for s in shifts if s.get("status") == "active"])
    print()
    print(f"=== SUMMARY ===")
    print(f"Events: {len(events)} total (+{len(all_new_events)} new)")
    print(f"Lessons: {len(lessons)} total (+{len(new_lessons)} new)")
    print(f"Shifts: {active_count}/12 active (+{len(new_shifts)} new, {len(expired)} expired)")
    print(f"Debriefs: {len(debriefs) + (1 if debrief else 0)} total")
    
    if new_shifts:
        print(f"\nNew active shifts:")
        for s in new_shifts:
            print(f"  [P{s['priority']}] {s['shift_text'][:80]}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
