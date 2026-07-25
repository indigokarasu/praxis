# Praxis Ingest — 2026-06-13 Cron Run 3 (Steady-State)

**Date:** 2026-06-13T05:12:23Z
**Run ID:** `r_20260613_051223_8fa0a5d4`

## Summary

Steady-state ingest run. 8 unevaluated journals scanned. 3 new events from finch scan (OAuth cascade + cron errors). 0 new lessons, 0 new shifts. All existing lesson groups and active shifts remain stable.

## Journals Scanned

| Journal | Signal |
|---------|--------|
| `ocas-forge/2026-06-13/r_20260613_journal-scan-1781327521.json` | no_signal |
| `ocas-forge/2026-06-12/r_20260612_journal-scan-1781326280.json` | no_signal |
| `ocas-forge/2026-06-12/r_20260612_journal-scan-1781326029.json` | no_signal |
| `ocas-elephas/2026-06-13/run_7a9a8fb7d04e.json` | no_signal |
| `ocas-elephas/2026-06-13/run_84a926fc699e.json` | no_signal |
| `ocas-spot/2026-06-12/sweep_20260612_214700.json` | no_signal |
| `ocas-spot/2026-06-12/spot-20260612-220217.json` | no_signal |
| `ocas-finch/2026-06-13/scan-0506.json` | **event_recorded** (3 signal types) |

## New Events

All from `ocas-finch/2026-06-13/scan-0506.json`:

1. **`cron_errors`**: `cron_health.error_jobs: 6` — 6 cron jobs failing
2. **`execution_error`**: `sources_scanned.email.status: blocked` — email source blocked
3. **`failure_keyword`**: `summary contains 'error'` — scan summary contains error references

## Key Finding: Google OAuth Fully Expired

The finch scan reveals Google OAuth is **fully expired** for `<user-google-email>`:
- **`RefreshError: invalid_grant`** on ALL Google MCP tools
- Affected services: Gmail (blocked), Calendar (blocked), Drive (blocked)
- All Google Workspace MCP-dependent cron jobs failing
<<<<<<< Updated upstream
- Also: missing `<hermes-home>/secrets/plaid.env`, HTTP 429 rate limits, response truncation (3 attempts exhausted), Telegram delivery failure (interpreter shutdown race)
=======
- Also: missing `~/.hermes/secrets/plaid.env`, HTTP 429 rate limits, response truncation (3 attempts exhausted), Telegram delivery failure (interpreter shutdown race)
>>>>>>> Stashed changes

**Praxis assessment:** This maps to existing `auth_failure` active shift (`shf_20260612_074237_a24d08`). No new shift needed — it's already tracked. This is an infrastructure issue requiring <operator>'s manual re-authorization, not a Praxis behavioral adjustment.

## Result

- Events: 50 total (3 new, 47 existing)
- Lessons: 10 (0 new — all 11 event groups already covered or have <2 events in new groups)
- Shifts: 7 active, 0 proposed, 0 activated
- Cap: 7/12
- `journals_evaluated.jsonl`: 672 entries

## Gotcha Updates

1. **Added `sources_scanned` to finch schema variant list** in `gotchas-praxis.md` — previously only `signals`, `sources`, `signal_sources` were documented.
2. **Added forge `result`-field no-op pattern** to `gotchas-praxis.md` — forge scan journals use `result` (not `status`) with no-op values like `"clean"`, `"no-op"`, `"no_new_proposals"`.