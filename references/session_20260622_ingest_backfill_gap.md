# Session 2026-06-22 Praxis Ingest @ ~14:15Z — Concurrent Cron Backfill Gap

**Trigger:** Scheduled cron job (praxis:journal_ingest)
**Profile:** indigo

## What happened

1. **4 new journals found** via Python mtime comparison with `last_ingest_run: 2026-06-22T13:58:25Z`:
   - `ocas-custodian/2026-06-22/update-070230.json` (type=action, no-op)
   - `ocas-custodian/2026-06-22/light-scan-2026-06-22-070000.json` (type=observation)
   - `ocas-mentor/2026-06-22/mentor-light-20260622T140718Z.json` (success, 0 errors)
   - `ocas-mentor/2026-06-22/mentor-light-20260622T140725Z.json` (success, 0 errors, 0 new files)

2. **Concurrent cron gap discovered:** A concurrent Praxis cron run at `14:13:42Z` had already advanced `last_ingest_run` past these journals' mtimes (~14:07Z) WITHOUT evaluating them. The journals fell through a timing gap — `last_ingest_run` moved forward but the journals were never marked in `journals_evaluated.jsonl`.

3. **All 4 journals correctly filtered as false positives** by pre-filters:
   - 2x mentor-light (success outcome, 0 errors, no gap) → filtered
   - 1x custodian action (no escalation) → filtered  
   - 1x custodian observation → filtered
   - 0 events recorded, 0 lessons, 0 shifts

4. **Backfill script written and executed** to properly mark these 4 journals as evaluated, even though they contained no signals. This prevents the dispatcher from re-detecting them.

## New gotcha: Concurrent cron backfill gap

**Problem:** When two Praxis cron runs execute in close succession (within ~5 minutes), the later-starting run may advance `last_ingest_run` past journals that the earlier run discovered but hadn't yet evaluated. The mtime-based discovery in the second run then finds 0 journals (because `last_ingest_run` is now past their mtime), and the journals are never evaluated.

**Detection:** After completing an ingest run, check if any journals found by mtime comparison are NOT in `journals_evaluated.jsonl`. If the count of "found but not evaluated" is > 0, a backfill is needed.

**Fix pattern:**
```python
# After ingest, verify all mtime-discovered journals are in eval file
evaluated = set()
for e in load_jsonl(EVAL_FILE):
    if isinstance(e, dict):
        evaluated.add(e.get("journal_id", ""))
    elif isinstance(e, str):
        evaluated.add(e)

for jp in new_journal_paths:
    cid = canonical_id_from_path(jp)
    if cid not in evaluated:
        # This journal fell through the gap — write a backfill eval entry
        append_jsonl(EVAL_FILE, {
            "journal_id": cid,
            "evaluated_at": now_iso,
            "action_taken": "backfill",
            "signals_found": 0,
            "reason": "Concurrent cron gap — journal discovered but not evaluated by prior run"
        })
```

**Prevention:** In each ingest run, after writing the initial mtime-based journal list, do a secondary check: scan ALL journals on disk and verify they're either in the eval file or in the "to be evaluated" list. Any that are in neither category are gap victims.

## State transitions
- `last_ingest_run`: 2026-06-22T13:58:25Z → 2026-06-22T14:18:38Z
- `total_ingests`: 9 → 10
- `last_evaluated_count`: 25,411 → 25,417 (+4 backfill + 2 from concurrent run)
- `journals_processed`: 12 → 16 (+4 backfill)
- Active shifts: 12/12 (unchanged)

## Files modified
- `journals_evaluated.jsonl`: +4 backfill entries (all `backfill` action_taken)
- `events.jsonl`: unchanged (0 new events)
- `lessons.jsonl`: unchanged
- `shifts.jsonl`: unchanged
- `ingest_state.json`: timestamp advanced, counts updated
- Praxis journal written to `commons/journals/ocas-praxis/2026-06-22/`

## Scripts cleaned up
- `ingest_cron_20260622_1407.py` (initial ingest script — 0 journals found due to concurrent run)
- `ingest_backfill_20260622_1415.py` (backfill script)
