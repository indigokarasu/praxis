# 2026-06-16 Praxis Journal Ingest

## Summary
- 16 new journals: 7 parsed, 9 malformed (all ocas-mentor)
- 2 new events (no_op, no_active_watches) — both routine, no lessons warranted
- Active shifts: 12/12 (at cap, no changes)

## Malformed Mentor Journals — Detailed Log

9 ocas-mentor journals could not be parsed. Root causes by category:

### Shell template variables not resolved (4 files)
Files containing `$(python3 -c "...")` that was not expanded:
- `ocas-mentor/2026-06-06/mentor-light-20260606T035357Z.json` — `timestamp` field contains literal `$(python3 -c "from datetime...")`
- `ocas-mentor/2026-06-06/mentor-light-20260606T214328Z.json` — similar template issue
- `ocas-mentor/2026-06-07/.json` — same pattern
- `ocas-mentor/2026-06-07/mentor-light-20260607T093727Z.json` — same pattern

### Placeholder values (2 files)
Template-expanded but placeholders not replaced:
- `ocas-mentor/2026-06-07/.json` — `RUN_ID_PLACEHOLDER`, empty run_id/timestamp
- `ocas-mentor/2026-06-14/.json` — `RUN_ID_PLACEHOLDER`, `TIMESTAMP_PLACEHOLDER`, `TOTAL_3D_PLACEHOLDER`, etc.

### Control characters (1 file)
- `ocas-mentor/2026-06-14/mentor-light-20260614T115612Z-caller.json` — raw control chars in caller-written journal

### Empty file (1 file)
- `ocas-mentor/2026-06-15/mentor-light-20260615T204918Z-caller.json` — 0 bytes

### Multi-document JSON (1 file)
- `ocas-mentor/2026-06-12/mentor-light-20260613T021940Z.json` — valid JSON followed by extra data (second JSON object or trailing content)

## Root Cause Analysis
The ocas-mentor lightweight heartbeat script writes JSON templates with embedded shell command substitution for dynamic fields (timestamps, run IDs). When the primary Python `json.dump()` write path fails (the known "dual failure" pattern where both evidence and ingestion writes fail), the fallback shell `cat >` writes don't resolve all `$()` expressions. This produces journals that are structurally present but semantically unparseable.

### Recommendation
This is an ocas-mentor journal production issue, not a Praxis issue. Future Praxis ingest runs should:
1. Catch `json.JSONDecodeError` per-journal (already standard practice)
2. Count malformed journals by skill for trend tracking
3. NOT treat malformed journals as Praxis errors or data quality failures

## 02:09 UTC — Cron Ingest (prior session)

- 8 new journals, 0 malformed, 0 errors
- 5 events created: 4 routine forge no-ops, 1 self-referential ingest entry
- No new lessons or shifts warranted
- Active shifts: 12/12 (at cap, no changes)
- Proposed shifts pending: 27 (blocked by cap)

### Data Hygiene Flag

## 04:11 UTC — Cron Ingest (this session, second pass)

- 8 new journals found: 7 forge no-ops + 1 spot_error (all watches inactive)
- 1 event extracted, 13 lessons (6 legitimate, 7 noise), 0 new active shifts (cap 12/12)
- Malformed cleanup: 0 (clean from prior run)
- **Critical: `write_file` destroyed `journals_evaluated.jsonl`** — second occurrence of this gotcha (first was 2026-06-15). Recovery: rebuilt from filesystem scan.
- **Event schema normalization** — Pre-2026-06-15 events use different field names (`type`/`summary`/`source_skill` vs `signal_type`/`evidence`/`skill`). Lesson extractor must normalize all events before grouping.
- **Lesson noise floor** — 7/13 new lessons were noise (`no_op`, `forge_activity`, `routine`, `unknown`, `no_active_watches`). The lesson extractor creates lessons for any uncovered (signal_type, phase) group without quality filtering.
- `journals_evaluated.jsonl` has ~7,871 entries for only ~2,348 actual journal files on disk (3.4x ratio)
- Dedup keeps entries with and without `.json` extension as separate entries
- Compaction at >5,000 entries should trigger more aggressively, or dedup normalization (canonicalize IDs to always include `.json`) should be applied before compaction check
- No action taken this run — flagged for future compaction pass
