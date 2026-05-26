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
# Praxis Debrief — {date}

## Events recorded: {N}
{List of new events with failure phase tags}

## Lessons extracted: {N}
{List of lessons with causal grounding level}
- [LESSON] What: ... Why: ... When: ... [confidence: high/med/low]
- [REJECTED] What: ... Reason: insufficient grounding / below threshold

## Behavior shifts activated: {N}
- [SHIFT] {shift_text} [phase: planning/execution/response] [reinforcement: Nth application]
- Shift targeting: {which phase this shift addresses}

## Behavior shifts decayed/expired: {N}
- [EXPIRED] {shift_text} Reason: no reinforcement for {N} days
- [REJECTED] {shift_text} Reason: {why rejected}

## Active shift summary
{Current count}/12 active shifts. {N} consolidated (3+ reinforcements). {N} provisional (1-2). {N} stale (approaching expiry).

## Open questions
{What we still don't know — unanswered causal mechanisms, uncertain boundary conditions}
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
