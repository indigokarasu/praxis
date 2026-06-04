# Praxis Data Model

## Event

Events in practice use one of two schemas depending on when they were recorded. Both are valid:

**v2.8+ schema (preferred):**
```json
{"event_id":"string","timestamp":"string","domain":"string","context_summary":"string","outcome_type":"string — success|failure|correction|observation","outcome_summary":"string","evidence":["string"],"failure_phase":"string — planning|execution|response|null","user_relevance":"string — user|agent_only|unknown"}
```

**Legacy schema (still present in events.jsonl):**
```json
{"id":"string","timestamp":"string","source":"string","pattern":"string","pattern_category":"string","description":"string","confidence":"number","severity":"string — low|medium|high|tier_2","context_summary":"string","outcome_type":"string","outcome_summary":"string","evidence":["string"],"failure_phase":"string"}
```

Key differences: legacy events have `source` and `pattern` at top level and use `id` instead of `event_id`. New events use `domain` (broader than `source`) and encode pattern info in `context_summary`. When processing events for lesson extraction, normalize by reading both shapes — use `event_id || id` and `domain || source`.

The `failure_phase` field (added v2.8.0) tags the task phase where the failure occurred. This enables phase-specific lesson extraction and shift targeting. See `lesson_rules.md` for phase-aligned extraction rules.

## MicroLesson

The schema below is the canonical definition. In practice, lesson records use `lesson_text` for the human-readable summary AND `what`/`why`/`when` as structured elaborative interrogation fields. Both coexist in the same record — `what`/`why`/`when` are not replacements for `lesson_text`, they enrich it.

```json
{"id":"string","event_ids":["string"],"lesson_text":"string","confidence":"string — high|med|low","scope":"string","status":"string — proposed|accepted|rejected","failure_phase":"string — planning|execution|response|null","causal_grounding":"string — what|what+why|what+why+when","what":"string — optional, elaborative interrogation: what pattern occurred","why":"string — optional, elaborative interrogation: causal mechanism","when":"string — optional, elaborative interrogation: boundary conditions"}
```

The `causal_grounding` field (added v2.8.0) tracks whether the lesson includes:
- `what`: Only what happened (low confidence, held for more evidence)
- `what+why`: What + causal mechanism (medium confidence)
- `what+why+when`: Full elaborative interrogation (high confidence, can produce shifts immediately)

## BehaviorShift
```json
{"id":"string","source_lesson_ids":["string"],"shift_text":"string","status":"string — proposed|active|merged|expired|rejected","activation_reason":"string","created_at":"string","last_reviewed_at":"string","expiry_condition":"string|null","priority":"number","last_reinforced_at":"string","reinforcement_count":"number","failure_phase":"string — planning|execution|response|null"}
```

New fields (added v2.8.0):
- `last_reinforced_at`: ISO timestamp of last successful application. Used for decay tracking.
- `reinforcement_count`: Number of times this shift was successfully applied. Higher count = longer half-life.
- `failure_phase`: Which phase this shift targets. Prevents mixing phase targeting.

## Debrief
```json
{"id":"string","related_event_ids":["string"],"summary":"string","accepted_changes":["string"],"rejected_changes":["string"],"open_questions":["string"]}
```

## Storage layout

```
{agent_root}/commons/data/ocas-praxis/
  config.json
  events.jsonl
  lessons.jsonl
  shifts.jsonl
  debriefs.jsonl
  decisions.jsonl
  signals_evaluated.jsonl → journals_evaluated.jsonl  (renamed in v2.7.0 — tracks consumed journal IDs instead of signal IDs)
  intents.jsonl
  evidence.jsonl
  reports/
{agent_root}/commons/journals/ocas-praxis/
  YYYY-MM-DD/
    {run_id}.json
```

## Default config.json

> **Note (v3.0.0):** The running config has evolved beyond v2.8.0. The schema below reflects v3.0.0 fields. SKILL.md frontmatter may reference an older version.

