# Session 2026-05-31 Ingest — Cron Journal Ingest

## Summary

Fourth Praxis journal ingest run on 2026-05-31. Found 13 unevaluated journals, 6 signal-free, 0 new events (signals already captured), 3 shifts proposed (11/12 active), 133 duplicate events removed. No new lessons.

## Path Construction Bug in Follow-up Pass

A second ingest pass tried to process 11 "remaining" unevaluated journals. All 11 were marked `skipped_unreadable` because the canonical ID used as a filesystem path didn't match the actual file location:

- `ocas-bones/ocas-bones/2026-05-18.json` was the canonical ID computed, but the actual file was at `ocas-bones/2026-05-18.json` (directly in skill dir)
- `ocas-custodian/no-date/light-2026-05-30-150000.json` — `no-date` isn't a real directory
- `ocas-sands/ocas-sands/2026-05-30.json` — double-nested skill name

Root cause: the follow-up script used pre-computed canonical IDs from the set difference as filesystem paths directly. The first ingest pass handled this correctly because it walked the filesystem natively.

**Fix**: Never use canonical IDs as filesystem paths. When you need to locate a journal file, walk the filesystem with `find` or `glob`. Canonical IDs are for tracking/lookup only.

## Post-Write Dedup: 133 Duplicate Events Removed

Post-write dedup found and removed 133 duplicate events from `events.jsonl` (249 -> 116). These accumulated from earlier ingest runs with mixed ID formats where the pre-filter missed entries due to format differences.

## Shift Activation: +3 Generic Shifts (8 -> 11/12)

Three new generic "verify preconditions" shifts activated for custodian/execution, mentor/execution, and custodian/planning. These are functionally identical to existing cross-skill "verify preconditions" shifts — the shift flooding problem.

Before proposing a new shift, check if an existing active shift's `shift_text` is semantically equivalent. If equivalent, reinforce the existing shift instead of creating a per-skill variant.

## Key Takeaways

1. **Canonical IDs are NOT filesystem paths** — always walk `find`/`glob` to locate files
2. **Post-write dedup is mandatory** — always dedup `events.jsonl` by `source_journal` after every write
3. **Shift semantic dedup needed** — check equivalence before creating per-skill variants of generic shifts
4. **Check existing events before creating new ones** — prior runs may have already captured the signal
