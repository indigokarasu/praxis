---
name: ocas-praxis
description: 'Praxis: bounded behavioral refinement loop. Records outcomes, extracts
  micro-lessons from repeated patterns, consolidates them into capped active behavior
  shifts, applies shifts at runtime, and generates plain-language debriefs. Trigger
  phrases: ''record outcome'', ''extract lesson'', ''behavior shift'', ''what have
  I learned'', ''runtime brief'', ''debrief'', ''update praxis''. Do not use for general
  memory, personality rewriting, or knowledge storage.

'
license: MIT
source: https://github.com/indigokarasu/praxis
includes:
  - references/**
  - scripts/**

metadata:
  author: Indigo Karasu
  version: "2.8.1"
---
## When to Use

- Recording outcomes from skill executions
- Behavioral refinement based on results
- Inter-skill cooperation tracking
- After any significant task completion
- When feedback loops need durable recording
## When NOT to Use

- Real-time task execution
- Content generation or research
- System health monitoring (use Custodian)
- Skill evaluation scoring (use Mentor)

# Praxis

Praxis is the system's behavioral self-improvement loop — it records real task outcomes, waits for patterns to emerge across multiple events, and then consolidates validated lessons into a small capped set of active behavior shifts that influence every future run. The cap of 12 active shifts is a hard constraint that prevents unbounded rule accumulation, and every shift must trace back to recorded events so nothing changes without an auditable reason.

## When to use

- Record a task outcome, failure, success, or correction
- Extract lessons from repeated patterns
- Review or manage active behavior shifts
- Generate the current runtime brief (active shifts only)
- Produce a debrief explaining what changed and why

## When NOT to use

- General knowledge storage — use Elephas
- Preference tracking — use Taste
- One-off trivia or domain facts
- Broad autobiographical summaries
- Silent personality mutation

## Responsibility boundary

Praxis owns bounded behavioral refinement: events, lessons, shifts, and debriefs.

Praxis does not own: general memory (Elephas), preference persistence (Taste), pattern discovery (Corvus), communications (Dispatch), skill evaluation (Mentor).

Praxis reads journals from all skills to extract behavioral signals. Praxis decides whether to act on each signal found in any skill's journal output.

## Ontology types

Praxis observes entity types during behavioral refinement:
- **Concept/Event** — recorded outcomes, task completions, failures, corrections, and behavioral signals
- **Concept/Idea** — extracted lessons, behavior shifts, and refinements

Praxis does not extract or emit Signals to Elephas directly. Journal entries track recorded events and behavioral shifts, but these are not promoted to Chronicle. Lessons remain isolated to the bounded refinement loop and do not flow to the knowledge graph.

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
- `praxis.update` — pull latest from GitHub source; preserves journals and data

## Core loop

1. Record event → 2. Extract lessons (if pattern detected) → 3. Propose shift → 4. Activate (if cap allows) → 5. Generate debrief

## Run completion

After every Praxis command:

1. Scan all skill journals at `{agent_root}/commons/journals/*/YYYY-MM-DD/` for new journal entries (not in `journals_evaluated.jsonl`). For each new journal: extract behavioral signals (failures, corrections, successes, patterns), decide whether to record as an event and extract a lesson. Track consumed `journal_id` values in `journals_evaluated.jsonl` to avoid reprocessing.
2. Persist events, lessons, shifts, and debriefs to local JSONL files
3. Log material decisions to `decisions.jsonl`
4. Write journal via `praxis.journal`

## Hard constraints

- No autonomous identity rewriting
- No silent safety boundary changes
- No unlimited behavior rule accumulation
- Only active shifts influence runtime
- Maximum 12 active shifts (configurable)
- Every shift must trace to recorded events
- Every lesson must include causal grounding (the "why" — not just "what")
- Shifts without decay review expire automatically (configurable, default 14 days)

## Capping and consolidation rules

Default cap: 12 active shifts. When at cap and a new shift is proposed: merge overlapping shifts, replace a weaker shift, or reject the new shift. No duplicate or contradictory active shifts.

### Shift decay (from forgetting curve research)

Active shifts that aren't reinforced decay. Praxis tracks reinforcement per shift:

- **Reinforced**: Shift applied successfully in a recent run — extends half-life
- **Stale**: Not reinforced in 7+ days — flagged for review at next debrief
- **Decayed**: Not reinforced in 14+ days (configurable `decay_days`) — auto-expired with reason "decay: no reinforcement for {N} days"

This prevents the shift list from becoming a graveyard of once-useful but now-stale rules. If a shift IS still valid, re-encountering the pattern will reinforce it. If it was context-specific and that context no longer applies, it naturally decays.

### Elaborative interrogation for lessons

When extracting a lesson, don't just record WHAT happened — capture WHY and WHEN:

- **What**: What pattern of events occurred?
- **Why**: Why did this pattern emerge? What's the causal mechanism?
- **When**: Under what conditions does this lesson apply? What are the boundary conditions?

Format: `[LESSON] What: <pattern>. Why: <cause>. When: <conditions>`

Lessons without causal grounding ("do X") are marked `confidence: low` and require an additional reinforcement cycle before producing shifts. Grounded lessons ("do X because Y fails when Z") are marked `confidence: high` and can produce shifts on first pattern detection.

### Failure-phase tagging (from arxiv:2508.13143)

Tag each event with the task phase where the failure occurred. This enables surgical shift targeting:

| Phase | Description | Shift target |
|-------|-------------|--------------|
| **Planning** | Wrong approach, bad assumptions, missing prerequisites | Precondition checks, "before doing X, verify Y" |
| **Execution** | Right plan but tool/step/parameter wrong | Tool usage constraints, parameter validation |
| **Response** | Correct result but wrong output format/tone | Output formatting rules, verbosity standards |

Two planning-failed events should produce a shift targeting preconditions — not a generic "be more careful."

## Runtime injection rules

The runtime brief is a compact list of active shifts only. Target: 3-12 items. Imperative, behavior-facing, free of historical clutter. Not a narrative log.

## Data model and storage

See `references/data_model.md` for the full storage layout, JSON schemas (Event, MicroLesson, BehaviorShift, Debrief), default config, and OKRs.

Key storage paths:
- Data: `{agent_root}/commons/data/ocas-praxis/` — events, lessons, shifts, debriefs, decisions, evidence (all JSONL)
- Journals: `{agent_root}/commons/journals/ocas-praxis/YYYY-MM-DD/{run_id}.json`

## Inter-skill interfaces

**All skills → Praxis (cooperative read):** Praxis scans journal output from every skill at `{agent_root}/commons/journals/*/YYYY-MM-DD/` on each cron run. Praxis extracts behavioral signals (failures, corrections, successes, patterns) from journal entries and decides whether to record each as an event and extract a lesson. Praxis is not obligated to act on every journal entry. Consumed `journal_id` values are tracked in `journals_evaluated.jsonl`. Skills do not write to Praxis's directories.

Known journal-producing skills: ocas-corvus, ocas-spot, ocas-rally, ocas-taste, ocas-elephas, ocas-finch, ocas-fellow, ocas-scout, ocas-bones, ocas-bower, ocas-vibes, ocas-voyage, ocas-imagine, ocas-weave, ocas-vesper, ocas-dispatch, ocas-mentor, ocas-lucid, ocas-sands, ocas-sift, ocas-reach, ocas-inception, ocas-look, ocas-multipass, ocas-forge, ocas-haiku, ocas-custodian. See `references/journal_sources.md` for per-skill signal descriptions.

See `references/journal_ingestion.md` for the journal schema and ingestion rules.

## Recovery Behavior

This skill implements the recovery contract from `spec-ocas-recovery.md`.

- **Evidence**: Every run writes an evidence record to `{agent_root}/commons/data/ocas-praxis/evidence.jsonl`, including no-op runs. The `not_activity_reason` field is mandatory when no side effects occur.
- **Gap detection**: On every wake, checks the evidence log. If gap exceeds expected cadence for signals processing, logs `gap_detected`.
- **Degraded mode**: When journal directories are unavailable or empty, continues with available inputs and logs `degraded: journals`.
- **Log compaction**: Evidence and decision logs older than 30 days (no-op) or 90 days (error/gap) compacted. Last 7 days retained.

- **Cross-skill contamination risk** — Praxis's core loop ("Record event → Extract lessons → Propose shift → Activate → Generate debrief") is distinct from Finch's ("Scan → Work → Mine → Route → Journal"). During major rewrites, verify Praxis content doesn't pick up artifacts from Finch or other sibling skills. The "core loop" and "run completion" sections are the most likely contamination points.
- **Journal directory scan pattern** — Praxis scans `commons/journals/*/YYYY-MM-DD/` on each cron run. Track consumed entries in `journals_evaluated.jsonl` using the composite key `{skill_name}/{YYYY-MM-DD}/{run_id}.json`. Never re-process a journal entry that's already been evaluated.

## Optional skill cooperation

- All OCAS skills — Praxis reads journal output from every skill at `{agent_root}/commons/journals/*/`. Skills don't know Praxis exists; this is a cooperative read.
- Dispatch — receives action decisions from Praxis for communication execution
- Elephas — journal entity observations consumed during Chronicle ingestion

## Journal outputs

Action Journal — every event recording, lesson extraction, shift change, and debrief generation.

When entities are encountered during runs, journals should include the following fields in `decision.payload`:

- `entities_observed` — entities noticed during the run (e.g., Concept/Action for behavioral events and lessons, Concept/Idea for behavioral patterns and shifts)
- `relationships_observed` — relationships between observed entities
- `preferences_observed` — any user preferences or behavioral preferences surfaced

Each entity observation must include a `user_relevance` field:
- `user` — the entity is directly related to the user's world (e.g., lessons learned about user preferences such as "user prefers concise responses")
- `agent_only` — encountered incidentally as part of the agent's internal behavioral refinement (most Praxis entities fall here)
- `unknown` — relevance to the user is unclear

## Initialization

On first invocation of any Praxis command, run `praxis.init`:

1. Create `{agent_root}/commons/data/ocas-praxis/` and subdirectories (`reports/`)
2. Write default `config.json` with ConfigBase fields if absent
3. Create empty JSONL files: `events.jsonl`, `lessons.jsonl`, `shifts.jsonl`, `debriefs.jsonl`, `decisions.jsonl`, `journals_evaluated.jsonl`, `intents.jsonl`, `evidence.jsonl`
4. Create `{agent_root}/commons/journals/ocas-praxis/`
5. Register cron jobs: `praxis:journal_ingest` (every 30min), `praxis:decay_check` (noon daily), `praxis:debrief` (6am daily), `praxis:update` (midnight daily). Use `hermes cron create` for each. Skip if already registered.
6. Log initialization as a DecisionRecord in `decisions.jsonl`

See `references/data_model.md` for the cron registration commands.

## Background tasks

All Praxis background tasks use cron scheduling. **Hermes does not support heartbeats.**

| Job name | Mechanism | Schedule | Command |
|---|---|---|---|
| `praxis:journal_ingest` | cron | `*/30 * * * *` (every 30 minutes) | Scan all skill journals at `{agent_root}/commons/journals/*/YYYY-MM-DD/` for new entries since last run; extract behavioral signals; record events and extract lessons as appropriate. Write evidence record. |
| `praxis:decay_check` | cron | `0 12 * * *` (noon daily) | Review all active shifts, check `last_reinforced_at` against `decay_days` threshold, expire stale shifts, flag shifts approaching expiry. Write evidence record. |
| `praxis:debrief` | cron | `0 6 * * *` (6am daily) | Review accumulated events and lessons from the past 24 hours; propose/activate behavior shifts if patterns detected; check shift decay status; generate debrief. |
| `praxis:update` | cron | `0 0 * * *` (midnight daily) | `praxis.update` |

**Critical: Do NOT create a heartbeat task file.** Hermes has no heartbeat mechanism. All Praxis background processing must use cron jobs only.

**Rationale for cron instead of heartbeats:**
- Hermes has no heartbeat mechanism; cron jobs are the only built-in scheduling primitive
- Journal ingestion needs to run frequently (every 30min) to process new skill output in near-real-time
- Debrief generation is a batch operation best done once daily when there's a full day of signals to analyze
- Self-update is a low-frequency maintenance task suited to midnight runs

For exact cron registration commands, see `references/data_model.md`.

## Self-update

`praxis.update` pulls the latest skill package from GitHub source. Preserves journals and data. See `references/self-update.md` for the full procedure.

## Visibility

public

## Gotchas

- **Active shift cap is hard** — The 12-shift cap is enforced on every activation. When at cap, new shifts must merge with existing ones, replace a weaker shift, or be rejected. No overflow is possible.
- **Journal ingestion scans ALL skills** — Every 30-minute cron run scans journal output from every installed skill. If a skill produces verbose journals, this can become expensive. Track consumed IDs in `journals_evaluated.jsonl` to avoid reprocessing.
- **Cross-skill contamination risk** — Praxis's core loop (Record → Extract → Propose → Activate → Debrief) is distinct from Finch's loop. During rewrites, verify Praxis content doesn't pick up artifacts from Finch or other sibling skills.
- **Lessons require causal grounding** — A lesson is only extracted when `min_pattern_count` (default 3) events form a repeatable pattern. Lessons without "why" and "when" are marked `confidence: low` and held for additional evidence. The exception: 2+ events in the same failure phase can produce a phase-aligned shift.
- **Shifts decay without reinforcement** — Active shifts not reinforced in 14 days (configurable) auto-expire. This prevents rule graveyard accumulation. The noon `praxis:decay_check` cron runs this check daily. If a shift is still valid, re-encountering the pattern will reinforce it.
- **Failure-phase tagging is mandatory for corrections** — Events from journal ingestion must include `failure_phase`. Untagged events can't participate in phase-aligned extraction.
- **Debriefs are plain-language only** — Runtime briefs must be imperative, behavior-facing, and free of historical clutter. A debrief that reads like a narrative log violates the format constraint.
- **Execute the fix, don't just summarize** — When you detect a failure signal, record the event AND extract a lesson in the same pass. Don't produce a report saying "X failed, consider updating Y." Actually update Y. This applies to all Praxis operations.

## Platform notes

Praxis uses the `memory` tool (2 references) to record behavioral outcomes. On platforms without `memory`, write outcomes to `references/outcomes.md` instead. The behavioral refinement loop works on any platform that provides `write_file` and `read_file`.

## Support File Map

| File | When to read |
|------|-------------|
| `references/data_model.md` | Before creating events, lessons, shifts, or debriefs; when checking data schemas; for storage layout, config, OKRs, cron commands |
| `references/self-update.md` | Before running `praxis.update` — compatibility checks and update procedure |
| `references/journal_sources.md` | Before scanning skill journals — per-skill signal descriptions and journal-producing skill list |
| `references/lesson_rules.md` | Before extracting lessons from events; when deriving micro-lessons from patterns |
| `references/runtime_rules.md` | Before generating runtime brief; when formatting active behavior shifts |
| `references/debrief_templates.md` | Before generating debriefs; when structuring plain-language debrief output |
| `references/journal.md` | Before calling praxis.journal; at end of every run |
| `references/journal_ingestion.md` | Before scanning skill journals for new entries; when extracting behavioral signals |
