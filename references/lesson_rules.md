# Praxis Lesson Extraction Rules

## When to extract
- Same failure pattern repeated 3+ times (raised from 2 — cognitive science shows
  3+ occurrences are needed for reliable pattern detection and to avoid
  overfitting to noise)
- User corrected the same type of issue 3+ times
- Outcome caused visible friction across multiple runs
- Outcome revealed a stable preference or operating constraint
- Outcome strongly improved quality or reliability when applied consistently
- **Failure-phase pattern**: 2+ events in the SAME failure phase (planning,
  execution, or response) — this triggers a phase-specific shift even at the
  lower threshold because the diagnostic signal is sharper

## When NOT to extract
- One-off trivia
- Emotionally loaded but behaviorally vague exchanges
- Abstract aspirations with no execution consequence
- Domain facts that belong in normal memory (Elephas)
- **Single events** — still require minimum pattern count before producing a
  shift (record the event but don't shift behavior on a single data point)
- **Reinforced stale shifts** — if a shift was recently reinforced, don't
  extract overlapping lessons that would create duplicate active shifts

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
| **high** | 3+ with causal grounding | OR 2+ in same failure phase |
| **med** | 3+ without causal grounding | Held for 1 more cycle to gather "why" |
| **low** | 2 without causal grounding | Held for 2 more cycles. If no "why" emerges, rejected. |

## Phase-aligned extraction

When extracting from failure events, the lesson should target the correct phase:

| Failure phase | Lesson should target | Example |
|---------------|---------------------|---------|
| **Planning** | Preconditions, assumption verification | "Before writing code, verify the API schema exists" |
| **Execution** | Tool usage, parameter validation | "When calling X tool, validate Y parameter first" |
| **Response** | Output formatting, verbosity, tone | "For technical questions, lead with code example" |

Mixing phase targeting (e.g., a planning failure generating an execution-phase shift)
produces ineffective lessons. The shift must address the phase where the failure occurred.
