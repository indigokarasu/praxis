# Session 2026-06-16 Ingest — New Gotchas

## 1. `events.jsonl` Dual Schema: `outcome_type` vs `signal_type`

**Discovered:** 2026-06-16 during v4→v5 ingest script iteration.

**Problem:** `events.jsonl` contains two distinct event schemas:
- **Legacy (pre-2026-06-15):** Uses `outcome_type` + `domain` + `source_journal`. No `signal_type` key, no `skill` key.
- **Current:** Uses `signal_type` + `skill` + `source_journal`.

Direct `evt["signal_type"]` access crashes with `KeyError` on legacy events during lesson extraction.

**Fix:** Define a normalization helper at the top of every ingest script:
```python
def get_signal_type(evt):
    return evt.get("signal_type") or evt.get("outcome_type") or "unknown"
```
Use this helper for ALL event grouping, filtering, and lesson extraction — never access `evt["signal_type"]` directly.

**Related:** The existing gotcha "Legacy events use `id` instead of `event_id`" covers ID field variance. This gotcha covers the *naming* split for the signal classification field — a separate schema dimension.

## 2. Forge Journal Double-Nested Path Canonicalization

**Discovered:** 2026-06-16 during v4 ingest.

**Problem:** Some forge cron jobs write journals to paths like `ocas-forge/r_20260616_journal-scan-1781597158.json/r_20260616_journal-scan-1781597158.json`. The canonical ID computation `f"{skill}/{date_dir}/{fname}"` produces a double-nested path because the `r_` prefix directory name matches the filename.

**Impact:** Eval entries have non-canonical IDs. On re-scan, the same file gets a different canonical ID, causing re-evaluation.

**Fix:** When computing canonical IDs, normalize by taking only the last two path components after the skill directory:
```python
path_parts = rel_path.split('/')
if len(path_parts) >= 3:
    skill = path_parts[0]
    fname = path_parts[-1]
    date_dir = path_parts[-2]
    canonical = f"{skill}/{date_dir}/{fname}"
```

## 3. Evidence Record Gap from Partial Crash

**Discovered:** 2026-06-16 when v4 crashed between eval append and evidence write.

**Problem:** If the ingest script crashes after writing eval entries to `journals_evaluated.jsonl` but before writing the evidence record, the audit trail is incomplete. Journals are marked as evaluated (won't be re-scanned) but no evidence record exists for the run.

**Fix:** Write the evidence record as early as possible — immediately after signal extraction completes, BEFORE lesson extraction or eval entry appends. The evidence should be the first JSONL append of the run, not the last.

**Recovery:** If this happens, write a retroactive evidence record with a `notes` field explaining the crash. Do NOT re-process journals (they're already evaluated). Do NOT re-extract events (they may or may not have been written — check `events.jsonl` for the run_id).
