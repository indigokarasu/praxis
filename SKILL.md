---
name: ocas-praxis
description: >
  Praxis: bounded behavioral refinement loop. Records outcomes, extracts
  micro-lessons from repeated patterns, consolidates them into capped active
  behavior shifts, applies shifts at runtime, and generates plain-language
  debriefs. Trigger phrases: 'record outcome', 'extract lesson', 'behavior
  shift', 'what have I learned', 'runtime brief', 'debrief', 'update praxis'.
  Do not use for general memory, personality rewriting, or knowledge storage.
metadata:
  author: Indigo Karasu
  email: mx.indigo.karasu@gmail.com
  version: "2.6.5"
  hermes:
    tags: [behavior, lessons, refinement]
    category: execution
    cron:
      - name: "praxis:update"
        schedule: "0 0 * * *"
        command: "praxis.update"
  openclaw:
    skill_type: system
    visibility: public
    filesystem:
      read:
        - "{agent_root}/commons/data/ocas-praxis/"
        - "{agent_root}/commons/journals/ocas-praxis/"
      write:
        - "{agent_root}/commons/data/ocas-praxis/"
        - "{agent_root}/commons/journals/ocas-praxis/"
    self_update:
      source: "https://github.com/indigokarasu/praxis"
      mechanism: "version-checked tarball from GitHub via gh CLI"
      command: "praxis.update"
      requires_binaries: [gh, tar, python3]
    cron:
      - name: "praxis:update"
        schedule: "0 0 * * *"
        command: "praxis.update"
---

# Praxis

Praxis is the system's behavioral self-improvement loop — it records real task outcomes, waits for patterns to emerge across multiple events, and then consolidates validated lessons into a small capped set of active behavior shifts that influence every future run. The cap of 12 active shifts is a hard constraint that prevents unbounded rule accumulation, and every shift must trace back to recorded events so nothing changes without an auditable reason.


## When to use

- Record a task outcome, failure, success, or correction
- Extract lessons from repeated patterns
- Review or manage active behavior shifts
- Generate the current runtime brief (active shifts only)
- Produce a debrief explaining what changed and why


## When not to use

- General knowledge storage — use Elephas
- Preference tracking — use Taste
- One-off trivia or domain facts
- Broad autobiographical summaries
- Silent personality mutation


## Responsibility boundary

Praxis owns bounded behavioral refinement: events, lessons, shifts, and debriefs.

Praxis does not own: general memory (Elephas), preference persistence (Taste), pattern discovery (Corvus), communications (Dispatch), skill evaluation (Mentor).

Praxis receives BehavioralSignal files from Corvus. Praxis decides whether to act on each signal.


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

1. Read BehavioralSignal files from `{agent_root}/commons/data/ocas-corvus/signals/`. Apply each signal: decide whether to record as an event and extract a lesson. Track consumed `signal_id` values in `signals_evaluated.jsonl` to avoid reprocessing.
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


## Capping and consolidation rules

Default cap: 12 active shifts. When at cap and a new shift is proposed: merge overlapping shifts, replace a weaker shift, or reject the new shift. No duplicate or contradictory active shifts.


## Runtime injection rules

The runtime brief is a compact list of active shifts only. Target: 3-12 items. Imperative, behavior-facing, free of historical clutter. Not a narrative log.


## Inter-skill interfaces

**Corvus → Praxis (cooperative read):** Praxis reads BehavioralSignal files from `{agent_root}/commons/data/ocas-corvus/signals/` on each heartbeat pass. Praxis decides whether to record each signal as an event and extract a lesson — it is not obligated to act on every signal. Consumed `signal_id` values are tracked in `signals_evaluated.jsonl`. Corvus does not write to Praxis's directories.

See `spec-ocas-interfaces.md` for the BehavioralSignal schema and handoff contract.


## Storage layout

```
{agent_root}/commons/data/ocas-praxis/
  config.json
  events.jsonl
  lessons.jsonl
  shifts.jsonl
  debriefs.jsonl
  decisions.jsonl
  signals_evaluated.jsonl
  reports/

{agent_root}/commons/journals/ocas-praxis/
  YYYY-MM-DD/
    {run_id}.json
```


