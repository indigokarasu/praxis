# Praxis Journal Ingest — 2026-05-31 02:18 UTC (Run 3)

## Summary

0 new journals (all 4,756 already evaluated). 0 events. 0 lessons. System nominal.

## Prior Partial Run Recovery

A prior ingest run (praxis-ingest-20260531021613) processed 6 new journals but crashed during lesson extraction with `KeyError: 'event_id'` — legacy events use `id` not `event_id`. The 6 journals were correctly written to `journals_evaluated.jsonl` before the crash. This run confirmed zero remaining unevaluated journals.

## Event Created (Prior Run)

- `ocas-weave` — sync aborted: token file `jared.zimmerman@gmail.com.json` is 0 bytes (empty). Tagged `failure` / `null` phase. First occurrence — held for pattern.

## Data State

- Events: 119 total
- Lessons: 62
- Shifts: 29 total, 11 active / 12 cap (1 slot free)
- journals_evaluated.jsonl: 5,106 entries (no duplicates)
- All active shifts reinforced within 2 days — no decay

## Gotcha Confirmed

- **`id` vs `event_id` dual-schema**: The v1 ingest script crashed because lesson extraction used `evt['event_id']` directly. Legacy records use `id`. Patch added to SKILL.md: always use `evt.get('event_id', evt.get('id', ''))`.

## No Overlap Issues

No skill overlap detected. Praxis owns the bounded refinement loop exclusively.
