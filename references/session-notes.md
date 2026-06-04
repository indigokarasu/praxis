# Praxis — Session Notes Reference

## Session Ingestion Notes

### 2026-05-30 Sessions

- `session_20260530_review.md` — Schema variance discoveries, creation of scripts/praxis_review.py
- `session_20260530_ingest.md` — Lesson inference quality issues, unknown-domain noise, cross-skill lesson scoping
- `session_20260530_ingest3.md` — Sibling agent file contention, eval dedup (121 duplicates), observation event noise floor, shift activation dedup
- `session_20260530_ingest4.md` — Reinforcement text-match false positive (orphaned-cron shift incorrectly matched to custodian execution event)

### 2026-06-01 Sessions

- `session_20260601_ingest1.md` — Lesson suppression false-positive gap (keyword-only matching), stale root-level journal filtering, mentor coverage critically low (0.87%), dispatch security alert first-seed
- `session_20260601_ingest2.md` — `-not -path` glob pitfall confirmation (shell find returning 0 results), sibling agent file contention on ingest_run.py, 8 routine journals no-signal correctly skipped, OAuth token invalid_grant confirmed persistent (3rd day), cap at 12/12

### 2026-05-31 Sessions

- `session_20260531_ingest.md` — Canonical ID vs filesystem path confusion, 133 duplicate events removed, shift semantic flooding
- `session_20260531_ingest2.md` — Near-duplicate journal ID detection, bones:paper-trade Telegram delivery failure, HTTP 429 shift reinforcement
- `session_20260531_ingest3.md` — Legacy `id` vs `event_id` KeyError in lesson extraction, system state verification
- `session_20260531_ingest4.md` — Two-pass lesson extraction category-shifted pattern blind spot, escalation-seed event handling, system health signals
- `session_20260531_ingest5.md` — Unknown signal_type noise filter, praxis_ingest_run.py rewrite, shift semantic flooding
- `session_20260531_ingest6.md` — Escalation fingerprint enrichment gap, non-standard journal schema confirmation, runtime typo
- `session_20260531_ingest7.md` — Batch event ID collision, lesson source_event_ids referencing phantom events, shift activation at 12/12 cap
- `session_20260531_ingest9.md` — OAuth token corruption from ENOSPC, expired→reauth_needed state escalation
- `session_20260531_ingest10.md` — Steady-state zero-new-journals confirmation, scan-window race condition, lesson_id vs id schema variance
- `session_20260531_ingest11.md` — datetime import namespace collision, dual-call datetime.now() timestamp drift, taste scan auth failure
- `session_20260531_ingest12.md` — Ad-hoc scan script lesson re-extraction bug, domain normalization gap, shift activation for ocas-taste auth-failure
- `session_20260531_ingest13.md` — Stale eval entries referencing deleted journal files, HTTP 429 rate-limit pattern lesson, cross-domain auth_failure observation
- `session_20260531_ingest14.md` — Cross-skill corroboration detection (custodian + finch both detecting finch:weekly 401 within 2 minutes)
- `session_20260531_ingest15.md` — Same-skill temporal dedup, shift merge-before-cap enforcement gap
