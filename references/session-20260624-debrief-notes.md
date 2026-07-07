# Praxis Debrief — Session Notes (2026-06-24)

## Debrief Structure Used

This session (running as a cron job) produced a more detailed debrief than the standard template. The enhanced structure includes:

1. **System Status table** — key metrics at a glance
2. **Active Shifts table** — with age and reinforcement tracking
3. **Decay Check** — specific day counts, pattern status
4. **Consolidation Check** — overlap analysis
5. **Recent Activity (7-day)** — trend table
6. **Open Questions** — carried from prior debriefs
7. **Recommendations** — actionable items

This structure should become the default for future debriefs.

## Key Findings From This Session

- All 4 active shifts are 11 days old with 0 reinforcements
- System has been quiet since June 20 (no new real signals)
- 3,133 total events but only 2,780 in the store (rest are pre-ingest baseline)
- `ingest_state.json:active_shifts_count` (9) doesn't match `shifts.jsonl` active count (4) — see `gotcha_ingest_state_shift_count.md`
- The 14-day TTL will naturally clear shifts by ~2026-06-27 if no reinforcing events appear

## Discrepancy Investigation

The `active_shifts_count` field in `ingest_state.json` is maintained by ingest scripts, not by the debrief workflow. It may include `proposed` entries or use different counting logic. Always verify against `shifts.jsonl`.
