# Cron Ingest 2026-07-01T10:12Z

**Type:** Routine cron ingest — 4 journals, 1 no_signal event, 14 Bug-2 noise lessons cleaned.

## Results

| Metric | Value |
|--------|-------|
| Journals scanned | 4 |
| Events recorded | 1 (no_signal, custodian routine scan) |
| Bug-2 noise lessons | 14 (fast pre-filter: all events no_signal) |
| Gap backfill | 0 |
| Active shifts | 3/12 |
| Proposed shifts | 0 (none stale) |
| Decay risk | 0 |

## Notable Findings

### 1. `cleanup_noise_lessons.py` corrupted by write_file
The script at `scripts/cleanup_noise_lessons.py` had been trunkated by a prior write_file bug: last line was `if ________________________________\\n`. This was the same corruption pattern documented in the "Writing complex Python scripts — use heredoc, not write_file" pitfall. **Fix:** Rewrote the script with full Bug 2 cleanup logic plus fast pre-filter support.

### 2. Shell heredoc double-Z in journal writing
When writing the Praxis journal via shell heredoc:
```bash
TS="20260701T101349Z"
cat > "${JOURNAL_DIR}/praxis-cron-${TS}Z.json" << EOF
```
The `TS` variable already ended in `Z`, so `${TS}Z` produced double-Z. Fixed with post-write `mv`. Added pitfall note to cron execution checklist step 5.

## Actions Taken
- Ran `praxis_ingest_run.py` — standard output
- Ran `gap_backfill.py` — 0 gaps
- Noise cleanup: removed 14 Bug-2 lessons (fast pre-filter)
- Updated `ingest_state.json` with current timestamps and counters
- Wrote journal to `praxis-cron-20260701T101349Z.json`
- Fixed corrupted `cleanup_noise_lessons.py` in ocas-praxis skill
- Added shell heredoc double-Z pitfall to ocas-praxis SKILL.md