# Session 2026-06-06 — Praxis Journal Ingest (cron)

## Context
Automated cron run scanning all skill journals for new entries.

## Journals Processed
- 9 unevaluated journals found (today + yesterday window)
- 7 clean (no signals): ocas-forge (×2), ocas-dispatch (×2), ocas-elephas (×2), ocas-spot sweep_20260606_045434
- 3 events recorded from 2 journals

## Signals Extracted
1. **ocas-finch/scan-1800** → `execution_error` (cronjob tool unavailable) + `auth_failure` (Calendar OAuth expired)
2. **ocas-spot/sweep_2026-06-06T060000** → `execution_error` (Russamee Square SPA crash post-Book)

## Lessons
- 2 new high-confidence lessons: `cron_errors/execution`, `finding/execution`
- 10 shifts proposed, all held at cap (12/12 active)

## Critical Bug: Dedup Key
**The ingest script used `source_journal` as the dedup key in post-write dedup**, causing finch scan-1800's second signal (`auth_failure`) to be silently dropped. Recovery required a second fix-up script. **Fix: always dedup by `(source_journal, signal_type)`** — this matches the documented best practice in ingest-script-pattern.md §Post-Write Dedup.

## Active Shifts
At cap (12/12). 205 proposed shifts queued. Decay review pending.
