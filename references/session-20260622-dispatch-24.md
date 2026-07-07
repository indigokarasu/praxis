# Praxis Dispatch Ingest — 2026-06-22 (Dispatch #24)

**Date**: 2026-06-22T14:12Z
**Run ID**: praxis-dispatch-20260622T141216Z
**Source**: Multi-skill dispatch (Forge + Mentor + Praxis + Dispatch)

## New Journals: 2 (dispatcher-detected, missed by previous ingest)

| Journal | Type | Signals |
|---------|------|---------|
| `ocas-mentor/2026-06-22/mentor-light-20260622T135211Z.json` | mentor light | success, 4 new files, 0 errors, active_skills_30d=14 |
| `ocas-mentor/2026-06-22/mentor-light-20260622T135407Z.json` | mentor light | success, 2 new files, 0 errors, active_skills_30d=14 |

Both journals were written at ~13:52-13:54Z, BEFORE `last_ingest_run` (13:58Z) but NOT in `journals_evaluated.jsonl`. The previous Praxis ingest's mtime-based discovery missed them because `last_ingest_run` had already been advanced past their mtime by the Mentor heartbeat script.

**Fix applied**: Evaluated both journals directly from dispatcher's `new_files` list, bypassing mtime comparison. Recorded 2 no-signal events. Added to `journals_evaluated.jsonl`.

## Root Cause: Cross-Pipeline State Collision (Recurring)

The Mentor heartbeat's `cron-heartbeat-light.py` updates `ingest_state.json:last_ingest_run` when it writes evidence. When Praxis runs AFTER Mentor in the same dispatch wave, the mtime comparison `journal_mtime > last_ingest_run` fails for journals written between the dispatcher's scan and the Mentor heartbeat's state update.

**Mitigation**: Always evaluate the dispatcher's `new_files` list as a fallback, regardless of mtime-based discovery results. See SKILL.md § Dispatch / Cron Integration step 3.

## Other Pipelines

- **Forge**: no_op (all proposals already processed)
- **Mentor**: Clean run, 0 new files, active_skills_30d corrected 14→22
- **Email**: 1 thread (Morning Briefing from jared.zimmerman@gmail.com) — archived, no action needed

## Third-Wave Mitigation

All dispatch-output journals (forge-scan, praxis-dispatch) added to `journals_evaluated.jsonl` to prevent re-detection in next wave.
