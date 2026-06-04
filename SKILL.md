---
name: ocas-praxis
description: >
  Praxis: bounded behavioral refinement loop. Records outcomes, extracts micro-lessons
  from repeated patterns, consolidates them into capped active behavior shifts, applies
  shifts at runtime, and generates plain-language debriefs. Use when recording task
  outcomes, extracting lessons from repeated patterns, managing active behavior shifts,
  generating runtime briefs, or producing debriefs. Trigger phrases: "record outcome",
  "extract lesson", "behavior shift", "what have I learned", "runtime brief",
  "debrief", "update praxis". Do not use for general memory (use Elephas), preference
  tracking (use Taste), real-time task execution, content generation, system health
  monitoring (use Custodian), or skill evaluation scoring (use Mentor).
license: MIT
source: https://github.com/indigokarasu/praxis
includes:
- references/**
- scripts/**
metadata:
  author: Indigo Karasu (indigokarasu)
  version: 3.2.0
triggers:
- behavioral refinement
- micro-lessons
- pattern consolidation
- outcome recording
- praxis loop
---

# Praxis

Praxis is the system's behavioral self-improvement loop — it records real task outcomes, waits for patterns to emerge across multiple events, and consolidates validated lessons into a small capped set of active behavior shifts that influence every future run. The cap of 12 active shifts is a hard constraint that prevents unbounded rule accumulation, and every shift must trace back to recorded events so nothing changes without an auditable reason.

## When to Use

- Recording outcomes from skill executions
- Extracting lessons from repeated patterns
- Reviewing or managing active behavior shifts
- Generating the current runtime brief (active shifts only)
- Producing a debrief explaining what changed and why

## When NOT to Use

- General knowledge storage — use Elephas
- Preference tracking — use Taste
- One-off trivia or domain facts
- Broad autobiographical summaries
- Silent personality mutation

## Responsibility Boundary

Praxis owns bounded behavioral refinement: events, lessons, shifts, and debriefs.

Praxis does not own: general memory (Elephas), preference persistence (Taste), pattern discovery (Corvus), communications (Dispatch), skill evaluation (Mentor).

Praxis reads journals from all skills to extract behavioral signals. Praxis decides whether to act on each signal found in any skill's journal output.

## Ontology Types

- **Concept/Event** — recorded outcomes, task completions, failures, corrections, and behavioral signals
- **Concept/Idea** — extracted lessons, behavior shifts, and refinements

Praxis does not extract or emit Signals to Elephas directly. Lessons remain isolated to the bounded refinement loop.

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
- `praxis.journal` — write journal for the current run; called at end of every run
- `praxis.update` — pull latest from GitHub source; journals and data preserved

## Core Loop

1. Record event → 2. Extract lessons (if pattern detected) → 3. **Upgrade lessons** — mandatory second pass to add causal grounding (what/why/when) and set `confidence: high` → 4. Propose shift (check domain+phase overlap, handle mixed schemas) → 5. Activate (if cap allows) → 6. Generate debrief

**Two-pass lesson extraction is mandatory.** Pass 1 groups events by signal_type+phase and produces lesson stubs. Pass 2 adds full causal grounding (what/why/when) and upgrades confidence to `high`. Without Pass 2, no lessons can produce shifts. See `references/ingest-script-pattern.md` for the production-proven script.

## Run Completion

After every Praxis command:

1. Scan all skill journals at `{agent_root}/commons/journals/*/YYYY-MM-DD/` for new journal entries (not in `journals_evaluated.jsonl`). Track consumed `journal_id` values.
2. Persist events, lessons, shifts, and debriefs to local JSONL files
3. **Shift merge pass** — Before checking cap, scan active shifts for semantic overlap. Merge overlapping shifts before proposing any new shift.
4. Log material decisions to `decisions.jsonl`
5. Write journal via `praxis.journal`

## Hard Constraints

- No autonomous identity rewriting
- No silent safety boundary changes
- No unlimited behavior rule accumulation
- Only active shifts influence runtime
- Maximum 12 active shifts (configurable)
- Every shift must trace to recorded events
- Every lesson must include causal grounding (the "why" — not just "what")
- Shifts without decay review expire automatically (configurable, default 14 days)

## Capping and Consolidation

Default cap: 12 active shifts. When at cap and a new shift is proposed: merge overlapping shifts, replace a weaker shift, or reject the new shift.

**Shift activation dedup and merge (mandatory before cap check):**

1. **Domain+phase overlap** — Does an active shift already target the same skill/domain AND failure phase? If yes, merge.
2. **Text similarity** — If two shifts have nearly identical `shift_text`, consolidate into a single cross-skill shift.
3. **Only after merge** — check if cap is exceeded. If still at cap, expire the oldest/lowest-reinforced-count shift.

**Shift decay:** Active shifts not reinforced in 14+ days auto-expire. Reinforcement extends half-life.

**Elaborative interrogation:** Lessons must capture WHAT happened, WHY, and WHEN. Format: `[LESSON] What: <pattern>. Why: <cause>. When: <conditions>`

**Failure-phase tagging:** Tag each event with the task phase (Planning, Execution, Response). See `references/gotcha_failure_phase_tagging.md`.

## Data Model and Storage

See `references/data_model.md` for full storage layout, JSON schemas, default config, and OKRs.

Key storage paths:
- Data: `{agent_root}/commons/data/ocas-praxis/`
- Journals: `{agent_root}/commons/journals/ocas-praxis/YYYY-MM-DD/{run_id}.json`

## Inter-skill Interfaces

**All skills → Praxis (cooperative read):** Praxis scans journal output from every skill. Consumed `journal_id` values tracked in `journals_evaluated.jsonl`.

Known journal-producing skills: ocas-corvus, ocas-spot, ocas-rally, ocas-taste, ocas-elephas, ocas-finch, ocas-fellow, ocas-scout, ocas-bones, ocas-bower, ocas-vibes, ocas-voyage, ocas-imagine, ocas-weave, ocas-vesper, ocas-dispatch, ocas-mentor, ocas-lucid, ocas-sands, ocas-sift, ocas-reach, ocas-look, ocas-multipass, ocas-forge, ocas-haiku, ocas-custodian.

See `references/journal_ingestion.md` for journal schema and ingestion rules.

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

## Background Tasks

| Job | Schedule | Command |
|-----|----------|---------|
| `praxis:journal_ingest` | `*/30 * * * *` | Scan skill journals, extract behavioral signals |
| `praxis:decay_check` | `0 12 * * *` | Review active shifts, expire stale |
| `praxis:debrief` | `0 6 * * *` | Generate debrief from past 24h |
| `praxis:update` | `0 0 * * *` | Self-update |

## Journal Outputs

Action Journal — every event recording, lesson extraction, shift change, and debrief generation. Include `entities_observed`, `relationships_observed`, `preferences_observed` with `user_relevance` field.

## Optional Skill Cooperation

- All OCAS skills — Praxis reads journal output (cooperative read)
- Dispatch — receives action decisions for communication execution
- Elephas — journal entity observations consumed during Chronicle Ingestion

## Gotchas — Critical

See `references/gotchas-praxis.md` for the full gotcha catalog (30+ operational pitfalls).

Key gotchas:

- **Active shift cap is hard** — 12-shift cap enforced on every activation
- **Lessons require causal grounding** — "do X because Y" not just "do X"
- **Execute the fix, don't just summarize** — Actually update Y when you detect failure in X
- **`execute_code` is blocked in cron context** — Use `terminal()` with heredoc for JSONL processing
- **`write_file` OVERWRITES JSONL files** — Read-then-rewrite pattern required for appends
- **Cross-skill contamination risk** — Verify Praxis content doesn't pick up artifacts from Finch
- **Lesson suppression false-positive** — When checking if an existing lesson covers a new pattern, keyword matching against `lesson_text` is NOT sufficient. An `ocas-sands` lesson about "Google OAuth token missing" (planning phase) will incorrectly suppress a new `ocas-custodian` lesson about "Google OAuth revoked" (execution phase) because both contain "token". Match on `domain` + `failure_phase` + semantic scope, not keywords. Default to extracting the lesson when in doubt — dedup belongs in shift activation (merge-before-cap), not in lesson suppression.

## OKRs

See `references/okrs-praxis.md` for full OKR definitions and targets.

Key OKRs: `event_coverage` (≥0.90), `lesson_extraction_precision` (≥0.80), `shift_activation_accuracy` (≥0.75), `shift_decay_compliance` (≥0.95), `cap_efficiency` (≥0.80).

## Self-Update

See `references/self-update-praxis.md`.

## Support File Map

| File | When to read |
|------|-------------|
| `references/data_model.md` | Before creating events, lessons, shifts; for schemas and storage layout |
| `references/okrs-praxis.md` | During OKR evaluation |
| `references/ingest-script-pattern.md` | Before writing ingest scripts; production-proven Python pattern for scan/dedup/extract/shift-activate workflow |
| `references/journal_ingestion.md` | Before scanning skill journals; signal extraction rules |
| `references/gotchas-praxis.md` | Before any Praxis operation; full gotcha catalog |
| `references/gotcha_cross_skill_corroboration.md` | Before recording events; cross-skill dedup rules |
| `references/gotcha_custodian_findings_schema.md` | When ingesting custodian journals |
| `references/gotcha_unknown_signal_type.md` | During lesson extraction; noise filtering |
| `references/gotcha_escalation_fingerprint.md` | During escalation signal extraction |
| `references/gotcha_oauth_corruption.md` | When detecting auth-related events |
| `references/gotcha_evidence_field_schema.md` | When reading events.jsonl for pattern detection |
| `references/lesson_rules.md` | Before lesson extraction; confidence thresholds |
| `references/session-notes.md` | Historical production session findings (15 sessions) |
| `references/storage-layout-praxis.md` | During initialization or path resolution |
| `references/self-update-praxis.md` | Before running praxis.update |
