# Session 2026-06-29 Cron Ingest 02:07Z

**Run type:** Scheduled cron (praxis:journal_ingest)
**Ingest #:** 127

## What Happened

1. Production script `praxis_ingest_run.py` ran: 3 journals scanned (2 mentor-light routine heartbeats, 1 dispatch-wave journal), 1 no_signal event recorded.
2. Bug 2 produced 14 noise lessons (all with empty `signal_type` from legacy-event reprocessing). All cleaned by post-ingest noise cleanup.
3. Gap backfill caught 5,817 previously-unevaluated historical journals — a one-time catchup from a backlog of journals that existed on disk but had never been added to the eval file.
4. Eval file grew from 42,357 → 48,176 entries (+5,819: 2 from script + 5,817 from backfill).
5. Active shifts: 3/12, all at age=0 with reinforcements. Zero decay risk.

## Key Learnings

- **Gap backfill scale can be large** when the eval file has a significant historical backlog. The 5,817 entries covered finch scans, custodian light-scans, bower scans, and dispatch journals from late June that were never evaluated. This is correct behavior — these journals existed but were invisible to the eval dedup mechanism.
- **Mixed-format eval file handling is critical** in the gap backfill path. The eval file contains both plain string entries (legacy) and JSON dict entries (modern). The gap backfill must handle both formats when building the evaluated-IDs set, otherwise it will re-evaluate already-processed journals.
- **Noise lesson heuristic confirmed:** All 14 Bug-2 lessons had `signal_type: ""` (empty string) — the most reliable single indicator of legacy-event reprocessing. The "all events are no_signal → all lessons are noise" decision rule correctly identified all 14 for cleanup.

## State After

- `total_ingests`: 127
- `journals_evaluated.jsonl`: 48,176 lines
- `events.jsonl`: 3,556 lines
- `lessons.jsonl`: 0 lines (all noise cleaned)
- `shifts.jsonl`: 264 lines (3 active, 230 expired, 16 rejected, 15 proposed)
- Active shifts: ocas-custodian/execution (4 reinf), ocas-mentor/Execution (2 reinf), ocas-spot/Execution (1 reinf)
