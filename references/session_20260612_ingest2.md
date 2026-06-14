# Session 2026-06-12 — Praxis Journal Ingest (Second Run)

## What happened

Ran the Praxis journal ingest cron job at 08:38 UTC, scanning 14 unevaluated journals.

## False positive detected and removed

An ocas-spot Observation-type journal stored summary as a dict of zero-count metrics:
{"venues_checked": 0, "new_availability": 0, "skipped": 0, "errors": 0}
with type: "Observation" and status: "skipped".

The ingest script converted this dict to a JSON string for keyword matching. The key "errors" matched the failure_keyword filter, producing a false positive event.

Resolution: Detected the false positive post-write, removed the spurious event from events.jsonl (17 -> 16 events), and fixed the eval update from event_recorded to no_signal.

## Root cause: gap between noise filter policy and script pattern

The journal_ingestion.md noise filter rule #3 already covers this case, but ingest-script-pattern.md item 12 said "use json.dumps(d) for keyword scanning" without checking type/status first. The script pattern overrode the noise filter policy.

## Fixes applied to skill library

1. ingest-script-pattern.md item 12: Added guard to check type/status BEFORE JSON serialization. If type is "Observation" or all values are zero-count, skip keyword matching.

2. gotchas-praxis.md: Added sub-case under "Dict-format summaries with success status" gotcha for Observation-type journals with zero-count dict summaries.

## Results (final)

- Journals scanned: 14
- New events: 0 (1 false positive removed)
- New lessons: 0
- Active shifts: 5/12

All 14 journals were routine no-ops.
