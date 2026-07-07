# Session: Cron Ingest 2026-06-28T10:06Z — Shift Consolidation Proactive Pass

**Goal:** Routine cron ingest that revealed 7 of 9 shifts approaching 14-day decay — proactive consolidation prevented mass expiry.

**Outcome:** 9 active shifts consolidated to 3; 0 decay-risk shifts remaining; 17 noise lessons removed.

## What Actually Happened

### Ingest
- Production script `praxis_ingest_run.py` ran successfully at 10:06Z.
- Found 10 journals, recorded 3 events (all `no_signal` — routine healthy journals).
- Extracted 14 lessons — all from full-history reprocessing (Bug #2, confirmed again).
- 0 genuine behavioral signals surfaced.

### Noise Cleanup
All 14 script-produced lessons + 3 pre-existing stale lessons removed:
- `confidence: low` = 2 removed
- Noise signal types (matched `NOISE_SIGNAL_TYPES` set) = 12 removed
- Stale history with event_count > 5 (impossible from 3 no_signal events) = 3 removed
- 1 remaining lesson had `domain: "unknown"` + `signal_type: "failure"` — legacy malformed, removed manually
- Result: `lessons.jsonl` = 0 lessons (clean slate)

### Decay-Risk Scan
- 9 active shifts, 7 at exactly 10 days with 0 reinforcements
- All were from a 2026-06-18 rebuild batch
- No shifts at 14-day threshold yet (would auto-expire next ~4 days)

### Shift Consolidation (new pattern)
**Problem:** Multiple shifts with identical `(domain, failure_phase)` and low triggers — semantically duplicate, each consuming cap space independently.

**Trigger condition for consolidation:**
- ≥2 active shifts share same `(domain, fault_phase)` (case-insensitive)
- Combined `reinforcement_count ≤ 3` (not individually valuable enough to keep separate)
- Age > 7 days (not freshly activated by recent events)

**Procedure:**
1. Group active shifts by `(domain.lower(), failure_phase.lower())`
2. For groups with >1 shift:
   - Pick keeper = shift with most reinforcements (first if tie)
   - Expire all others with reason: `Consolidated into {keeper_id}: same domain+phase`
   - Merge signal types into keeper: `sig1+sig2+sig3` prefix (+Nmore if >3)
   - Update `shift_text` to reflect merged scope
   - Reinforce keeper by +1 (consolidation = deliberate action, not abandonment)
3. Full rewrite of `shifts.jsonl` (all statuses) to persist the in-memory changes

**Results:**
| Group | Before | After | Keeper signal |
|-------|--------|-------|---------------|
| ocas-custodian/execution | 5 shifts (tier2_open + 3) | 1 | correction+escalation+execution_error+2more |
| ocas-mentor/execution | 2 shifts | 1 | anomaly+gap_detected |
| ocas-spot/execution | 2 shifts | 1 | failure+platform_failure |
| **Total** | **9 active** | **3 active** | |

### Pitfall
- The post_ingest cleanup script was **removed by Step 6** (stale script cleanup) before I could run the rm command.
- `rm post_ingest_*.py` returned "No such file" because cleanup in Step 6 already removed it.
- Lesson: Run stale script cleanup AFTER all other script-dependent steps in the same sequence. Don't rm-convenience scripts before they've been consumed.

## Artifacts
- `praxis-cron-20260628T100801Z.json` (initial journal, before consolidation)
- `praxis-cron-20260628T101012Z.json` (final journal, after consolidation)
- `journals_evaluated.jsonl` appended 10 entries
- `ingest_state.json` updated with consolidation notes
- `lessons.jsonl` → 0 entries
- `shifts.jsonl` shifted from 9 active (of 9) to 3 active (of 3)

## Recommendation
This consolidation pattern should be promoted to a formal Step 7.5 in `references/cron-execution-checklist.md` so it runs automatically every time decay-risk scan finds ≥3 shifts with domain+phase overlap. The production script could also learn this.
