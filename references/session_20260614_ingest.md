# Session 2026-06-14 Ingest

**Date:** 2026-06-14 01:07 UTC | **Cron:** praxis:journal_ingest

## Results: 186 scanned, 7 unevaluated, 1 new event, 0 new lessons, 0 new shifts.

New event: ocas-finch scan-0100 → failure_keyword (FALSE POSITIVE: json.dumps() keyword scan hit "exception" from filename "Metformin_ER_Exception_Continuation_2026-06-10" in drive.notable[]). Journal is all-healthy, no escalations. Contained by dedup.

Gotcha: Finch scan summary dicts contain filenames/subject lines that produce failure keywords during json.dumps() scanning. Existing "Dict-format summaries with success status" gotcha doesn't cover this because finch lacks status/type fields. Fix: for ocas-finch journals, skip json.dumps(); rely only on structured signals (signals.*, findings[], tasks_added[]).