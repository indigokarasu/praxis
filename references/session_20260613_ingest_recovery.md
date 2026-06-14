# Session 2026-06-13 — Ingest Cron Recovery

## What happened

The ingest cron ran with a buggy script that had two issues:

1. **Function return value mismatch**: `extract_signals_from_dict` returned 3 values `(signals, summary, status)` but the list-format handler in `extract_signals` tried to unpack 4: `entry_signals, entry_summary, entry_status, _ = extract_signals_from_dict(entry)`. This caused `ValueError: not enough values to unpack (expected 4, got 3)` for every journal.

2. **Forge no-op detection incomplete**: The script only checked for `result: "no_op"` but forge also uses `result: "clean"` and longer variants like `"clean — no pending VariantProposal or VariantDecision files"`.

## Recovery steps taken

1. Ran the buggy script → 5 journals marked as "error" in `journals_evaluated.jsonl`
2. Fixed the script (consistent return values, `FORGE_NO_OP_RESULTS = {"no_op", "clean"}`)
3. Removed the 5 error entries from `journals_evaluated.jsonl`
4. Re-ran the fixed script → all 5 journals correctly classified as `no_signal`
   - 2 forge journals: routine no-op scans (result: "clean")
   - 3 spot journals: routine observations with all-skipped/deactivated watches

## Key lesson: error entries block re-processing

When a journal is marked with `action_taken: "error"` in `journals_evaluated.jsonl`, it will NOT be re-processed by subsequent ingest runs. The fix is to manually remove error entries before re-running.

## Spot observation all-skipped detection

Spot journals with `type: "Observation"` (capital O) store per-watch results in a `results[]` array. Each result has a `status` field like `"skipped_inactive"`, `"skipped_platform_unavailable"`, or `"deactivated"`. When ALL results have statuses starting with `"skipped"` or `"deactivated"`, the journal is a routine no-op.

The handler must check BOTH:
- The summary string for no-op phrases (existing behavior)
- The `results[]` array for all-skipped status (new in this session)

## Files modified

- `SKILL.md`: Updated forge no-op gotcha to include `result: "clean"` variant
- `references/gotchas-praxis.md`: Added 3 new gotchas (error entries blocking re-processing, function return value mismatch, spot results[] all-skipped detection)
- `scripts/ingest_run_20260613_cron_recovery.py`: Fixed ingest script saved as reference
