# Praxis Ingest Run — 2026-05-30T19:50Z

## Session Summary

Scheduled cron journal ingest + lesson extraction pass. No user interaction.

## Pipeline Run

1. **Scan**: 4,742 journal files on disk, 83 new since last evaluation
2. **Event recording**: 18 events after dedup (from 83 new journals)
3. **Lesson extraction**: 54 total lessons after extraction, 21 new (10 real, 11 noise)
4. **Shift activation**: 13 proposed → activated, then 11 expired to enforce 12/12 cap
5. **Final state**: 12 active / 12 cap, 51 lessons (11 noise-rejected), 164 events

## Key Findings

### Lesson Inference Quality Issue (NEW)
The `infer_cause()` and `infer_conditions()` functions in the extraction script always return non-empty strings for any input. This caused 21 lessons to all be marked `confidence: high`, producing 13 generic shifts. 11 legacy shifts had to be expired to compensate.

Fix: These functions must return None when domain is not a real skill name or failure_phase is None/null. Only patterns with (real skill domain) AND (specific failure phase in {planning, execution, response}) AND (specific error keywords in summary) should produce high confidence.

### Unknown Domain Noise Floor
11 of 21 extracted lessons (52%) came from unknown domain events — journals where the skill couldn't be identified. Filter at extraction time, not post-hoc.

### Cross-Skill Phase Lessons Too Generic
Cross-skill groups (66 events in execution phase across 20+ skills) produce observations, not actionable shifts. These should be confidence: low and never produce shifts.

### Cap Enforcement Worked
The cap enforcement pass correctly expired 11 lower-priority shifts to maintain 12/12 compliance.

## Data State After Run
- Events: 164
- Lessons: 51 (10 new real, 11 new rejected as noise, 30 pre-existing)
- Shifts: 26 total, 12 active, 3 proposed, 11 expired
- Evaluated journals: 5,054
