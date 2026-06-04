# Praxis Lesson Extraction Rules

## When to extract
- **Default**: 2+ events with the same failure pattern (config `lessons.min_pattern_count: 2`)
- **Failure-phase pattern**: 2+ events in the SAME failure phase (planning,
  execution, or response) — this triggers a phase-specific shift because the diagnostic signal is sharper
- User corrected the same type of issue (N=1 is sufficient for user corrections — config `lessons.user_correction_min_count: 1`)
- Outcome caused visible friction across multiple runs
- Outcome revealed a stable preference or operating constraint
- Outcome strongly improved quality or reliability when applied consistently
- **Escalation signals**: Any event with `signal_type: "escalation"` and a new
  fingerprint not seen before — record as pattern-seed event; extract lesson
  immediately on second occurrence (override min_pattern_count for escalations)
## When NOT to extract

- One-off trivia
- Emotionally loaded but behaviorally vague exchanges
- Abstract aspirations with no execution consequence
- Domain facts that belong in normal memory (Elephas)
- **Single events** — still require minimum pattern count before producing a shift (record the event but don't shift behavior on a single data point)
- **Reinforced stale shifts** — if a shift was recently reinforced, don't extract overlapping lessons that would create duplicate active shifts
- **Legacy events with unknown signal type** — events with `signal_type` of `"unknown"`, `"?"`, `None`, or `""` are from pre-v3.0 journal schemas. They carry no meaningful failure-phase or error-type information. Skip them during pattern grouping entirely. In production, legacy events from ocas-custodian (42), ocas-elephas (22), and ocas-mentor (12) all had `signal_type: "?"` and generated 3 useless low-confidence lessons per ingest cycle until this filter was added.

## Elaborative interrogation requirements

Every extracted lesson MUST include causal grounding. Without it, the lesson
is marked `confidence: low` and held for additional evidence.

Required fields:
- **What**: What pattern of failure/success was observed?
- **Why**: Why did this pattern emerge? What's the causal mechanism?
- **When**: Under what conditions does this apply? What are boundary conditions?

Format:
```
[LESSON] What: <pattern>. Why: <cause>. When: <conditions>
```

Example (low confidence — rejected):
```
What: Don't use curl for API calls.
Why: (missing)
When: (missing)
```

Example (high confidence — accepted):
```
What: Don't use curl for GitHub API calls.
Why: curl requests to api.github.com get flagged as data exfiltration by the
security scanner, causing false positives that block skill publication.
When: Any GitHub API interaction — fetching releases, querying issues, reading
repo metadata. Applies specifically when the skill auditor runs agentskill.sh.
```

## Minimum pattern count by confidence

| Confidence | Min events | Notes |
|------------|------------|-------|
| **high** | 2+ with full causal grounding (what+why+when) | OR 2+ in same failure phase with specific error-type keywords |
| **med** | 2+ with partial grounding (what+why, no when) | Held for 1 more cycle to gather boundary conditions |
| **low** | 2 with only "what" | Held for 2 more cycles. If no "why" emerges, rejected. |

**Config reference**: `lessons.min_pattern_count: 2` (v3.0.0). Lowered from 3 in v2.x because empirically, 2 same-phase events with specific causal content produce better shifts than 3 generic events.

**Escalation override**: Events with `signal_type: "escalation"` and a new fingerprint bypass min_pattern_count — extract lesson on 2nd occurrence of same fingerprint (not 1st, to confirm it's not transient).

## Phase-aligned extraction

When extracting from failure events, the lesson should target the correct phase:

| Failure phase | Lesson should target | Example |
|---------------|---------------------|---------|
| **Planning** | Preconditions, assumption verification | "Before writing code, verify the API schema exists" |
| **Execution** | Tool usage, parameter validation | "When calling X tool, validate Y parameter first" |
| **Response** | Output formatting, verbosity, tone | "For technical questions, lead with code example" |

Mixing phase targeting (e.g., a planning failure generating an execution-phase shift)
produces ineffective lessons. The shift must address the phase where the failure occurred.
