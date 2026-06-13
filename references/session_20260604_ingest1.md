# Praxis Ingest Session — 2026-06-04

## Run Summary

- **Time**: 2026-06-04T17:19–17:24 UTC
- **Trigger**: Scheduled cron (`praxis:journal_ingest`)
- **Journals scanned**: 13 (today + yesterday)
- **New events**: 5 (all from targeted re-extraction)
- **New lessons**: 0 (all patterns already covered)
- **New shifts activated**: 0 (cap 12/12)

## Journals Processed

| Journal | Skill | Initial Pass | Re-extraction |
|---------|-------|-------------|---------------|
| esc-run-20260604-0950 | custodian | NO SIGNAL | 1 escalation (finding-level) |
| esc-run-20260604-1007 | custodian | NO SIGNAL | — |
| light-20260604-1707 | custodian | NO SIGNAL | 1 platform_failure (8/105 errors) |
| taste-scan-historical-365d | taste | NO SIGNAL | — |
| r_journal-scan-2000 | forge | NO SIGNAL | — |
| r_journal-scan-1830 | forge | NO SIGNAL | — |
| run_cron_20260604_171837 | elephas | NO SIGNAL | — |
| run_cron_20260604_164050 | elephas | NO SIGNAL | — |
| run_cron_20260604_165325 | elephas | NO SIGNAL | — |
| monitor-20260604-1709 | bones | NO SIGNAL | — |
| sweep_20260604_0945 | spot | NO SIGNAL | — |
| sweep_20260604_100431 | spot | NO SIGNAL | — |
| scan-1710 | finch | NO SIGNAL | 3 events (auth_failure, platform_failure, execution_error) |

## Key Finding: Nested Signal Scan Gap

### Problem
The initial signal extraction pass only checked top-level journal fields (`escalation_needed`, `status`, `summary`). Two journal schemas store critical signals in nested structures:

1. **Custodian escalation-runner journals**: `findings[]` array contains per-finding `escalation_needed: true` — the top-level journal has no `escalation_needed` field at all.
2. **Finch scan journals**: `sources.*.error_breakdown` dict contains categorized error counts (`http_401`, `http_429`, `script_path_blocked`) — the top-level journal has no `status` or `summary` fields.

### Missed Signals
- `ocas-custodian/esc-run-20260604-0950.json`: finding `oc_google_token_invalid_email_check_20260603_rev2` with `escalation_needed: true`
- `ocas-finch/scan-1710.json`: 5 HTTP 401, 4 HTTP 429, 7 script_path_blocked errors in `sources.cron.error_breakdown`
- `ocas-custodian/light-20260604-1707.json`: 8/105 error jobs

### Fix Applied
Added nested scan steps 8 and 10 to the signal extraction checklist in `ingest-script-pattern.md`:
- Step 8: Scan `findings[]` arrays for per-finding `escalation_needed`, `status`, and `action_taken`
- Step 10: Scan `sources.*.error_breakdown` for non-zero error category counts

### Lesson
**Never rely solely on top-level fields.** Always drill into `findings[]`, `sources.*`, and `new_findings[]` arrays on the initial pass. A two-phase extraction (initial + targeted re-extraction) doubles script complexity and ingest time.

## Events Recorded

| # | Signal Type | Source | Detail |
|---|------------|--------|--------|
| 1 | escalation | custodian esc-run-0950 | `oc_google_token_invalid_email_check_20260603_rev2` — Google OAuth token invalid for email check job, MCP credentials valid but job overdue |
| 2 | auth_failure | finch scan-1710 | 5 HTTP 401 errors in cron jobs |
| 3 | platform_failure | finch scan-1710 | 4 HTTP 429 (rate limit) errors in cron jobs |
| 4 | execution_error | finch scan-1710 | 7 script_path_blocked errors in cron jobs |
| 5 | platform_failure | custodian light-1707 | 8/105 error jobs (7.6% error rate) |

## Notable Signal: Google OAuth Token

The `oc_google_token_invalid_email_check_20260603_rev2` issue has been open since June 3. The custodian runner noted:
- MCP credentials at `/root/.google_workspace_mcp/credentials/jared.zimmerman@gmail.com.json` are valid (updated 2026-06-04T09:36)
- The email check job's `last_run_at` is 2026-06-01 (before the script path fix)
- Job is overdue — should work on next run
- Marked as "monitoring" instead of active escalation

## Store State After Run

- Events: 187 (was 182 before this run)
- Lessons: 111 (no change — all patterns already covered)
- Shifts: 43 total, 12 active (cap reached)
- Decisions: 222
- Journals evaluated: 5,682
