# 2026-06-15 Full Journal Ingest

## What happened

Comprehensive journal ingest run as `praxis:journal_ingest` cron job. First run to scan ALL date directories on disk rather than just today/yesterday.

## Key findings

- **476 journals on disk**, all previously unevaluated (evaluated count was 5895 from prior targeted scans)
- **197 events** extracted across 12 skills (ocas-bower through ocas-vesper)
- **3 new lessons** (1 malformed removed): security_alert/execution, calendar_conflict/planning, directive/planning
- **Shift merge pass**: Consolidated 7 redundant active shifts (same signal_type) → 12 active → 5 active
- **7 new shifts proposed** from uncovered lessons
- **0 parse errors** — signal extraction logic handled all journal schemas correctly

## Validated gotchas

These gotchas from SKILL.md were confirmed critical in this run:

1. **Scan ALL dates** — All 476 journals were across multiple date directories. A today/yesterday filter would have missed everything.
2. **Dedup by (source_journal, signal_type)** — Using just source_journal would collapse distinct signals.
3. **write_file OVERWRITES JSONL** — All append operations used read-then-rewrite or file append mode.
4. **execute_code blocked in cron** — Used `terminal()` + `write_file()` pattern throughout.
5. **Malformed lesson cleanup** — 1 lesson with empty signal_type from custodian journals was correctly identified and removed.
6. **Two-pass lesson extraction** — Pass 1 grouped by (signal_type, failure_phase), Pass 2 added causal grounding (what/why/when) and upgraded confidence to high.
7. **Shift merge before cap** — Merged 7 overlapping shifts before proposing new ones, freeing cap space.

## Scripts produced

- `scripts/ingest_journal_20260615.py` — Journal scan + signal extraction
- `scripts/lesson_extract_20260615.py` — Two-pass lesson extraction
- `scripts/shift_merge_check.py` — Initial merge analysis (crashed on missing key, superseded)
- `scripts/shift_merge_pass.py` — Full merge + proposal pass

## State after ingest

| Metric | Before | After |
|--------|--------|-------|
| Events | 257 | 454 |
| Lessons | 36 | 38 |
| Active shifts | 12 | 5 |
| Proposed shifts | 32 | 39 |
| Expired shifts | 0 | 7 |
| Evaluated journals | 5,895 | 6,371 |

## Session notes reference

See `session_20260615_ingest.md` for prior session's findings on forge date-window misses (still relevant).
