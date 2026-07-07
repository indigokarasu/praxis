# Praxis Debrief Templates

## Structure
1. What happened (event summary)
2. What lesson was extracted or rejected (with causal grounding assessment)
3. Whether any active behavior changed (including phase targeting)
4. What remains tentative
5. Shift decay status (new in v2.8.0)

## Tone
- Concise and operational
- Understandable to a human reviewer
- Free of chain-of-thought reasoning dumps
- Honest about uncertainty

## Debrief template

```
# Praxis Debrief — {date} ({time} UTC)

## System Status

| Metric | Value |
|--------|-------|
| Total events recorded | {N} |
| Active shifts | {N} (cap: 12, headroom: {N}) |
| Shifts expired (all time) | {N} |
| Lessons extracted (all time) | {N} |
| Last ingest | {timestamp} ({N} new events) |
| Last event recorded | {timestamp} ({domain}/{signal}) |

## Active Shifts ({N}/12)

| # | Shift | Domain | Signal | Phase | Created | Age | Reinforcements |
|---|-------|--------|--------|-------|---------|-----|----------------|
| 1 | {shift_id} | {domain} | {signal} | {phase} | {date} | {N} days | {N} |

**⚠ Decay alert:** Note any shifts approaching 14-day TTL with 0 reinforcements.

## Decay Check

- **Shifts past threshold:** {N}
- **Borderline (10-13 days, 0 reinforces):** {N} — list them
- **Pattern status:** Are the signal types still occurring or have they gone quiet?

## Consolidation Check

**Overlaps found:** {N} — detail any shifts sharing (domain, signal_type, phase) tuples.

## Recent Activity (Last 7 Days)

| Date | Events | Notes |
|------|--------|-------|
| {date} | {N} | {summary} |

## Open Questions

{Carry forward from prior debriefs, mark resolved ones}

## Recommendations

{Actionable items: monitor patterns, let shifts expire, investigate gaps}
```

## Causal grounding assessment
For each lesson, explicitly rate the grounding:
- **Full** (what+why+when): Lesson can produce a shift immediately
- **Partial** (what+why): Held for one more cycle to gather boundary conditions
- **Minimal** (what only): Held for two more cycles; rejected if no "why" emerges

## Phase alignment check
For each activated shift, verify:
- Does the shift target the correct failure phase?
- A planning failure should produce a precondition-check shift, not an execution constraint
- Mixed-phase shifts should be split into separate phase-specific shifts
