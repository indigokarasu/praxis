# Session: 2026-06-13 Praxis Ingest (cron)

**Run ID:** r_20260613_072830 (first pass) + r_20260613_073448 (fixed pass)
**Date:** 2026-06-13 07:24 UTC

## Summary

Two-pass ingest run. First pass missed signals due to incomplete finch `sources.*` schema handling; fixed pass recovered them.

## Journals Scanned

18 files across 5 skills (ocas-elephas, ocas-finch, ocas-forge, ocas-mentor, ocas-spot). 11 unevaluated on first pass, all re-processed on second pass.

## Findings

### New Events (4)

| # | Signal Type | Source | Detail |
|---|------------|--------|--------|
| 1 | `escalation` | ocas-finch/scan-0600 | Critical finding: "Google Workspace MCP server unreachable" — both jared.zimmerman@gmail.com and mx.indigo.karasu@gmail.com affected. All 3 Google Workspace tools (Gmail, Calendar, Drive) impacted. |
| 2 | `execution_error` | ocas-finch/scan-0600 | sources.cron_health: "Unable to verify — Google Workspace MCP unreachable" |
| 3 | `failure_keyword` | ocas-finch/scan-0600 | Summary contains "unreachable" |
| 4 | `observation` | ocas-mentor/mentor-light-065528 | Low evaluation coverage: 0.1364 (below 0.2 threshold) |

Plus 1 previously recorded event (ocas-spot persistent_platform_failure from 2026-06-12).

### Lessons Extracted

0 — all event groups have <2 events (each signal type appears only once).

### Shifts Proposed

0 — no high-confidence lessons available (lessons require 2+ events per group).

## Root Cause of First-Pass Failure

The finch scan-0600 journal uses a **string-value `sources.*` schema** where each value is a plain string (not a dict):
```
sources.cron_health: "Unable to verify — Google Workspace MCP unreachable"
sources.email: "MCP unreachable — cannot check"
```

The first-pass extraction code only handled dict-valued `sources.*` entries. String values were silently skipped. This is a distinct schema variant from the already-documented `signals.*`, `signal_sources.*`, and `sources_scanned.*` dict-based schemas.

Additionally, the critical finding in `findings[]` with `type: "critical"` was missed because the extraction only checked `escalation_needed`, `status`, and `action_taken` within findings — not the `type` field.

## Fixes Applied

1. Added `isinstance(src_val, str)` branch to `sources.*` extraction (keyword scan for failure indicators)
2. Added `findings[].type == "critical"` → escalation signal check
3. Added mentor `metrics.evaluation_coverage < 0.2` → observation signal
4. Patched `gotchas-praxis.md` with new finch string-value `sources.*` gotcha
5. Patched `ingest-script-pattern.md` with scan-0600 schema variant and critical findings type check
6. Patched `journal_ingestion.md` with `metrics.active_anomalies` check

## Updated Files

- `scripts/ingest_run_20260613_fixed.py` — corrected second pass (canonical for this date)
- `references/gotchas-praxis.md` — added finch string-value sources gotcha
- `references/ingest-script-pattern.md` — added scan-0600 schema + findings type check
- `references/journal_ingestion.md` — added anomalies check
