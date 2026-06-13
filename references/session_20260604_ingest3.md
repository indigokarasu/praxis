# Session Note — 2026-06-04 Ingest Cycle 10 (Cron)

## Run ID
`ingest_20260604T224556`

## What happened
- Scanned 2 unevaluated journals from 2026-06-04
- Found signals in 1 journal: `ocas-custodian/esc-run-20260604-1539.json`
  - `escalation` (planning): 3 open issues requiring user action (OAuth client deleted, script-path false positive, HTTP 401)
  - `correction` (execution): stale email-check error auto-resolved
- 1 journal clean: `ocas-elephas/run_cron_20260604_224411.json` (non-standard schema, no status field)
- Recorded 1 new event (escalation; correction dropped by source_journal dedup)
- 1 new lesson: `lesson_escalation_planning` (2 events in group)
- 0 shifts activated (cap at 12/12, 1 shift proposed)
- Active shifts: 12/12, 17 proposed

## Issues / Fixes Applied

### 1. Schema-ambiguous journal noise filter gap (FIXED in ingest-script-pattern.md)
The elephas journal had no top-level `status` field. The noise filter `if status in ("ok", "success", "complete", "completed") and not signals` didn't catch it because `data.get("status", "")` returned `""`. The journal fell through all signal checks without an eval_update being appended. It was later marked as "event_recorded" in the batch eval write — a false status.

**Fix:** Added explicit `no_signal` fallback after the signal loop: if `signals` is empty after all checks, always append a `no_signal` eval_update regardless of status field presence. This replaces the earlier pattern of relying solely on `status in ("ok", ...)` as the no-signal gate.

### 2. Post-write dedup drops multiple signals from same journal (DOCUMENTED in ingest-script-pattern.md)
The dedup by `source_journal` keeps only 1 event per journal file. The custodian esc-run journal produced both `escalation` and `correction` signals, but only the first (escalation) survived dedup. Documented as a known limitation with recommendation to dedup by `(source_journal, signal_type)` when both types matter.

### 3. journals_evaluated.jsonl growth rate
The file now has ~5,842 entries. At ~8 entries per 30-min cycle (~384/day), the 30-day retention policy keeps it bounded at ~11,500 entries. Compaction at 5,000-entry threshold will trigger roughly every 13 days.

## Observations
- Custodian escalation-runner journals remain the most reliable source of escalation signals
- The active shift cap of 12 continues to block new activations — 17 proposed shifts are waiting
- Elephas journals use a non-standard schema (no top-level `status`, uses `decision.journals_scanned` etc.) — the ingest script must handle missing fields gracefully
