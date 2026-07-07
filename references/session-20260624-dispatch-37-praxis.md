# Dispatch #37 — 2026-06-24T02:22Z (Multi-skill: Forge + Mentor + Praxis)

**Trigger:** Dispatcher detected 1 new journal (`ocas-mentor/2026-06-24/mentor-light-20260624T021135Z.json`).

**Phase 1 — Forge:** CLEAN (28 processed, 0 unprocessed). No-op journal written.

**Phase 2 — Mentor:**
- 4,315 files scanned (dual-path), 1 new ingested
- Evidence: 4465→4467 (+1 script +1 correction)
- Ingestion: 28316→28317 (+1)
- `active_skills_30d` corrected: 11→22 (OCAS: 18)
- All 3 script writes succeeded — no backup needed

**Phase 3 — Praxis:**
- 4 journals evaluated via mtime-based discovery (1 mentor-light no-signal, 1 custodian light-scan, 1 praxis cron-ingest, 1 mentor-light from this dispatch)
- 1 event recorded (custodian light-scan signal)
- Third-wave mitigation: applied (2 dispatch-output journals added to eval, state advanced)
- Gap backfill: 0 (all journals within expected window)

**Pitfall: Inline script bypassed template**
- The agent wrote a ~150-line inline Python script (`/tmp/praxis_dispatch_ingest.py`) instead of using the production `templates/dispatch_ingest_template.py`
- Root cause: The template requires `CAPTURED_TS` env var for cross-pipeline timing, which wasn't obvious from the main SKILL.md body
- Fix: When triggered by dispatcher with multi-skill dispatch, ALWAYS use the template with `CAPTURED_TS=<pre-Mentor-timestamp>`. The template already implements all noise filters, mtime-based discovery, and mixed-format eval handling
- The inline script worked but duplicated ~150 lines of logic that already exists in the template

**Notes:**
- Dispatcher's `new_files` (`mentor-light-20260624T021135Z.json`) was already ingested by the Mentor heartbeat script — correctly skipped in mtime-based discovery
- All pipelines clean, queue cleared
