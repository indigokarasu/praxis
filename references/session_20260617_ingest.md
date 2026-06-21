# Session 2026-06-17: Praxis Journal Ingest — Complete Loop Run

## Summary
Full Praxis loop executed: journal ingest → lesson extraction → shift proposal/activation → daily debrief.
All four steps completed successfully with multiple bug fixes applied inline.

## Key Learnings / New Gotchas

### 1. Cap Enforcement via Priority Selection (Not Churn)
**Problem:** First shift activation script activated shifts in proposal order and expired newly added shifts when cap was reached, losing high-value shifts (execution_error with 19 reinforcements).

**Fix:** Build candidate pool of ALL shifts (existing active + proposed), rank by priority tuple:
```python
(reinforcement_count, source_event_count, is_cross_skill, last_reinforced)
```
Select top 12, expire the rest. Use separate `active_count` counter computed ONCE before loop.

### 2. Noise Signal Types Must Be Filtered at Lesson Creation
**Problem:** 2026-06-17 ingest produced noise lessons (`forge_no_unprocessed_files`, `forge_no-op`, `cron_healthy`, `journal_entry`, `mentor_light`, `success`) with `confidence: high` that then produced shifts.

**Fix:** Apply `NOISE_SIGNAL_TYPES` filter immediately after Pass 2 grounding, BEFORE writing to `lessons.jsonl`.

### 3. New Noise Signal Types to Add to `NOISE_SIGNAL_TYPES`
- `forge_no_unprocessed_files` — Forge routine no-op with natural language result
- `forge_no-op` — Forge no-op with hyphenated result  
- `cron_healthy` — Routine cron health signal
- `journal_entry` — Routine journal write
- `mentor_light` — Mentor heartbeat signal
- `success` — Legacy outcome_type from pre-2026-06-15 events

### 4. Case-Insensitive Phase Normalization for Shift Overlap
**Problem:** `failure_phase` field has inconsistent casing (`"Execution"` vs `"execution"`, `"Planning"` vs `"planning"`).

**Fix:** Normalize both sides to lowercase before comparison:
```python
normalize_phase = lambda p: str(p).strip().lower()
```

### 5. Cron Ingest Script Pattern Confirmed
The production-proven pattern works reliably:
1. Write Python script to `.py` file via `write_file()`
2. Execute via `terminal(command="python3 /path/to/script.py")`
3. Never use heredoc (`<< 'PYEOF'`) — shell metacharacters break it

### 6. Mentor Malformed Journal Handling
Mentor lightweight heartbeat journals often contain unresolved shell template variables. Catch `json.JSONDecodeError` and log as `malformed: mentor` rather than crashing.

### 7. Forge No-Op Detection Must Use `startswith`
Forge result strings include trailing detail: `"clean — no unprocessed VariantProposal..."`. Exact match fails. Use:
```python
def is_forge_no_op(result_val):
    if not result_val: return False
    r = str(result_val).lower().strip()
    return any(r.startswith(prefix) for prefix in FORGE_NO_OP_RESULTS)
```
Where `FORGE_NO_OP_RESULTS` includes `"no unprocessed"` (with spaces).

### 8. Evidence Record Must Be Written BEFORE Eval Entries
If script crashes after writing eval entries but before evidence, journals are marked evaluated but no evidence record exists. Write evidence immediately after signal extraction completes.

## Metrics
- Journals scanned: 2,892
- Unevaluated: 294 (291 mentor, 1 finch, 1 forge, 1 spot)
- Events extracted: 288 (mentor_light)
- Valid events for lessons: 302 (after null-phase + noise filter)
- New lessons created: 18
- Active shifts: 12/12 (at cap)
- Top shifts by event_count: failure_keyword(60), correction(25), parse_error(11)

## Files Modified
- `/root/ingest_main.py` — journal ingest with noise filtering, dedup, evidence-before-eval
- `/root/lesson_extract.py` — lesson extraction with noise filter, phase validation, content dedup
- `/root/shift_propose_v2.py` — shift proposal with priority-based cap enforcement
- `/root/debrief_gen.py` — daily debrief generation