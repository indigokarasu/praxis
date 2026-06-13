# Session 2026-06-07 — Praxis Journal Ingest (Cron)

## Summary
Routine 30-min cron ingest. 7 unevaluated journals found (all from 2026-06-06). 1 new event recorded, 0 new lessons, 0 new shifts activated.

## Journals Processed
| Journal | Signal | Action |
|---------|--------|--------|
| ocas-custodian/light-scan-1800 | none (all transient, consecutive_failures=0) | no_signal |
| ocas-finch/scan-1800 | failure_keyword (weave:sync-contacts model error in tasks_added) | event_recorded |
| ocas-forge/journal-scan-1780793241 | none (completed, no new work) | no_signal |
| ocas-forge/journal-scan-1780793562 | none (no_new_work) | no_signal |
| ocas-forge/r_journal-scan-1780792934 | none (complete, all processed) | no_signal |
| ocas-forge/r_journal-scan-1780793802 | none (clean) | no_signal |
| ocas-forge/r_journal-scan-1780794381 | none (all_clear) | no_signal |

## New Event
- `ocas-finch/scan-1800` → `failure_keyword` signal from `tasks_added[]` containing "weave-sync-contacts-model-error"
- The underlying cause: `signals.cron.new_errors[]` had a real entry: `weave:sync-contacts` — `nvidia/nemotron-3-ultra:free is not a valid model ID (HTTP 400)`, first seen 2026-06-06T13:14Z, severity "new — different from 429 pattern"
- Classified as `failure_keyword` (not `cron_errors`) because the script checked `tasks_added` but not `signals.cron.new_errors`

## Key Findings

### Finch Schema: `signals` not `sources`
The finch scan-1800 journal uses `signals.cron` (not `sources.cron`). The `sources` key is empty. All cron data — `new_errors[]`, `error_jobs`, `healthy_jobs`, `error_breakdown` — lives under `signals.*`. The ingest pattern checklist (items 9-10) and the gotcha about finch escalations both referenced `sources.*`, which is wrong. **Fixed in this session**: updated `ingest-script-pattern.md` items 9-10 and added a new gotcha.

### Script Bugs Fixed
1. **run_id format string**: `%%M` (double percent) in f-string → fixed to `%M`
2. **Exception handler `dir()` anti-pattern**: `return signals, data if 'data' in dir() else {}` → fixed to `return signals, {}`
3. **Typo**: `fixes_applies` → `fixes_applied` in checks path

### System State
- Active shifts: 12/12 (at cap)
- Proposed shifts: 214 (backed up)
- Total events: 122
- Total lessons: 241
- All `(signal_type, failure_phase)` groups already have lessons — no new patterns emerged

### Noise Filtering Performance
- Custodian light-scan: correctly suppressed (transient errors, consecutive_failures=0)
- Forge journal scans: correctly suppressed (routine no-op results)
- Semantic suppression filter (SUPPRESS_PHRASES) was not triggered because the custodian journal's `summary` field was a plain string that didn't match the `should_suppress_failure_keyword` function's guard (the function checks if the ONLY signals are `failure_keyword`; since no signals were extracted from the summary, the journal was already `no_signal` before suppression was evaluated)

## Recommendations
1. Update finch scan signal extraction to check `signals.cron.new_errors[]` directly
2. Consider lowering the active shift cap or implementing proposed-shift TTL cleanup (214 proposed shifts is a large backlog)
3. The `tasks_added` keyword-matching path is a reasonable fallback but should not be the primary signal path for finch journals
