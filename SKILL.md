---
license: MIT
name: ocas-praxis
description: 'Bounded behavioral refinement loop. Records outcomes, extracts micro-lessons from repeated patterns, consolidates them into capped active behavior shifts, applies shifts at runtime, and generates plain-language debriefs. Use for recording task outcomes, extracting lessons from repeated patterns, managing active behavior shifts, generating runtime briefs, or producing debriefs. Not for: general memory (use Chronicle), preference tracking (use Taste), real-time task execution, content generation, system health monitoring (use Custodian), or skill evaluation scoring (use Mentor).'
source: https://github.com/indigokarasu/praxis
includes:
- references/**
- scripts/**
metadata:
  author: Indigo Karasu (indigokarasu)
  version: "3.3.0"
  hermes:
    tags: [behavioral-refinement, lessons, outcomes, OCAS-core]
    category: productivity
tags:
- behavioral-refinement
- lessons
- outcomes
- OCAS-core
triggers:
- behavioral refinement
- micro-lessons
- pattern consolidation
- outcome recording
- praxis loop
---

# Praxis

Praxis is the system's behavioral self-improvement loop — it records real task outcomes, waits for patterns to emerge across multiple events, and consolidates validated lessons into a small capped set of active behavior shifts that influence every future run. The cap of 12 active shifts is a hard constraint preventing unbounded rule accumulation; every shift must trace back to recorded events so nothing changes without an auditable reason.

## When to Use

- Recording outcomes from skill executions
- Extracting lessons from repeated patterns
- Reviewing or managing active behavior shifts
- Generating the current runtime brief (active shifts only)
- Producing a debrief explaining what changed and why
- Running scheduled cron ingest (praxis:journal_ingest) — see `references/cron-execution-checklist.md` and `references/ingest-script-pattern.md`
- Running shift cleanup/consolidation — use `scripts/shift_cleanup_YYYYMMDD.py` pattern
- Running lesson noise cleanup — use `scripts/cleanup_noise_lessons.py`
- Running praxis review pass — `scripts/praxis_review.py --since-hours 24`
- Generating daily debrief — use `scripts/debrief_YYYYMMDD.py` template

## When NOT to Use

- General knowledge storage — use memory tool
- Preference tracking — use Taste
- One-off trivia or domain facts
- Broad autobiographical summaries

## Workflow

The praxis workflow: Record → Extract → Consolidate → Apply → Debrief.

1. **Record** — Capture task outcomes as evidence records
2. **Extract** — Identify micro-lessons from repeated patterns (NEW events only)
3. **Consolidate** — Merge lessons into active behavior shifts (capped at 12)
4. **Apply** — Apply shifts at runtime
5. **Debrief** — Generate plain-language summary

## Responsibility Boundary

Praxis owns bounded behavioral refinement: events, lessons, shifts, and debriefs. Praxis reads journals from all skills to extract behavioral signals. Praxis decides whether to act on each signal found in any skill's journal output. Error handling follows the recovery contract.

Praxis does not own: general memory (use memory tool), preference persistence (Taste), pattern discovery (Finch), communications (Dispatch), skill evaluation (Mentor).

## Commands

- `praxis.event.record` — record a completed event or outcome with evidence
- `praxis.lesson.extract` — derive micro-lessons from recorded events
- `praxis.shift.propose` — propose a new behavior shift from lessons
- `praxis.shift.list` — list all shifts with status
- `praxis.shift.activate` — activate a proposed shift (enforces cap)
- `praxis.shift.expire` — expire or reject a shift with reason
- `praxis.runtime.brief` — generate runtime brief with active shifts only
- `praxis.debrief.generate` — produce a plain-language debrief
- `praxis.status` — event count, active shifts, cap usage, last debrief
- `praxis.journal` — write journal for the current run
- `praxis.update` — pull latest from GitHub source

## Core Loop

1. Record event → 2. Extract lessons (if pattern detected) → 3. **Upgrade lessons** — mandatory second pass to add causal grounding (what/why/when) and set `confidence: high` → 4. **Dedup lessons against active shifts** — skip if an active shift already covers the same `(signal_type, failure_phase)` key → 5. Propose shift (check domain+phase overlap, handle mixed schemas) → 6. **Stage for approval** — route to `{agent_root}/commons/data/ocas-forge/staged/{skill}/` for `ocas-fellow` benchmark verification before committing → 7. Activate (if cap allows) → 8. Generate debrief

**Two-pass lesson extraction is mandatory.** Pass 1 groups events by signal_type+phase and produces lesson stubs. Pass 2 adds full causal grounding and upgrades confidence to `high`. Without Pass 2, no lessons can produce shifts.

**Lesson extraction scope: NEW EVENTS ONLY.** Track `last_lesson_extraction_event_id` in the ingest state and filter `all_events` to only events with `event_id` greater than that marker before grouping. Re-processing all events causes stale lessons, unknown-domain lessons, and noise lessons.

**Ingest state file (`ingest_state.json`):** Tracks `last_lesson_extraction_event_id` for scoped lesson extraction. Create with all required fields on first run if missing. Empty string `""` is equally broken as `null` — both fail the `event_id > marker` comparison.

## Run Completion

After every Praxis command:
1. Scan all skill journals at `{agent_root}/commons/journals/*/YYYY-MM-DD/` for new entries
2. Persist events, lessons, shifts, and debriefs to local JSONL files
3. **Shift merge pass** — scan active shifts for semantic overlap, merge before proposing new
4. Log material decisions to `decisions.jsonl`
5. Write journal via `praxis.journal`
6. **Update `ingest_state.json`** — `last_ingest_run`, `journals_processed`, `total_ingests`, etc.

### Cron Execution Checklist

After running `praxis_ingest_run.py` in cron mode, the caller must:
1. Update `ingest_state.json` (last_ingest_run, journals_processed, total_ingests, etc.)
2. **Gap journal backfill** — run `gap_backfill.py` BEFORE updating last_ingest_run (catches missed journals)
3. Update ingest_state with backfill count
4. **Noise lesson cleanup** — remove Bug 2 noise lessons (see `references/recurring-noise-lesson-cleanup.md`)
5. **Write Praxis journal** — to `{agent_root}/commons/journals/ocas-praxis/YYYY-MM-DD/praxis-cron-{timestamp}Z.json`
6. **Decay-risk scan** — shifts with `reinforcement_count == 0` and age > 7 days
7. **Stale proposed-shift cleanup** — proposed shifts ≥10 days old
8. **Verify post-write** — state JSON parses, journal JSON valid, lessons.jsonl byte count

See `references/cron-execution-checklist.md` for the production-proven script pattern.

## Known Production Script Bugs (ACTIVE)

Four confirmed bugs in `scripts/praxis_ingest_run.py` and `scripts/praxis_common.py` (as of 2026-06-30). Workarounds prevent failures but waste compute. See `references/gotchas-praxis.md` for full catalog.

- **Bug 1:** Date filter too narrow — only scans today/yesterday dirs. Workaround: gap backfill.
- **Bug 2:** Lesson extraction processes full event history — produces noise lessons. Workaround: noise cleanup.
- **Bug 3:** Eval file ID format mismatch — occasional re-scanning. Workaround: gap backfill.
- **Bug 4:** Double-Z timestamp in journal filenames — cosmetic. Fix: check `ts.endswith('Z')`.

## Hard Constraints

- No autonomous identity rewriting
- No silent safety boundary changes
- No unlimited behavior rule accumulation
- Only active shifts influence runtime
- Maximum 12 active shifts (configurable)
- Every shift must trace to recorded events
- Every lesson must include causal grounding (the "why")
- Shifts without decay review expire automatically (default 14 days)

## Capping and Consolidation

Default cap: 12 active shifts. When at cap and a new shift is proposed: merge overlapping shifts, replace a weaker shift, or reject.

**Shift activation dedup (mandatory before cap check):**
1. Domain+phase overlap — merge if exists
2. Text similarity — consolidate if nearly identical
3. Only after merge — check cap

**Shift decay:** Active shifts not reinforced in 14+ days auto-expire. Use `last_reinforced_at` (not `activated_at`) for decay age. Shift records carry duplicate reinforcement fields — read `reinforcement_count` and `last_reinforced_at` (canonical), ignore `reinforced_count`/`last_reinforced`.

**Elaborative interrogation:** Lessons must capture WHAT, WHY, and WHEN. Format: `[LESSON] What: <pattern>. Why: <cause>. When: <conditions>`

## Data Model and Storage

See `references/data_model.md` for full storage layout, JSON schemas, default config, and OKRs.

Key storage paths:
- Data: `{agent_root}/commons/data/ocas-praxis/`
- Journals: `{agent_root}/commons/journals/ocas-praxis/YYYY-MM-DD/{run_id}.json`

## Inter-skill Interfaces

**All skills → Praxis (cooperative read):** Praxis scans journal output from every skill. Consumed `journal_id` values tracked in `journals_evaluated.jsonl`.

Known journal-producing skills: ocas-spot, ocas-rally, ocas-taste, ocas-finch, ocas-fellow, ocas-scout, ocas-bones, ocas-bower, ocas-vibes, ocas-voyage, ocas-imagine, ocas-weave, ocas-vesper, ocas-dispatch, ocas-mentor, ocas-lucid, ocas-sands, ocas-sift, ocas-reach, ocas-look, ocas-multipass, ocas-forge, ocas-haiku, ocas-custodian.

## Recovery Behavior

Implements the recovery contract from `spec-ocas-recovery.md`.

- **Evidence**: Every run writes an evidence record including no-op runs. `not_activity_reason` mandatory.
- **Gap detection**: If gap exceeds expected cadence, logs `gap_detected`.
- **Degraded mode**: When journal directories unavailable, logs `degraded: journals`.
- **Log compaction**: 30 days (no-op) / 90 days (error/gap). Last 7 days retained.

## Initialization

On first invocation, run `praxis.init`:
1. Create `{agent_root}/commons/data/ocas-praxis/` and subdirectories
2. Write default `config.json` if absent
3. Create empty JSONL files
4. Create journal directory
5. Register cron jobs: `praxis:journal_ingest` (every 30min), `praxis:decay_check` (noon daily), `praxis:debrief` (6am daily), `praxis:update` (midnight daily)
6. Log initialization as DecisionRecord

## Second-Wave Detection (Already Evaluated)

When triggered by the dispatcher, always check `journals_evaluated.jsonl` for the journal filename before running mtime-based discovery. If already present (regardless of `action_taken`), skip silently.

## Dispatch / Cron Integration

When triggered by the dispatcher, Praxis owns `journals_evaluated.jsonl` and `ingest_state.json`.

**Key rules:**
- Capture `last_ingest_run` BEFORE Mentor runs
- Third-wave mitigation is mandatory
- Gap journal backfill after every run
- `execute_code` is blocked in cron mode — use `terminal()` with scripts
- Never do `ts.isoformat() + "+00:00"` — double suffix breaks `fromisoformat()`
- Large gap backfill (80+ entries) is normal at steady-state
- Cold-start: initialize state with CURRENT timestamp, not epoch
- `last_ingest_run` MUST stay an ISO-8601 string — a float crashes the ingest

## Journal Outputs

Action Journal — every event recording, lesson extraction, shift change, and debrief generation. Include `entities_observed`, `relationships_observed`, `preferences_observed` with `user_relevance` field.

## Debrief Generation

When running `praxis.debrief.generate` outside scheduled cron:
1. Load active shifts from `shifts.jsonl` — filter `status == "active"`
2. Scan for decay risk — shifts with `reinforcement_count == 0` and age > 10 days
3. Scan for overlap — group by domain+phase; flag shifts sharing >3 words
4. Count recent events — last 200 events by signal_type
5. Check cap headroom — if active shifts ≥ 10, flag "approaching cap"
6. Write structured debrief to `debriefs.jsonl`
7. NEVER use `write_file` on JSONL files — use append via `open(..., 'a')`

See `references/debrief_workflow.md` for full debrief steps.

## Gotchas — Critical

Key gotchas (see `references/gotchas-praxis.md` for the full catalog of 100+ gotchas):

- **Dedup key must be `(source_journal, signal_type)`** — not just `source_journal`
- **Shift cap enforcement requires proactive merge-before-cap** — merge overlap check BEFORE cap check
- **Noise signal types must be filtered at lesson creation** — apply NOISE_SIGNAL_TYPES filter after Pass 2
- **Mentor-light `low_coverage` is a measurement artifact** — filter at extraction time, not globally
- **Lesson content dedup required** — dedup by `(signal_type, failure_phase)`, not `lesson_id`
- **Active shift cap is hard** — 12-shift cap enforced on every activation
- **Cap enforcement must use full file rewrite** — expired shifts not persisted with append-only
- **Domain must be the skill name, not the signal_type** — use skill field from events
- **Writing complex Python scripts — use heredoc, not write_file** — write_file corrupts multi-line Python
- **`patch` corrupts multi-line JSON in `ingest_state.json`** — prefer full file rewrite via load→modify→dump
- **`last_ingest_run` must stay ISO-8601 string** — float crashes ingest with AttributeError
- **0-byte `shifts.jsonl` is NOT data loss** — live store is `/root/indigokarasu/SOUL/autobio/shifts.jsonl`

## OKRs

See `references/okrs-praxis.md`. Key OKRs: `event_coverage` (≥0.90), `lesson_extraction_precision` (≥0.80), `shift_activation_accuracy` (≥0.75), `shift_decay_compliance` (≥0.95), `cap_efficiency` (≥0.80).

## Support File Map

See [references/support-file-map.md](references/support-file-map.md) for the full file registry with "When to read" column. Key references: `cron-execution-checklist.md`, `data_model.md`, `ingest-script-pattern.md`, `dispatch-ingest.md`, `gotchas-praxis.md`, `inline-examples.md`, `debrief_workflow.md`.

- `references/praxis-ingest-cli-pitfall.md` — Before invoking `praxis_ingest_run.py`: inspect source for interface details; any invocation has side effects.
