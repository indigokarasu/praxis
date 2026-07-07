# Session 2026-06-28 — Cron Ingest 19:37Z (Bug 2 Cleanup Scope Expansion)

**Run type:** `cron_ingest`  
**Ingested:** 19:37Z, June 28 2026  
**Active shifts:** 3/12

## Summary

Routine ingest with zero genuine behavioral signals (all 4 events were `no_signal` from ocas-mentor routine). The production script's Bug 2 (full-history lesson reprocessing) produced **14 noise lessons** — notably all had `signal_type: "?"` and `confidence: "high"`. 

**Key insight:** The existing checklist criterion for noise cleanup was "remove lessons with `confidence: low`" — but Bug 2's Pass 2 grounding ALWAYS upgrades lessons to `confidence: high`, so the `low` criterion caught only 2 of 14. The `(signal_type == "?")` pattern was the definitive marker.

## Why This Matters

Bug 2 reprocesses ~3,500 events every run. Most legacy events (pre-2026-06) lack a `signal_type` field entirely. When the lesson extraction groups these, the resulting lessons inherit `signal_type: "?"`. These lessons:
- Always get `confidence: high` from Pass 2 (even though they're noise)
- Have inflated event counts (n=9 to n=51) from decades of historical accumulation
- Are semantically meaningless (domain: `system`, or skill-named domains with `?` signal)

## Cleanup Decision Rule Established

> If ALL events in the current run are `no_signal`, then ALL co-produced lessons are Bug 2 noise — wipe `lessons.jsonl` entirely. The `(signal_type == "?")` heuristic is the most reliable single-indicator filter.

## Metrics

| Metric | Value |
|--------|-------|
| Journals processed | 10 (9 script + 1 gap backfill) |
| Events recorded | 4 (all no_signal) |
| Lessons extracted | 14 |
| Lessons cleaned | 14 (all noise) |
| Active shifts | 3 (healthy, all reinforced) |
| Gap journals backfilled | 1 (praxis-cron dispatch_no_op journal) |
| Decay risk | 0 |

## Action Taken

Updated Bug 2 description in Cron Execution Checklist Step 4 and the main Bug 2 section to reflect expanded cleanup criteria beyond `confidence: low`.
