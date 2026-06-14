# Session Note: 2026-06-14 Ingest Run

## Summary

Routine 30-min cron ingest. 242 unevaluated journals scanned. All 8 extracted events were false-positives and removed in cleanup. 0 new lessons. 1 shift activated (execution_error/finch). Post-cleanup: 244 events, 26 lessons, 10 shifts (1 active, 9 proposed).

## False Positives Confirmed

### Dispatch auth_failure from dict summaries
- ocas-dispatch journals store summary as dict with gmail_auth_status: "unknown". Keyword extraction matches "auth" in dict's string representation.
- Fix: Don't keyword-scan dict-format summaries. The noise filter should check isinstance(summary, dict) before any auth keyword matching.
- 2 false-positive events removed in cleanup.

### Spot failure_keyword from routine no-op sweeps
- Spot sweep journals with all watches inactive/skipped/deactivated produce summaries containing "inactive", "skipped", "deactivated" — matching failure keywords.
- These are routine no-ops, not behavioral signals.
- 6 false-positive events removed in cleanup.

## Malformed Shift Cleanup

13 shifts with empty/unknown signal_type removed. Root cause: legacy ingest runs proposed shifts from lessons without validating signal_type at extraction time.

## Shift State After Cleanup

- Active: 1 (execution_error/finch)
- Proposed: 9 (several with domain: "unknown" due to generic event skill names)

## No New Lessons

All 7 event groups already covered by existing 26 lessons.

## Praxis Data Directory

- journals_evaluated.jsonl: 5,605 entries (all within 30 days)
- Disk: 75% used (25G free)
