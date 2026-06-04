# Session: 2026-05-31 Ingest Run (journal_ingest #13)

## Run Summary
- **Date**: 2026-05-31T18:17:00Z
- **Journals scanned**: 132 on disk (5,085 evaluated)
- **New journals**: 3
- **Journals with signals**: 1 (ocas-finch)
- **Routine/no-op journals**: 2 (ocas-elephas success, ocas-lucid skipped)
- **Events recorded**: 3
- **Lessons extracted**: 2 (1 high confidence, 1 low/proposed)
- **Shifts activated**: 1 (finch HTTP 429 stagger)
- **Active shifts after**: 7/12

## New Events
1. **ocas-finch execution_error** — NEW HTTP 429 on corvus:deep cron (not in error at prior scan)
2. **ocas-finch execution_error** — NEW HTTP 429 on look:morning-scan cron (not in error at prior scan)
3. **ocas-finch auth_failure** — NEW 401 on ocas-finch:weekly (different auth path from daily)

## Lessons Extracted
- **High confidence**: HTTP 429 rate limiting affects multiple cron jobs simultaneously when LLM API calls cluster (shared rate-limit bucket). 2 events, domain: ocas-finch, phase: execution. Pattern key: `http_429_rate_limit`.
- **Low confidence (proposed)**: Cross-skill Google OAuth token failures span system/taste/finch domains. Token-level root cause, not per-skill. 3 events, cross-domain. Recorded as observation, not promoted to shift.

## Shifts Activated
- `shift-finch-http429` — Before finch scan execution: check for HTTP 429 on recently-recovered jobs; stagger execution or add backoff when multiple jobs transition to 429 simultaneously. (7/12 cap)

## Bugs Found
### Stale eval entries reference deleted journal files
**Problem**: The set-difference scan picked up `ocas-custodian/no-date/light-scan-20260531-080400.json` as "unevaluated" even though the file no longer existed on disk. The journal had been evaluated in a prior run but the file was subsequently deleted or moved.

**Fix**: Added `os.path.exists()` filter to the scan. After computing the set difference (disk IDs minus evaluated IDs), filter out any paths that don't exist on disk before processing.

**SKILL.md update**: Added gotcha — "Stale eval entries reference deleted journal files."

## System State Post-Run
| Metric | Value |
|--------|-------|
| events.jsonl | 217 |
| lessons.jsonl | 12 |
| shifts.jsonl | 7 (7 active / 12 cap) |
| journals_evaluated.jsonl | 5,088 |

## Notes
- Clean run with no duplicate events or lessons.
- Cross-domain auth_failure lesson correctly held at confidence: low / status: proposed per gotcha.
- HTTP 429 pattern was new — no existing shift covered rate-limit stagger behavior.
- All prior gotchas applied correctly (no routine-success events, lucid skipped, domain normalized).
