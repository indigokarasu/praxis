# Praxis Session — 2026-06-14 Debrief Cron

## Summary
Full Praxis debrief + decay/consolidation pass. No new events since June 2. All active shifts approaching decay.

## System State
- Events: 244 total, 0 in last 7 days
- Lessons: 26 (cleaned from 49 — removed 23 with empty/unknown signal_type)
- Shifts: 11 active / 2 proposed / 2 expired / 8 merged
- Cap: 11/12
- Journals: 6,660 total, 1,651 unevaluated

## Actions Taken
1. Generated full debrief (debrief-review-20260614T060815)
2. Cleaned 23 malformed lessons (empty/unknown signal_type)
3. Updated `last_reinforced_at` on shifts missing the field
4. No shifts expired (all at 12-13 days, TTL=14)
5. No merges needed (no domain+phase overlaps among active shifts)

## Key Findings
- **All 11 active shifts are stale**: 12-13 days old, 0 reinforcements. Will hit 14-day TTL in 1-2 days.
- **Quiet period**: No new events since June 2. Either system is healthy or journal ingestion is not running.
- **1,651 unevaluated journals**: Signals may be accumulating unseen.
- **2 proposed shifts** pending activation review (ocas-spot/execution, ocas-sands/execution).

## Quality Issues
- 2 active shifts have empty domain (`?` or `""`) — poorly targeted
- 2 active shifts have vague text ("Improve execution-phase handling") — not actionable
- praxis_review.py has wrong hardcoded DATA_DIR (fixed in gotchas)

## Files Modified
- `lessons.jsonl` — removed 23 malformed entries
- `shifts.jsonl` — added `last_reinforced_at` to shifts missing it
- `debriefs.jsonl` — appended debrief-review-20260614T060815
- `decisions.jsonl` — appended decay+consolidation decision
- `evidence.jsonl` — appended evidence record
- `references/gotchas-praxis.md` — added praxis_review.py path bug, lesson accumulation note
- `SKILL.md` — added data directory path section, updated decay description
- `references/session_20260614_debrief.md` — this file