Default config.json:
```json
{
  "skill_id": "ocas-praxis",
  "skill_version": "2.4.0",
  "config_version": "1",
  "created_at": "",
  "updated_at": "",
  "shifts": {
    "max_active": 12
  },
  "lessons": {
    "min_pattern_count": 2
  },
  "retention": {
    "days": 0,
    "max_records": 10000
  }
}
```


## OKRs

Universal OKRs from spec-ocas-journal.md apply to all runs.

```yaml
skill_okrs:
  - name: shift_traceability
    metric: fraction of active shifts with at least one traced event
    direction: maximize
    target: 1.0
    evaluation_window: 30_runs
  - name: cap_compliance
    metric: fraction of runs where active shift count is at or below cap
    direction: maximize
    target: 1.0
    evaluation_window: 30_runs
  - name: lesson_precision
    metric: fraction of extracted lessons leading to activated shifts
    direction: maximize
    target: 0.50
    evaluation_window: 30_runs
  - name: debrief_quality
    metric: fraction of debriefs rated useful by human review
    direction: maximize
    target: 0.80
    evaluation_window: 30_runs
```


## Optional skill cooperation

- Corvus — reads BehavioralSignal files from Corvus's `signals/` directory (cooperative read; Corvus owns)
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
3. Create empty JSONL files: `events.jsonl`, `lessons.jsonl`, `shifts.jsonl`, `debriefs.jsonl`, `decisions.jsonl`, `signals_evaluated.jsonl`
4. Create `{agent_root}/commons/journals/ocas-praxis/`
5. Register heartbeat entry `praxis:signals` in `HEARTBEAT.md` if not already present
6. Register cron job `praxis:update` if not already present (check the platform scheduling registry first)
7. Log initialization as a DecisionRecord in `decisions.jsonl`


## Background tasks

| Job name | Mechanism | Schedule | Command |
|---|---|---|---|
| `praxis:signals` | heartbeat | every heartbeat pass | Read BehavioralSignal files from `{agent_root}/commons/data/ocas-corvus/signals/`; process new signals (not in `signals_evaluated.jsonl`); record as events and extract lessons as appropriate |
| `praxis:update` | cron | `0 0 * * *` (midnight daily) | `praxis.update` |

Heartbeat registration: append `praxis:signals` entry to `{agent_root}/HEARTBEAT.md` if not already present.

Registration during `praxis.init`:
```
# Check platform scheduling registry for existing tasks
# Task declared in SKILL.md frontmatter metadata.{platform}.cron
```


## Self-update

`praxis.update` pulls the latest package from the `source:` URL in this file's frontmatter. Runs silently — no output unless the version changed or an error occurred.

1. Read `source:` from frontmatter → extract `{owner}/{repo}` from URL
2. Read local version from SKILL.md frontmatter `metadata.version`
3. Fetch remote version from SKILL.md frontmatter: `gh api "repos/{owner}/{repo}/contents/SKILL.md" --jq '.content' | base64 -d | grep 'version:' | head -1 | sed 's/.*"\(.*\)".*/\1/'`
4. If remote version equals local version → stop silently
5. Download and install:
   ```bash
   TMPDIR=$(mktemp -d)
   gh api "repos/{owner}/{repo}/tarball/main" > "$TMPDIR/archive.tar.gz"
   mkdir "$TMPDIR/extracted"
   tar xzf "$TMPDIR/archive.tar.gz" -C "$TMPDIR/extracted" --strip-components=1
   cp -R "$TMPDIR/extracted/"* ./
   rm -rf "$TMPDIR"
   ```
6. On failure → retry once. If second attempt fails, report the error and stop.
7. Output exactly: `I updated Praxis from version {old} to {new}`


## Visibility

public


## Support file map

| File | When to read |
|---|---|
| `references/data_model.md` | Before creating events, lessons, shifts, or debriefs |
| `references/lesson_rules.md` | Before extracting lessons from events |
| `references/runtime_rules.md` | Before generating runtime brief |
| `references/debrief_templates.md` | Before generating debriefs |
| `references/journal.md` | Before praxis.journal; at end of every run |

## Update command

This skill self-updates every 24 hours via:

```bash
praxis.update
```

This pulls the latest version from GitHub and restarts the skill's background tasks if applicable.
