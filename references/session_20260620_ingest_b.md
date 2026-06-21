# Session 2026-06-20 Ingest Cron B — Findings

## Run Summary
- **Date:** 2026-06-20 ~03:20 UTC
- **Journals scanned:** 500 (batch-limited from 11,974 unevaluated)
- **New events:** 12
- **New lessons:** 1
- **New shifts:** 0 (cap at 12/12)
- **Active shifts:** 12/12

## New Events
All 12 events were `finch_actionable_email` from ocas-finch scans spanning Jun 13–20:
- 10 distinct finch scan journals
- 2–4 actionable emails per scan
- Typical content: arbolus study applications, paid consulting opportunities, job alerts

## New Lesson
**`finch_actionable_email | execution`** — confidence: high, 12 events
- What: Finch scans detect actionable emails on 12 occasions (avg 1.0 per scan when filtered)
- Why: Email monitoring is a core finch function; actionable items require attention
- When: During routine finch scans when new emails arrive from sources like arbolus, job alerts, service notifications

## Shift Cap Status
- 12/12 active shifts — cannot activate new finch_actionable_email shift
- No overlap with existing `auth_failure | ocas-finch` shift (different signal_type)
- 8 shifts at 0 reinforcements (all from Jun 18 rebuild), approaching 14-day decay

## Backlog
- ~11,463 journals still unevaluated after this 500-journal batch
- ocas-mentor largest source (1,093), ocas-forge second (336)
- Batch limiting at 500/run continues to manage

## Key Observations
1. **finch_actionable_email is a recurring pattern** — first time crossing ≥2 threshold as a lesson. Legitimate signal (not noise) but shift cap prevents activation.
2. **Cap management needed** — 8 shifts at 0 reinforcements should be reviewed for expiry to make room for new patterns.
3. **All other journal types** (forge, spot, mentor, custodian) continue to produce only routine no-signal results.
4. **Dual-path scan** confirmed working — journals from both indigo and legacy paths correctly deduped.
5. **Lesson extraction scoping works** — filtering to new events only (since last_lesson_extraction_event_id) prevented stale lesson re-creation.