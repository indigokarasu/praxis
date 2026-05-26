# Praxis Runtime Rules

## Runtime Brief Format
The runtime brief is a compact list of active behavior shifts. It is injected into the agent's operational context.

Target size: 3-12 items. Each item: one imperative sentence.

Example:
1. When uploaded files are present, inspect them before asking clarifying questions.
2. For technical questions, provide code examples alongside explanations.
3. When scheduling, check calendar conflicts before proposing times.

## Context-aware formatting (v2.8.0)

Shifts should include their failure phase and reinforcement status when relevant. This helps the agent apply the right shift at the right time:

### Phase-tagged format
For shifts with a failure phase, prefix with the phase tag:

```
[PLAN] Before writing code, verify the API schema exists.
[EXEC] When calling gh api, validate the response status before parsing.
[RESP] For technical questions, lead with code example, not explanation.
```

### Reinforcement-aware application
- Shifts with `reinforcement_count >= 3` are "consolidated" — apply them automatically.
- Shifts with `reinforcement_count = 1-2` are "provisional" — apply but be ready to adjust.
- Shifts approaching `stale_days` threshold — apply but note uncertainty.

### Elaborative context
For high-confidence shifts (causal grounding = what+why+when), include the "why" as a comment in the brief so the agent understands the principle, not just the rule:

```
[PLAN] Before writing code, verify the API schema exists.
  → Why: Planning failures from missing prerequisites caused 3+ execution errors.
  → When: Any task involving external APIs or unfamiliar libraries.
```

## What the runtime brief is NOT
- A narrative log of learning history
- A personality description
- A list of every lesson ever extracted
- A list of expired or stale shifts (only active shifts appear)

## Stale shift handling
Shifts flagged as stale (not reinforced in 7+ days) are included in the brief with a `[STALE]` prefix. The agent should:
1. Still apply them if the context matches
2. Note in the next debrief whether the shift was still relevant
3. If the shift was NOT relevant, that's evidence for expiry

This creates a natural test: stale shifts that prove irrelevant get expired. Stale shifts that prove relevant get reinforced and return to full active status.
