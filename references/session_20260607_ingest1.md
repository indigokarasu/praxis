# Session 2026-06-07 Praxis Ingest — Journal Scan Findings

## What happened

Cron-triggered Praxis journal ingest ran at 00:08 UTC. Scanned 6 unevaluated journals from today+yesterday.

## Journals scanned

| Journal | Signals found | Outcome |
|---------|--------------|---------|
| `ocas-custodian/2026-06-06/light-scan-20260606-170000.json` | `failure_keyword` ("error" in top-level summary) | **False positive** — removed. Summary said "All 13 error-state jobs are transient" |
| `ocas-forge/2026-06-06/r_20260606_journal-scan-1780789312.json` | none | no_signal |
| `ocas-forge/2026-06-06/r_20260606_journal-scan-1780790850.json` | none | no_signal |
| `ocas-forge/2026-06-06/r_20260606_journal-scan-1780790187.json` | none | no_signal |
| `ocas-forge/2026-06-06/r_20260606_journal-scan-1780790582.json` | none | no_signal |
| `ocas-spot/2026-06-06/sweep_20260606_003000.json` | none | no_signal |

## False positive cleanup

Also removed 4 false-positive events from the prior (21:14) ingest run:
- 2 custodian journals (light-scan, deep-scan) — `failure_keyword` from summaries describing clean state
- 1 finch scan journal — `failure_keyword` + `auth_failure` from summary describing clean state

All 5 false positives shared the same pattern: keyword matching on "error"/"expired" in top-level `summary` strings that described healthy/clean system state.

## Root cause

The ingest script's signal extraction checked `decision.summary` for keyword matching but also checked top-level `summary` as a fallback. The noise filters only addressed:
1. Dict-format summaries with success status
2. `escalation_flagged` arrays in custodian journals
3. "Correction" keyword false positives

They did NOT address plain string `summary` fields at the top level that contain failure keywords in non-failure contexts.

## Fix applied

Added a new noise filter section to `ingest-script-pattern.md`:
- **Top-level `summary` string noise filter** — Semantic suppression check using `SUPPRESS_PHRASES` list
- Only suppresses when the ONLY signals are `failure_keyword` (preserves real signals)
- Added corresponding gotcha entry to `gotchas-praxis.md`

## State after ingest

- Events: 121 (removed 5 false positives)
- Lessons: 241 (0 new — all groups already covered)
- Shifts: 12 active (at cap), 214 proposed
- No new lessons or shifts activated

## Key takeaway

The `failure_keyword` signal type remains the noisiest signal path. Every ingest run should apply semantic suppression on top of keyword matching — the suppress phrase list is a durable, extensible approach that's cheaper than post-hoc event cleanup.
