# Session 2026-06-30: Decay Check — Stale Proposed Shift Cleanup

## Summary

Scheduled decay check (noon cron) discovered 15 proposed shifts stuck in `proposed` status for 11 days since the 2026-06-18 rebuild. None had been activated. All expired in a single cleanup pass.

## Discovery

After the standard active-shift decay scan (3 active shifts, all healthy — reinforced 2 days ago), a count of remaining `proposed` shifts revealed 15 entries:

- All created `2026-06-18T12:07:25Z` (bulk rebuild batch)
- Age: 11 days at time of check
- Source events: ranged 0–12 (many had 0 events — pure noise proposals)
- None had ever been activated or reinforced

## Root Cause

The 2026-06-18 Praxis rebuild bulk-proposed shifts from historical lesson data but never activated them. The decay check at that time only scanned `active` shifts — proposed shifts were invisible to the decay logic. They sat in limbo indefinitely.

## Cleanup Action

Expired all 15 with:
```json
{
  "status": "expired",
  "expired_at": "2026-06-30T10:04:26Z",
  "expire_reason": "decay_check: proposed shift never activated after 11 days; Stale since rebuild 2026-06-18"
}
```

Used full file rewrite from canonical in-memory state (not append-only) to ensure status changes persisted correctly.

## Lesson

**Proposed shifts need a TTL.** The existing decay logic only covers `active` shifts (14-day reinforcement window). Proposed shifts that never get activated accumulate as dead weight in `shifts.jsonl`. The decay check should include a proposed-shift scan with a 10-day TTL.

## Pattern for Future Runs

When running `praxis:decay_check`:
1. After scanning active shifts, run: `grep -c '"status": "proposed"' shifts.jsonl`
2. If >0, check age of each proposed shift (from `created_at` or `proposed_at`)
3. Expire any proposed shift ≥10 days old that was never activated
4. Log count in journal and update `ingest_state.json:stale_proposed_expired`
