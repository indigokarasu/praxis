---
name: ocas-praxis
source: https://github.com/indigokarasu/praxis
install: openclaw skill install https://github.com/indigokarasu/praxis
description: Use when recording outcomes, extracting micro-lessons from repeated patterns, managing capped behavior shifts (max 12 active), generating the runtime brief, or producing plain-language debriefs from the bounded behavioral refinement loop. Trigger phrases: 'record outcome', 'extract lesson', 'behavior shift', 'what have I learned', 'runtime brief', 'debrief', 'update praxis'. Do not use for general memory, personality rewriting, or knowledge storage.
metadata: {"openclaw":{"emoji":"🔄"}}
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

1. Check `~/openclaw/data/ocas-praxis/intake/` for BehavioralSignal files from Corvus; process and move to `intake/processed/`
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

Praxis receives BehavioralSignal files from Corvus at: `~/openclaw/data/ocas-praxis/intake/{signal_id}.json`

Praxis checks its intake directory during `praxis.event.record` and during any scheduled pass. Praxis decides whether to record each signal as an event and extract a lesson. It is not obligated to act on every signal.

After processing each file, move to `intake/processed/`.

See `spec-ocas-interfaces.md` for the BehavioralSignal schema and handoff contract.


## Storage layout

```
~/openclaw/data/ocas-praxis/
  config.json
  events.jsonl
  lessons.jsonl
  shifts.jsonl
  debriefs.jsonl
  decisions.jsonl
  intake/
    {signal_id}.json
    processed/
  reports/

~/openclaw/journals/ocas-praxis/
  YYYY-MM-DD/
    {run_id}.json
```


Default config.json:
```json
{
  "skill_id": "ocas-praxis",
  "skill_version": "2.3.0",
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

- Corvus — receives BehavioralSignal files via intake directory
- Dispatch — receives action decisions from Praxis for communication execution


## Journal outputs

Action Journal — every event recording, lesson extraction, shift change, and debrief generation.


## Initialization

On first invocation of any Praxis command, run `praxis.init`:

1. Create `~/openclaw/data/ocas-praxis/` and subdirectories (`intake/`, `intake/processed/`, `reports/`)
2. Write default `config.json` with ConfigBase fields if absent
3. Create empty JSONL files: `events.jsonl`, `lessons.jsonl`, `shifts.jsonl`, `debriefs.jsonl`, `decisions.jsonl`
4. Create `~/openclaw/journals/ocas-praxis/`
5. Register heartbeat entry `praxis:intake` in `HEARTBEAT.md` if not already present
6. Register cron job `praxis:update` if not already present (check `openclaw cron list` first)
7. Log initialization as a DecisionRecord in `decisions.jsonl`


## Background tasks

| Job name | Mechanism | Schedule | Command |
|---|---|---|---|
| `praxis:intake` | heartbeat | every heartbeat pass | Check `~/openclaw/data/ocas-praxis/intake/` for BehavioralSignal files from Corvus; process and move to `intake/processed/` |
| `praxis:update` | cron | `0 0 * * *` (midnight daily) | `praxis.update` |

Heartbeat registration: append `praxis:intake` entry to `~/.openclaw/workspace/HEARTBEAT.md` if not already present.

Registration during `praxis.init`:
```
openclaw cron list
# If praxis:update absent:
openclaw cron add --name praxis:update --schedule "0 0 * * *" --command "praxis.update" --sessionTarget isolated --lightContext true --timezone America/Los_Angeles
```


## Self-update

`praxis.update` pulls the latest package from the `source:` URL in this file's frontmatter. Runs silently — no output unless the version changed or an error occurred.

1. Read `source:` from frontmatter → extract `{owner}/{repo}` from URL
2. Read local version from `skill.json`
3. Fetch remote version: `gh api "repos/{owner}/{repo}/contents/skill.json" --jq '.content' | base64 -d | python3 -c "import sys,json;print(json.load(sys.stdin)['version'])"`
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
