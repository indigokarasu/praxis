# Session 2026-06-12 — Praxis Journal Ingest (Primary + Supplemental)

## What happened

Ran the Praxis journal ingest cron job for 2026-06-12. Two-pass execution: primary scan + supplemental re-scan after identifying a schema gap.

## Schema gap discovered: `signal_sources.*`

**The critical finding:** Newer finch scan journals (scan-0200, scan-0702) use `signal_sources.*` as the top-level key — not `signals.*` or `sources.*` as documented in the gotcha docs. The `signals.*` key is present but empty.

Schema structure:
```json
{
  "signal_sources": {
    "cron_health": {
      "status": "completed",
      "total_jobs": 105,
      "error_jobs": 10,
      "new_issues_since_last_scan": [...],
      "unchanged_errors": [...]
    },
    "email": { "status": "blocked", ... },
    "calendar": { "status": "blocked", ... },
    "drive": { "status": "blocked", ... },
    "sessions": { ... },
    "system": { ... }
  }
}
```

**Impact:** Primary ingest pass found only 1 event from scan-0702 (keyword match on summary). Supplemental pass recovered 6 additional events: email/calendar/drive blocked (3 execution_error), 2 new issues (state.db oversized 8GB, gateway health unreachable), cron_health error_jobs count, and an auth_failure from OAuth token expiry.

## Events recorded (7 new)

| Signal Type | Journal | Detail |
|-------------|---------|--------|
| auth_failure | scan-0702 | OAuth broken across all Workspace APIs (from summary keyword) |
| cron_errors | scan-0200 | error_jobs=10 (from signal_sources) |
| execution_error | scan-0200 | email.status=blocked (from signal_sources) |
| auth_failure | scan-0200 | OAuth token expired (from summary) |
| failure_keyword | scan-0200 | Summary error keyword |
| execution_error | scan-0702 | new_issue: state.db oversized 8GB (from signal_sources) |
| cron_errors | scan-0702 | error_jobs=10 (from signal_sources) |

## Lessons extracted (3 new, high confidence)

1. **cron_errors/execution** (ocas-finch, 3 events) — Recurring cron errors across multiple finch scans
2. **auth_failure/execution** (ocas-finch, 2 events) — Google OAuth expired/revoked, cascading blocks
3. **failure_keyword/execution** (ocas-finch, 2 events) — Task additions correlate with cron error bursts

## Shifts activated (3 new)

- `shf_...0623ee` — cron_errors behavioral adjustment (ocas-finch, execution)
- `shf_...2de25c` — failure_keyword behavioral adjustment (ocas-finch, execution)
- `shf_...a24d08` — auth_failure behavioral adjustment (ocas-finch, execution)

**Total active shifts: 5/12**

## Key operational notes

- **Always check all three finch schema variants:** `signals.*`, `sources.*`, AND `signal_sources.*` — whichever is non-empty contains the data
- The `signal_sources` key name (with the `signal_` prefix) is easy to miss when the code only checks `signals` and `sources`
- Semantic suppression worked correctly: scan-0200 summary contains "System healthy" but real signals from `signal_sources` prevented suppression (correct behavior — don't suppress when real signals exist)
- Supplemental ingest pattern works: re-scan specific journals by canonical ID, check for signal types not already covered by existing events, append only truly new signals

## Files modified

- `references/ingest-script-pattern.md` — Added step 9b for `signal_sources.*` extraction
- `references/journal_ingestion.md` — Updated step 7/7b for `signal_sources.*` schema
