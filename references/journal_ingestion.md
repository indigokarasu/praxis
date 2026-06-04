# Journal Ingestion — Signal Extraction Rules

## Pre-scan data hygiene (MANDATORY — run before every filesystem scan)

1. **Deduplicate `journals_evaluated.jsonl`** — read all entries, keep the first occurrence of each canonical `journal_id`, rewrite the file. Duplicates accumulate silently and cause scan misses.
2. **Compact if >5,000 entries** — entries older than 30 days can be removed. This keeps scan diffs fast.
3. Use JSON-aware tools for dedup (Python `json.loads` + dict by `journal_id`), not `grep`/`comm` which fail on mixed formats.

## Source

Praxis scans all skill journals at `{agent_root}/commons/journals/*/YYYY-MM-DD/`. Every skill writes journals as `{run_id}.json` files following the OCAS journal spec v1.3.

## Journal ID format

Each journal file is identified by `{skill_name}/{YYYY-MM-DD}/{run_id}.json`. Praxis tracks consumed journals in `journals_evaluated.jsonl` with entries like:
```json
{"journal_id": "ocas-spot/2026-05-23/r_abc123.json", "evaluated_at": "2026-05-23T12:30:00Z", "action_taken": "event_recorded"}
```

**Normalization rule:** Always normalize the `journal_id` to include the `.json` extension before writing to or looking up in `journals_evaluated.jsonl`.

**Recommended scan pattern (production-proven)**: Use a Python script that:
1. Deduplicates `journals_evaluated.jsonl` by `journal_id` (keep first occurrence)
2. Walks `commons/journals/*/` to build a set of all `.json` file paths for today and yesterday
3. Normalizes both filesystem paths and eval IDs to canonical `skill/YYYY-MM-DD/filename.json` form
4. Computes the set difference to find unevaluated journals
5. Skips files in `ocas-praxis/` and `ocas-lucid/` directories
6. Skips hidden/archive directories: any directory starting with `.`

## Signal extraction rules

From each new journal entry, Praxis extracts behavioral signals by examining:

1. **decision.execution_result.status** — `ok`, `partial`, or `error`. Any `error` or `partial` result is a candidate for event recording.
2. **decision.summary** — Only match keywords when summary is a non-empty string. Guard: `if summary and isinstance(summary, str) and len(summary.strip()) > 0`.
3. **decision.payload.entities_observed** — Entities tagged with `user_relevance: "user"` are higher priority.
4. **decision.payload.action_result.booked** / **.changed** / **.error** — Action outcomes indicating behavioral patterns.
5. **Top-level escalation_needed: true** — Direct escalation signal.
6. **actions_taken[].outcome** — Check for error/failure/correction outcomes.
7. **runtime.model** and **runtime.duration_seconds** — Unusually long runs or model fallbacks.

## Noise filters (MANDATORY — apply before recording any event)

These patterns produce false-positive signals. Check BEFORE recording:

### 1. `escalation_flagged` arrays in custodian journals
Custodian journals store `"escalation_flagged": ["issue_id_1", ...]` arrays. These are NOT new escalations — they track previously-known issues. **Do not keyword-match against JSON key names.** Only treat `escalation_needed: true` or `escalations[].type == "new_item"` as real escalation signals.

### 2. "Correction" keyword false positives
Summaries containing "correct", "fixed", "correction" in non-failure contexts (e.g., "correctly handled", "fixed-width format") are NOT correction events. Require one of:
- `execution_result.status` is `"partial"` or `"error"`
- `fixes_applied > 0`
- `actions_taken[].outcome` explicitly indicates a fix was applied

If `status` is `"ok"` and the only signal is a keyword match in the summary, **do not record**.

### 3. Dict-format summaries with success status
When `summary` is a dict and `status` is `"ok"`/`"success"`/`"completed"` or `type` is `"observation"`, the scan succeeded. Do NOT extract failure_keyword signals from its data fields (e.g., `"error_jobs": 7` fields that report on *other* systems).

### 4. Empty or None summary fields
When `decision.summary` is absent, empty, or None, do not attempt keyword matching. `str(None).lower()` produces `"none"` which won't match failure keywords, but calling `.lower()` on a dict or empty field produces spurious results.

