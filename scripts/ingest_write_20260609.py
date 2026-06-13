#!/usr/bin/env python3
"""Write eval updates for 3 unevaluated journals and Praxis journal entry."""
import json
import os
from datetime import datetime, timezone

EVAL_FILE = "/root/.hermes/commons/data/ocas-praxis/journals_evaluated.jsonl"
JOURNAL_DIR = "/root/.hermes/commons/journals/ocas-praxis/2026-06-09"
now = datetime.now(timezone.utc).isoformat()

# Eval updates for 3 unevaluated journals
eval_updates = [
    {
        "journal_id": "ocas-forge/2026-06-09/r_20260609_journal-scan-1780991879.json",
        "evaluated_at": now,
        "action_taken": "no_signal",
        "signals_found": [],
        "reason": "Routine forge journal scan: no_new_proposals, 0 unprocessed files, no actions taken"
    },
    {
        "journal_id": "ocas-spot/2026-06-09/sweep-20260609011636.json",
        "evaluated_at": now,
        "action_taken": "no_signal",
        "signals_found": [],
        "reason": "Spot sweep: known platform failure pattern (Meevo 50+, Vagaro 60+ consecutive failures). Russamee no_change. All signals are known tracked patterns, no new behavioral signal."
    },
    {
        "journal_id": "ocas-spot/2026-06-09/spot-20260609-005150.json",
        "evaluated_at": now,
        "action_taken": "no_signal",
        "signals_found": [],
        "reason": "Spot sweep: known platform failure pattern (Meevo 50+, Vagaro 60+ consecutive failures). Russamee no_change. All signals are known tracked patterns, no new behavioral signal."
    }
]

# Append eval updates
with open(EVAL_FILE, 'a') as f:
    for entry in eval_updates:
        f.write(json.dumps(entry) + "\n")

print(f"Wrote {len(eval_updates)} eval updates")

# Write Praxis journal entry
os.makedirs(JOURNAL_DIR, exist_ok=True)
run_id = f"r_20260609_praxis_ingest_{datetime.now(timezone.utc).strftime('%H%M%S')}"
journal_path = os.path.join(JOURNAL_DIR, f"{run_id}.json")

journal_entry = {
    "journal_spec_version": "1.3",
    "run_identity": {
        "run_id": run_id,
        "journal_type": "Action",
        "skill": "ocas-praxis",
        "skill_version": "3.2.0",
        "started_at": now,
        "completed_at": now
    },
    "command": "praxis.journal_ingest",
    "journals_scanned": 142,
    "unevaluated_found": 3,
    "events_recorded": 0,
    "lessons_extracted": 0,
    "shifts_proposed": 0,
    "shifts_activated": 0,
    "eval_updates_written": 3,
    "summary": "Ingest scan: 142 journal files for 2026-06-09 + 2026-06-08. 3 unevaluated (all ocas-forge/ocas-spot routine sweeps). 0 new events — all signals are known tracked patterns. 0 lessons extracted. No shift changes.",
    "not_activity_reason": "No new behavioral signals detected in unevaluated journals"
}

with open(journal_path, 'w') as f:
    json.dump(journal_entry, f, indent=2)

print(f"Wrote Praxis journal: {journal_path}")
print("Done.")
