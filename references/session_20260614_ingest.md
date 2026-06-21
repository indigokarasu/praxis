# Session 2026-06-14 Ingest

**Date:** 2026-06-14 01:07 UTC | **Cron:** praxis:journal_ingest

## 18:32 UTC Ingest Run (Separate Cron)

- 5 unevaluated journals (4 forge no-op, 1 spot all-inactive) → 0 new events
- **Bugs fixed**: (1) Compaction `removed = len(eval_entries) - compacted` → `len(eval_entries) - len(compacted)`. (2) `'final_shifts' in dir()` returns false positives → use `locals()` or pre-initialize. (3) Stray `else:` at wrong indent → SyntaxError. (4) Forge no-op `result: "no_files_found"` → added substring fallback.
- Cleaned 9 stale ad-hoc scripts from data directory root
- Added "Python Anti-Patterns" section to `ingest-script-pattern.md`
- State after: 247 events, 28 lessons, 12 active / 20 proposed shifts, all 0d old

New event: ocas-finch scan-0100 → failure_keyword (FALSE POSITIVE: json.dumps() keyword scan hit "exception" from filename "Metformin_ER_Exception_Continuation_2026-06-10" in drive.notable[]). Journal is all-healthy, no escalations. Contained by dedup.

Gotcha: Finch scan summary dicts contain filenames/subject lines that produce failure keywords during json.dumps() scanning. Existing "Dict-format summaries with success status" gotcha doesn't cover this because finch lacks status/type fields. Fix: for ocas-finch journals, skip json.dumps(); rely only on structured signals (signals.*, findings[], tasks_added[]).