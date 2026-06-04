# Session: 2026-05-31 Praxis Journal Ingest (cron)

## Run metadata
- **Time**: 2026-05-31T04:46:43Z
- **Type**: Scheduled cron (praxis:journal_ingest)
- **Trigger**: Automatic 30-min cron cycle

## What happened

### Journal scan
- 4,784 total journal files on disk
- 5,111 unique entries in `journals_evaluated.jsonl` (after dedup: 1 duplicate removed)
- 0 new journals from today (2026-05-31) or yesterday (2026-05-30)
- 2 journals were processed in a **partial prior run** that crashed at lesson extraction (NameError: `signal_count` undefined) — already evaluated, event already written

### First partial run (crashed)
- Processed: `ocas-custodian/2026-05-30/light-scan-20260531-041316.json` → 1 event (escalation, high)
- Processed: `ocas-spot/2026-05-31/spot-20260531-1000-sweep.json` → no signal
- Bug: `NameError: name 'signal_count' is not defined` at lesson extraction line ~452

### Fix + second run (this session)
- Fixed variable name typo in `/tmp/praxis_ingest_run.py`
- Rewrote entire script as `praxis_ingest_run.py` with proper error handling
- Script copied to `skills/ocas-praxis/scripts/praxis_ingest_run.py`

### Lesson extraction
- 3 lessons auto-extracted by pattern_grouper — all `confidence: low`, all `pattern_key: "unknown"`
- Root cause: legacy events (42 custodian, 22 elephas, 12 mentor) use old schema with `signal_type: "?"` → grouped as `"unknown"`
- All 3 noise lessons **removed** (62 lessons remain, 0 with unknown pattern_key)
- **Fix applied**: added `signal_type` filter in lesson extraction to skip `unknown`/`?`/empty keys

### Data state
| File | Records |
|------|---------|
| events.jsonl | 126 |
| lessons.jsonl | 62 |
| shifts.jsonl | 29 (11 active, 18 expired, 0 proposed) |
| journals_evaluated.jsonl | 5,113 entries, 0 duplicates |

### Shift analysis
- 11/12 active slots used
- **Semantic flooding still present**: 5 active shifts are near-identical "verify preconditions" variants:
  - `ocas-custodian/planning` (rc=1)
  - `ocas-custodian/execution` (rc=1)  
  - `ocas-mentor/planning` (rc=1)
  - `ocas-mentor/execution` (rc=0)
  - Generic custodian planning (rc=1) and execution (rc=1)
- These 5 should consolidate to 1-2 cross-skill shifts, freeing 3-4 slots
- **No autonomous consolidation performed** — flagged for debrief recommendation

## Gotchas encountered
1. **Script re-execution after partial crash**: First run wrote events+eval entries before crashing. Second run's eval check correctly found them already evaluated (safe dedup). The post-write dedup in first run was never reached — the 1 new event has no dupes.
2. **`write_file` overwrites praxis_ingest_run.py**: The script file at `/root/.hermes/skills/ocas-praxis/scripts/praxis_ingest_run.py` was safely overwritten (same content). No data files were affected.

## Files modified
- `/root/.hermes/commons/data/ocas-praxis/events.jsonl` — 1 new event (escalation from custodian)
- `/root/.hermes/commons/data/ocas-praxis/journals_evaluated.jsonl` — 2 new eval entries, 1 dup removed
- `/root/.hermes/commons/data/ocas-praxis/lessons.jsonl` — 3 noise lessons extracted then removed
- `/root/.hermes/commons/data/ocas-praxis/evidence.jsonl` — 1 new evidence record
- `/root/.hermes/skills/ocas-praxis/scripts/praxis_ingest_run.py` — rewritten with bug fix + unknown filter
- `/root/.hermes/commons/journals/ocas-praxis/2026-05-31/ingest_20260531044643.json` — this journal
