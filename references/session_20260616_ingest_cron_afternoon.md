# 2026-06-16 Praxis Journal Ingest — Afternoon Cron Run

## Summary
- 2352 journal files on disk, 2391 evaluated entries
- 14 unevaluated journals found and processed
- 1 event extracted (parse_error — script bug, not behavioral)
- 0 new lessons, 0 new shift proposals
- Active shifts: 12/12 (at cap, no changes)
- Malformed: 0

## Key Finding: Forge `files_processed` Type Mismatch Bug

The ingest script's forge handler checked `journal_data.get("files_processed", 0) > 0` to detect forge activity. However, the `files_processed` field in forge journals is a **list** (of processed file paths), not an integer. This caused a `TypeError: '>' not supported between instances of 'list' and 'int'` inside the `extract_signals` function, which was caught by the outer `except Exception` handler and emitted as a `parse_error` event.

**The journal itself was a routine no-op** (`result: "no-op"`, `files_processed: [...]`) that should have been caught by the forge no-op handler and returned as `no_signal`.

**Fix:** The forge activity detection in `extract_signals` should either:
1. Check `isinstance(journal_data.get("files_processed"), list) and len(journal_data["files_processed"]) > 0`, OR
2. Remove the `files_processed` check entirely — the `result` field already distinguishes no-op from activity.

**This is a self-inflicted ingest script bug, NOT a behavioral signal.** The emitted `parse_error` event should be ignored.

## Other Observations

1. **13 no-signal journals** — all routine: forge no-ops, spot sweeps, mentor degraded-mode scans. Correctly filtered.

2. **No new behavioral patterns** — all 14 journals covered by existing lesson/shift coverage.

3. **Cap holds at 12** — no merge or expiry needed. All shifts 0-2 days old.

4. **System operating in steady state** — consistent with prior cron runs today (02:09, 04:11, 05:36).