```json
{
  "skill_id": "ocas-praxis",
  "skill_version": "3.0.0",
  "config_version": "2",
  "created_at": "",
  "updated_at": "",
  "shifts": {
    "max_active": 12,
    "ttl_days": 14,
    "proposed_ttl_days": 7,
    "auto_expire_enabled": true
  },
  "lessons": {
    "min_pattern_count": 2,
    "high_confidence_threshold": 0.9,
    "high_confidence_min_count": 1,
    "user_correction_min_count": 1,
    "pattern_categories_enabled": true
  },
  "retention": {
    "days": 0,
    "max_records": 10000
  }
}
```

Config changes in v3.0.0:
- `shifts.ttl_days` replaces `shifts.decay_days` (same semantics, clearer name)
- `shifts.proposed_ttl_days`: Days a proposed shift can remain proposed before auto-rejection (default: 7)
- `shifts.auto_expire_enabled`: Master switch for automatic shift expiry (default: true)
- `lessons.min_pattern_count`: Lowered to 2 (empirically, 2 same-phase events suffice)
- `lessons.high_confidence_threshold`: Confidence score above which a single event can produce a shift (default: 0.9)
- `lessons.high_confidence_min_count`: Events above threshold needed for single-event shift (default: 1)
- `lessons.user_correction_min_count`: User corrections always N=1 (immediate lesson)
- `lessons.pattern_categories_enabled`: Enable pattern_category tagging on events (default: true)
- Removed `shifts.stale_days` and `lessons.phase_aligned_min` (absorbed into category logic)

Legacy v2.8.0 fields (no longer used):
- `shifts.decay_days` → replaced by `shifts.ttl_days`
- `shifts.stale_days` → removed (auto_expire handles this)
- `lessons.phase_aligned_min` → absorbed into `pattern_categories_enabled`

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
  - name: schedule_adherence
    metric: fraction of scheduled cron runs that completed without skip
    direction: maximize
    target: 0.95
    evaluation_window: 30_runs
  - name: data_integrity
    metric: fraction of evidence records with valid schema and no missing mandatory fields
    direction: maximize
    target: 0.99
    evaluation_window: 30_runs
  - name: shift_decay_health
    metric: fraction of expired shifts that were decayed (not manually rejected)
    direction: maximize
    target: 0.80
    evaluation_window: 30_runs
  - name: causal_grounding_rate
    metric: fraction of accepted lessons with what+why+when grounding
    direction: maximize
    target: 0.70
    evaluation_window: 30_runs
```

New OKRs in v2.8.0:
- `shift_decay_health`: Measures whether the decay mechanism is working — shifts should expire naturally when not reinforced, not pile up until manually cleaned.
- `causal_grounding_rate`: Tracks lesson quality — grounded lessons produce better shifts.

## Cron registration commands

Used during `praxis.init` to register background cron jobs:

```bash
hermes cron create --name "praxis:journal_ingest" --schedule "*/30 * * * *" --prompt "Run praxis journal ingestion: scan all skill journals for new entries, extract behavioral signals, record events and lessons. Target: {agent_root}/commons/journals/"
hermes cron create --name "praxis:debrief" --schedule "0 6 * * *" --prompt "Run praxis debrief: review past 24h of events and lessons, propose/activate behavior shifts if patterns detected, check shift decay status, generate debrief."
hermes cron create --name "praxis:decay_check" --schedule "0 12 * * *" --prompt "Run praxis decay check: review all active shifts, check last_reinforced_at against decay_days threshold, expire stale shifts, flag shifts approaching expiry."
hermes cron create --name "praxis:update" --schedule "0 0 * * *" --prompt "praxis.update"
```

New in v2.8.0: `praxis:decay_check` runs at noon daily to check shift reinforcement status and expire decayed shifts before the daily debrief.

## Self-update procedure

`praxis.update` pulls the latest package from the `source:` URL in the skill's frontmatter. Runs silently — no output unless the version changed or an error occurred.

Steps:
1. Read `source:` from frontmatter → extract `{owner}/{repo}` from URL
2. Read local version from SKILL.md frontmatter `metadata.version`
3. Fetch remote version: `gh api "repos/{owner}/{repo}/contents/SKILL.md" --jq '.content' | base64 -d | grep 'version:' | head -1 | sed 's/.*"\(.*\)".*/\1/'`
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
