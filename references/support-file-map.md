# Praxis Support File Map

| File | When to read |
|------|-------------|
| `references/cron-execution-checklist.md` | After running production script in cron mode — state update, gap backfill, journal write, decay scan, stale script cleanup |
| `references/data_model.md` | Before creating events, lessons, shifts; for schemas and storage layout |
| `references/okrs-praxis.md` | During OKR evaluation |
| `references/ingest-script-pattern.md` | Before writing ingest scripts; production-proven Python pattern for scan/dedup/extract/shift-activate workflow |
| `references/dispatch-quick-path.md` | **Read when triggered by dispatcher** — 5-line quick path for routine `new_files` that are all no-signal (80% of dispatches). Only use full template for journals with errors/escalations. |
| `references/journal_ingestion.md` | Before scanning skill journals; signal extraction rules |
| `references/gotchas-praxis.md` | Before any Praxis operation; full gotcha catalog |
| `references/mentor-light-noise-filters.md` | During journal ingest — mandatory filters for mentor-light false positives |
| `references/recurring-noise-lesson-cleanup.md` | After every cron ingest — mandatory cleanup of low-confidence noise lessons |
| `references/shift-cap-repair.md` | When active shifts exceed cap: repair procedure, curated rebuild, prevention patterns |
| `references/storage-layout-praxis.md` | During initialization or path resolution |
| `references/self-update-praxis.md` | Before running praxis.update |
| `references/inline-examples.md` | Before writing/repairing `ingest_state.json` (bootstrap vs null/empty-string fix), Bug 2 noise-lesson cleanup, or lesson dedup — holds the exact code snippets extracted from SKILL.md |
| `templates/dispatch_ingest_template.py` | Copy-and-adapt template for dispatch-triggered Praxis ingest |
| `scripts/debrief_20260617.py` | When generating daily debrief; production-proven template |

## Session Notes (historical reference)

| File | When to read |
|------|-------------|
| `references/session-20260629-dispatch-1221Z.md` | Dispatch with gap_backfill.py path fix + concurrent cron gap pattern |
| `references/session-20260629-dispatch-1240Z-praxis.md` | **Massive legacy eval backfill** — 12,087 journals backfilled in one dispatch. One-time catchup pattern. |
| `references/session-20260629-cron-ingest-0207.md` | 5,817 gap backfill catchup, 14 noise lessons cleaned |
| `references/session-20260629-cron-ingest-0308.md` | Phantom gap journal detected (os.walk race), 14 Bug-2 noise lessons cleaned |
| `references/session-20260629-cron-ingest-1231.md` | 13 Bug-2 noise lessons with MISSING signal_type key — cleanup filter bug discovered and fixed |
| `references/session-20260701-cron-ingest-0735Z.md` | **Cron ingest 2026-07-01:** `last_lesson_extraction_event_id: ""` (empty string) is as broken as `null`. Phantom finch journal produced unverifiable event. Fast pre-filter vs per-lesson comparison. |
| `references/session-20260707-cron-ingest-0205z.md` | **Steady-state confirmation:** All 4 production bugs active but mitigated. Fast pre-filter (3rd validation), noise cleanup fix works (missing signal_type), decay check uses last_reinforced_at correctly. 3/12 active shifts stable. |

For other session-specific gotchas and incident reports, see `references/session_*.md` files. Read only when debugging a specific past issue mentioned in those sessions.
