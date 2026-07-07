# 2026-06-26 Praxis Debrief

**Timestamp:** 06:07Z
**Type:** Manual debrief (cron job)

## Summary

Signal velocity collapsed from 2,220 events (June 17 peak) to ~6/day. 9/12 active shifts are "zombies" from the June 18 rebuild — never reinforced. 27 lessons extracted June 25-26 with `signal_type='?'` (schema regression blocking shift pipeline).

## Key Findings

### Zombie Shifts
7 of 9 active shifts have `reinforcement_count: 0` and no `last_reinforced_at`. All created during June 18 rebuild. Consuming cap space without evidence of ongoing relevance.

### Signal Velocity Collapse
- June 17: 2,220 real-signal events (peak, bulk re-ingestion)
- June 21: 22 real signals
- June 26: 1 real signal
- Could indicate system stability OR ingest pipeline gap

### Schema Regression
27 lessons on June 25 with `signal_type='?'` — post-v3.0 ingest script is producing lessons without signal_type. Blocks shift proposal pipeline entirely.

### Expired Shifts (Correct)
- `tier1_fix_applied` (custodian) — Jun 24, issue resolved
- `tier2_issue` (custodian) — Jun 24, state.db issue resolved

## Debrief Written
`debrief-20260626T060749` appended to `debriefs.jsonl`

## Recommendations Generated
1. Reinforce or expire 7 zombie shifts
2. Fix signal_type schema regression in lesson extraction
3. Consolidate overlapping custodian shifts (4 shifts, identical template)
4. Consider expiring gap_detected (measurement artifact, not behavioral pattern)
5. Monitor signal velocity — if low for 7+ days, check ingest pipeline
