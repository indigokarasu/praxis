# Journal Ingestion Rules

## Source

Praxis scans all skill journals at `{agent_root}/commons/journals/*/YYYY-MM-DD/`. Every skill writes journals as `{run_id}.json` files following the OCAS journal spec v1.3.

## Journal ID format

Each journal file is identified by `{skill_name}/{YYYY-MM-DD}/{run_id}.json`. Praxis tracks consumed journals in `journals_evaluated.jsonl` with entries like:
```json
{"journal_id": "ocas-spot/2026-05-23/r_abc123", "evaluated_at": "2026-05-23T12:30:00Z", "action_taken": "event_recorded"}
```

## Signal extraction rules

From each new journal entry, Praxis extracts behavioral signals by examining:

1. **decision.summary** — the one-line summary of what happened. Look for failure keywords ("failed", "error", "blocked", "timeout"), correction keywords ("fixed", "corrected", "adjusted"), and success keywords ("completed", "succeeded", "booked", "placed").

2. **decision.execution_result.status** — `ok`, `partial`, or `error`. Any `error` or `partial` result is a candidate for event recording.

3. **decision.payload.entities_observed** — entities tagged with `user_relevance: "user"` are higher priority for lesson extraction.

4. **decision.payload.action_result.booked** / **.changed** / **.error** — action outcomes that indicate a behavioral pattern.

5. **runtime.model** and **runtime.duration_seconds** — unusually long runs or model fallbacks may indicate issues.

## When to record an event

Record a praxis event when ANY of the following are true:
- The journal reports an error or partial failure
- The journal reports a user correction or complaint
- The journal reports an action with `changed: true` that succeeded after a prior failure
- The journal duration exceeds 5x the skill's average run time
- The decision summary contains keywords indicating a behavioral lesson

## When to extract a lesson

Extract a lesson when a pattern is detected across 2+ events with the same:
- Error type or failure mode
- Skill or command category
- User-relevance tag

## When NOT to record

- Journal status is `ok` with no unusual patterns
- The run is a no-op (no side effects, nothing to learn)
- The journal is from ocas-praxis itself (avoid self-referencing loops)
- The journal is from ocas-lucid (Lucid already curates journals; don't double-process)

## Priority order

When many new journals exist, process in this order:
1. Error/failure journals (highest priority — most to learn from)
2. User-correction journals
3. Success-after-failure journals (pattern of improvement)
4. Normal success journals (lowest priority — only if pattern detection needs more data)
5. No-op journals (extracted last, for completeness)

## Degraded mode

If no journal directories exist or all are empty, Praxis logs `degraded: journals` and continues. It will retry on the next cron cycle.
