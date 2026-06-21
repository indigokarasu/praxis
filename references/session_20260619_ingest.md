# Session 2026-06-19: Praxis Journal Ingest + Shift/Lesson Cleanup

## Key Findings

### Dual Journal Directory Paths
Journals are split across TWO directories:
- `/root/.hermes/commons/journals/` — legacy/default profile (forge, finch, spot)
- `/root/.hermes/profiles/indigo/commons/journals/` — indigo profile (custodian, mentor, others)

**11 unevaluated journals found on 2026-06-19:**
- Legacy: `ocas-finch/scan-2210`, `ocas-forge` x 2, `ocas-spot/sweep-cron`
- Indigo: `ocas-custodian/light`, `ocas-mentor/mentor-light` x 6

A script using only one path misses half the signals.

### New Signal
- `tier_2_open` from `ocas-custodian` — 2 known Tier 2 issues persisting:
  1. `oc_checkpoint_store_git_corrupted` — 94 errors/day
  2. `oc_context_engine_chronicle_session_lookup_noise` — known false positive

### Shift Cap Bug
The ingest script expired one shift in-memory but the new shift was still appended,
resulting in 13 active (1 over cap). The expired shift's status change wasn't persisted
back to disk because only new shifts were appended.

**Fix:** Full rewrite of `shifts.jsonl` from canonical in-memory state after all
modifications, not append-only. See `shift-cap-repair.md`.

### Cleanup Actions
1. **Shifts**: 13 -> 11 active
   - Expired 55 proposed with domain=unknown (ingest artifacts)
   - Expired 1 low_coverage (measurement artifact)
   - Expired 1 active with domain=unknown
2. **Lessons**: 89 -> 72
   - Removed 17 with empty/None signal_type

### Data State After Cleanup
- Active shifts: 11/12 (1 slot free)
- Lessons: 72 (semantically unique)
- Events: 2,519 total