### 5. `context_summary` field may be empty
Many legacy events have empty `context_summary`. Do not rely on keyword matching against this field alone. Filter by `outcome_type == "failure"` + `domain` first, then enrich with keyword scanning on non-empty summaries.

## When to record an event

Record a praxis event when ANY of the following are true (AND the noise filters above do not apply):
- The journal reports an error or partial failure
- The journal reports a user correction or complaint
- The journal reports an action with `changed: true` that succeeded after a prior failure
- The journal duration exceeds 5x the skill's average run time
- The decision summary contains keywords indicating a behavioral lesson

**Execute the fix — don't just summarize.** When you detect a failure signal, record the event AND extract a lesson in the same pass.

## When NOT to record

- Journal status is `ok` with no unusual patterns — **do not create an event**
- The run is a no-op — **do not create an event**
- No failure signals detected after running the full signal extraction checklist AND noise filters — **do not create an event**
- The journal is from ocas-praxis itself (avoid self-referencing loops)
- The journal is from ocas-lucid (Lucid already curates journals; don't double-process)
- The only signal is a keyword match in a summary where `status` is `"ok"` — **do not create an event**

**Enforcement rule:** If no signal is extracted from a journal after running the full signal extraction checklist and noise filters, that journal should only produce an entry in `journals_evaluated.jsonl` — NOT an event in `events.jsonl`.

## Failure-phase tagging

When recording an event from a journal, tag the `failure_phase` field:

| Phase | Indicators in journal |
|-------|-----------------------|
| **planning** | `decision.summary` contains "should have", "before", "wrong approach", "didn't check", "missing prerequisite" |
| **execution** | `execution_result.status` is `error` or `partial`, summary contains "failed", "timeout", "wrong parameter" |
| **response** | Summary contains "too verbose", "wrong format", "just give me", "make it concise", "don't explain" |
| **null** | Success events, observations without clear failure phase |

Phase tagging is mandatory for correction/failure events. Success events use `null`.

## Handling non-standard journal schemas

Not all skills produce journals that follow the standard OCAS v1.3 schema. When scanning a journal that doesn't match the expected schema:
1. Fall back to `summary` field for signal extraction (instead of `decision.summary`)
2. Check `actions_taken[].outcome` for "applied", "monitoring_continued", or error indicators
3. Treat `checks.fixes_applied > 0` as a success/correction signal
4. Treat any top-level `escalation_needed: true` as a failure-phase indicator
5. Don't error on missing `decision` or `execution_result` keys — just use what's available
6. Scan `new_findings[]` arrays — check each finding's `title`, `severity`, and `detail` fields for signal keywords. Findings with `severity: "info"` that reference already-known issues (via `related_issue` field) are lower priority.
7. For finch scan journals with `sources.*` structure: check each source's `status` field and `notes` for behavioral signals.
8. For mentor heartbeat journals that use `metrics.evaluation_coverage` below 0.5: flag as a planning-phase observation, but don't record as a failure event unless coverage has degraded >20% from the previous heartbeat.
9. **List-format journals** — Some journals are stored as a JSON array `[...]` at the top level. Check `isinstance(data, list)` first.
10. **`summary` field may be a dict** — Check the type before keyword scanning. If dict, use `json.dumps(d)` or extract specific text fields.

## Lesson extraction pass ordering (MANDATORY)

1. Read events.jsonl → existing_events
2. Process journals → write new events to events.jsonl
3. **Re-read events.jsonl** ← critical step
4. Run lesson extraction against the fresh list
5. Write new lessons, shifts, decisions

## Causal grounding requirement

Every extracted lesson must include at minimum the "what". Lessons that also include "why" and "when" are marked `confidence: high` and can immediately produce behavior shifts.

Lessons with only "what" are marked `confidence: low` and are held for one additional evidence-gathering cycle. If no "why" or "when" emerges after 2 hold cycles, the lesson is rejected with reason: "insufficient grounding."

**Reject empty stubs immediately** — If Pass 1 produces a lesson stub with empty `lesson_text` and Pass 2 cannot add grounding (no events with meaningful summaries), reject it on the spot. Do not write empty stubs to `lessons.jsonl`.

## Degraded mode

If no journal directories exist or all are empty, Praxis logs `degraded: journals` and continues. It will retry on the next cron cycle.
