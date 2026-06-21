---
name: ocas-praxis
description: 'Bounded behavioral refinement loop. Records outcomes, extracts micro-lessons from repeated patterns, consolidates them into capped active behavior shifts, applies shifts at runtime, and generates plain-language debriefs. Use for recording task outcomes, extracting lessons from repeated patterns, managing active behavior shifts, generating runtime briefs, or producing debriefs. Do not use for general memory (use Elephas), preference tracking (use Taste), real-time task execution, content generation, system health monitoring (use Custodian), or skill evaluation scoring (use Mentor).'
license: MIT
source: https://github.com/indigokarasu/praxis
includes:
- references/**
- scripts/**
metadata:
  author: Indigo Karasu (indigokarasu)
  version: 3.2.1
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

Praxis is the system's behavioral self-improvement loop — it records real task outcomes, waits for patterns to emerge across multiple events, and consolidates validated lessons into a small capped set of active behavior shifts that influence every future run. The cap of 12 active shifts is a hard constraint that prevents unbounded rule accumulation, and every shift must trace back to recorded events so nothing changes without an auditable reason.

## When to Use

- Recording outcomes from skill executions
- Extracting lessons from repeated patterns
- Reviewing or managing active behavior shifts
- Generating the current runtime brief (active shifts only)
- Producing a debrief explaining what changed and why
- **Running scheduled cron ingest (praxis:journal_ingest)** — use the production-proven pattern in `scripts/ingest_cron_YYYYMMDD.py` and `references/ingest-script-pattern.md`
- **Running shift cleanup/consolidation** — use `scripts/shift_cleanup_YYYYMMDD.py` pattern
- **Running lesson noise cleanup** — use `scripts/lesson_cleanup_YYYYMMDD.py` pattern
- **Generating daily debrief** — use `scripts/debrief_YYYYMMDD.py` template

## When NOT to Use

- General knowledge storage — use memory tool
- Preference tracking — use Taste
- One-off trivia or domain facts
- Broad autobiographical summaries
- Silent personality mutation

## Responsibility Boundary

Praxis owns bounded behavioral refinement: events, lessons, shifts, and debriefs.

Praxis does not own: general memory (use memory tool), preference persistence (Taste), pattern discovery (Finch), communications (Dispatch), skill evaluation (Mentor).

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

1. Record event → 2. Extract lessons (if pattern detected) → 3. **Upgrade lessons** — mandatory second pass to add causal grounding (what/why/when) and set `confidence: high` → 4. **Dedup lessons against active shifts** — before writing new lessons, check if an active shift already covers the same `(signal_type, failure_phase)` key; if yes, skip lesson creation (the shift already encodes it) → 5. Propose shift (check domain+phase overlap, handle mixed schemas) → 6. Activate (if cap allows) → 7. Generate debrief

**Two-pass lesson extraction is mandatory.** Pass 1 groups events by signal_type+phase and produces lesson stubs. Pass 2 adds full causal grounding (what/why/when) and upgrades confidence to `high`. Without Pass 2, no lessons can produce shifts. See `references/ingest-script-pattern.md` for the production-proven script.

**Lesson extraction scope: NEW EVENTS ONLY.** Pass 1 must group only events added in the current ingest run (or since the last lesson extraction), NOT the entire `events.jsonl` history. Re-processing all 2,500+ events every run causes: (a) stale lessons re-created for patterns that are no longer active, (b) unknown-domain lessons from legacy events that lack a `skill` field, (c) noise lessons (`no_active_watches`, `system_memory_drop`) that pass the ≥2 event threshold from historical accumulation. Track `last_lesson_extraction_event_id` in the ingest state and filter `all_events` to only events with `event_id` greater than that marker before grouping. See `references/session_20260618_ingest_cron_d.md`.

**Ingest state file (`ingest_state.json`) — create if missing.** The state file at `{agent_root}/commons/data/ocas-praxis/ingest_state.json` tracks `last_lesson_extraction_event_id` for scoped lesson extraction. If the file doesn't exist, create it with `{"last_lesson_extraction_event_id": null}` on first run. Without this file, the lesson extraction scoping mechanism cannot function and falls back to full-history re-processing.

**Fixing `last_lesson_extraction_event_id` after sessions with no events:** If the ingest state shows `last_lesson_extraction_event_id: null` but `events.jsonl` has entries, the scoping mechanism is broken — lesson extraction will re-process the full history every run, producing stale lessons. Fix by setting it to the last event's ID:
```bash
# Get the last event_id from events.jsonl
LAST_EVT=$(tail -1 {root}/commons/data/ocas-praxis/events.jsonl | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('event_id',''))")
# Update the state file
python3 -c "import json; f='{root}/commons/data/ocas-praxis/ingest_state.json'; s=json.load(open(f)); s['last_lesson_extraction_event_id']=''$LAST_EVT''; json.dump(s, open(f,'w'), indent=2)"
```
After 2026-06-21 dispatch (0 events from 4 mentor-light journals), the state should be set to the last existing event in `events.jsonl` (e.g., `evt-20260621...`).

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

**Shift decay:** Active shifts not reinforced in 14+ days auto-expire. Reinforcement extends half-life. Debriefs should flag shifts at 10+ days without reinforcement as "approaching decay" — on 2026-06-14, all 11 active shifts were 12-13 days old with 0 reinforcements, one day from mass expiry, but the debrief reported no action needed.

**Elaborative interrogation:** Lessons must capture WHAT happened, WHY, and WHEN. Format: `[LESSON] What: <pattern>. Why: <cause>. When: <conditions>`

**Failure-phase tagging:** Tag each event with the task phase (Planning, Execution, Response). See `references/gotcha_failure_phase_tagging.md`.

## Data Model and Storage

See `references/data_model.md` for full storage layout, JSON schemas, default config, and OKRs.

Key storage paths:
- Data: `{agent_root}/commons/data/ocas-praxis/`
- Journals: `{agent_root}/commons/journals/ocas-praxis/YYYY-MM-DD/{run_id}.json`

## Inter-skill Interfaces

**All skills → Praxis (cooperative read):** Praxis scans journal output from every skill. Consumed `journal_id` values tracked in `journals_evaluated.jsonl`.

Known journal-producing skills: ocas-spot, ocas-rally, ocas-taste, ocas-finch, ocas-fellow, ocas-scout, ocas-bones, ocas-bower, ocas-vibes, ocas-voyage, ocas-imagine, ocas-weave, ocas-vesper, ocas-dispatch, ocas-mentor, ocas-lucid, ocas-sands, ocas-sift, ocas-reach, ocas-look, ocas-multipass, ocas-forge, ocas-haiku, ocas-custodian.

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

## Dispatch / Cron Integration

When triggered by the dispatcher (`dispatcher.py`) or a cron job:

1. **Capture pre-run timestamp** — BEFORE running any sibling skill pipelines (e.g., Mentor heartbeat), read `ingest_state.json:last_ingest_run` and capture it. The Mentor heartbeat script updates this timestamp, which would cause Praxis mtime-based discovery to miss journals written before the heartbeat ran.

2. **Determine new journals** — use mtime-based discovery with the **captured** timestamp (not a fresh read of the state file):
   ```bash
   # Compare file mtime against the CAPTURED timestamp (not current state file)
   find {journals_dirs} -name "*.json" -newermt "{captured_timestamp}" 2>/dev/null
   ```
   The `journals_evaluated.jsonl` dedup is broken (path format mismatch) — mtime comparison is the reliable method.

3. **Run ingest** — use the production template `templates/dispatch_ingest_template.py` as a starting point:
   ```bash
   cp templates/dispatch_ingest_template.py scripts/dispatch_ingest_YYYYMMDD.py
   python3 scripts/dispatch_ingest_YYYYMMDD.py
   ```
   The template implements all mandatory gotcha filters (mentor-light noise, forge no-op, mixed-format eval handling).

4. **Post-ingest cleanup** — clean up stale scripts from the data directory root (see "Stale Script Cleanup" section in SKILL.md body).

5. **Write journal** — call `praxis.journal` with dispatch metadata.

**CRITICAL: Cross-pipeline state collision fix** — When the dispatcher triggers Forge + Mentor + Praxis in sequence, the Mentor heartbeat's `cron-heartbeat-light.py` updates `ingest_state.json:last_ingest_run` to a timestamp AFTER the mentor-light journal was written. If Praxis then reads the state file to determine new journals, the mtime comparison `journal_mtime > last_ingest_run` fails because the journal is now "older" than the state timestamp. The journal is missed. **Fix:** Capture `last_ingest_run` from `ingest_state.json` at the START of the dispatch (before Mentor runs), and pass that captured timestamp to Praxis mtime discovery. Confirmed 5+ times (2026-06-21).

**Multi-skill dispatch pattern:** When the dispatcher triggers Forge + Mentor + Praxis, each pipeline runs independently. Praxis reads journals produced by other skills (especially mentor-light and forge) but does not block on them. See `references/session-20260621-dispatch-2.md` for a worked example with 0-event clean result.

## Journal Outputs

Action Journal — every event recording, lesson extraction, shift change, and debrief generation. Include `entities_observed`, `relationships_observed`, `preferences_observed` with `user_relevance` field.

## Optional Skill Cooperation

- All OCAS skills — Praxis reads journal output (cooperative read)
- Dispatch — receives action decisions for communication execution

## Data Directory Path

**The Praxis data directory is profile-specific.** The correct path is:
```
/root/.hermes/profiles/<profile>/commons/data/ocas-praxis/
```
NOT `/root/.hermes/commons/data/ocas-praxis/` (the default profile path).

The `scripts/praxis_review.py` review script hardcodes the wrong path. Any ad-hoc scripts must use profile-aware resolution or the indigo-specific path. Always verify `events.jsonl` exists at the target path before running.

**Ingest state file:** `{agent_root}/commons/data/ocas-praxis/ingest_state.json` tracks `last_lesson_extraction_event_id` for scoped lesson extraction. Create with `{"last_lesson_extraction_event_id": null}` if missing.

## Debrief Generation

When running `praxis.debrief.generate` outside the scheduled cron:

1. **Load active shifts** from `shifts.jsonl` — filter `status == "active"`, count reinforcement, compute age from `activated_at` or `last_reinforced_at`
2. **Scan for decay risk** — shifts with `reinforcement_count == 0` and age > 10 days are "approaching decay" (flag in debrief)
3. **Scan for overlap** — group active shifts by domain+phase; flag shifts sharing >3 words as potential consolidation candidates
4. **Count recent events** — last 200 events by signal_type to identify emerging patterns
5. **Check cap headroom** — if active shifts ≥ 10, flag "approaching cap" with weakest shift identified for potential manual expiry
6. **Write structured debrief** to `debriefs.jsonl` with fields: `debrief_id`, `generated_at`, `period`, `active_shift_count`, `cap_usage`, `new_shifts`, `expired_shifts`, `new_lessons`, `findings`, `recommendations`
7. **NEVER use `write_file` on JSONL files** — it overwrites. Use `terminal("python3 -c ...")` or append via `open(..., 'a')`

Debrief JSON structure:
```json
{
  "debrief_id": "debrief-YYYYMMDDTHHMMSS",
  "generated_at": "ISO timestamp",
  "period": "YYYY-MM-DD to YYYY-MM-DD",
  "active_shift_count": 12,
  "cap_usage": "12/12 (at cap)",
  "new_shifts": 0,
  "expired_shifts": 0,
  "new_lessons": 1,
  "findings": ["finding 1", "finding 2"],
  "recommendations": ["rec 1", "rec 2"],
  "events_ingested": 0,
  "lessons_extracted": 0,
  "shifts_proposed": 0,
  "shifts_activated": 0,
  "shifts_expired": 0
}
```

## Eval File Path Mismatch (Operational Issue — 2026-06-19)

- **Eval file path format mismatch — workaround: use mtime, not dedup** — The `journals_evaluated.jsonl` file stores journal IDs in a different format than filesystem scans produce. Eval file stores `ocas-mentor/mentor-light-20260620T091801Z.json` (no date dir) while filesystem scan produces `ocas-mentor/2026-06-20/mentor-light-20260620T091801Z.json` (with date dir). The dedup mechanism cannot match, so every journal appears unevaluated. **Workaround:** Determine new journals by comparing file mtime against `ingest_state.json:last_ingest_run` timestamp, bypassing the broken dedup. See `references/session-20260620-dispatch.md`.

**Root cause:** The eval file was rebuilt from a disk scan on 2026-06-15 using a different `path_to_journal_id` function than subsequent ingest runs. The eval file stores IDs like `ocas-mentor/mentor-light-20260619T233559Z.json` (no date directory) while the filesystem scan produces `ocas-mentor/2026-06-19/mentor-light-20260619T233559Z.json` (with date directory).

**Impact:** The dedup mechanism cannot match, so every journal appears unevaluated. Ingest runs waste time scanning already-evaluated journals. New journals may be missed in the noise.

**Fix needed:** Normalize eval IDs at the start of each ingest run — for each entry in `journals_evaluated.jsonl`, compute both possible path forms (with/without date directory, with/without `.json` extension) and check against both. Alternatively, rebuild the eval file from the current filesystem scan using the canonical `path_to_journal_id` function.

**Workaround:** The actual new journals since last ingest can be determined by comparing file mtime against `ingest_state.json:last_ingest_run` timestamp, bypassing the broken dedup for new-journal detection.

## Stale Script Cleanup

Every ingest run writes a new `.py` file to the data directory. Over weeks, 40+ stale scripts accumulate (116 files / 1.7MB observed 2026-06-22). **At the end of each ingest run, clean up stale scripts:**

```python
# At end of main(), before final summary:
import glob
stale_patterns = [
    'ingest_cron_*.py', 'ingest_*.py', 'scan_*.py', 'cleanup_*.py',
    'lesson_extract_*.py', 'lesson_cleanup_*.py', 'shift_cleanup_*.py',
    'shift_repair_*.py', 'debrief_*.py', 'analyze_patterns*.py',
]
# CRITICAL: Only clean the data directory root, NOT the scripts/ subdirectory
removed = 0
for pattern in stale_patterns:
    for f in glob.glob(os.path.join(DATA_DIR, pattern)):
        os.remove(f)
        removed += 1
if removed:
    print(f"  Cleaned up {removed} stale scripts from data root")
```

**Production scripts live in `scripts/` and must NOT be removed.** The `scripts/` subdirectory at `{agent_root}/commons/data/ocas-praxis/scripts/` is the canonical location. Production scripts: `praxis_review.py`, `praxis_ingest_run.py`, `praxis_self_signaler.py`, `update.sh`, `praxis_common.py`. If any production scripts are found in the data directory root (not in `scripts/`), move them to `scripts/` rather than deleting — they may have been placed there by a previous ingest or manual operation. In the 2026-06-19 ingest, an overly broad cleanup deleted 46 files including production scripts that had been copied to the data root. Recovery required copying from the skill directory.

## Gotchas — Critical

See `references/gotchas-praxis.md` for the full gotcha catalog (30+ operational pitfalls).

Key gotchas:

- **Dedup key must be `(source_journal, signal_type)`** — Using `source_journal` alone as the dedup key in `events.jsonl` post-write dedup collapses multiple distinct signals from the same journal into one event. In ingest_20260606_v3, finch scan-1800 produced both `cron_errors` and `auth_failure` signals, but only the first survived dedup — the second had to be recovered manually. This matches the known limitation documented in `ingest-script-pattern.md` §Post-Write Dedup. **Always dedup by `(source_journal, signal_type)`**, not just `source_journal`.

- **Shift cap enforcement requires proactive merge-before-cap, not just reject-at-cap** — When proposing shifts, the merge-overlap check (domain+phase) MUST happen BEFORE the cap check. In the 2026-06-17 ingest, 5 new shifts were proposed and activated before the cap was hit, but 2 were duplicates of existing active shifts (same signal_type+phase). The merge logic caught them during cleanup, but the original ingestion didn't merge at proposal time — it just let them fill the cap. **Fix:** The shift proposal loop must check domain+phase overlap against ALL active shifts and merge/reinforce instead of proposing new shifts when overlap exists. This prevents cap saturation with duplicates.

- **Noise signal types must be filtered at lesson creation, not just shift proposal** — The 2026-06-17 ingest produced 5 noise lessons (`routine`, `no_signal`, `cron_error`, `forge_activity`, `no_op`, `success`) with `confidence: high` that then produced shifts. The NOISE_SIGNAL_TYPES filter exists in the ingest script but wasn't applied during lesson extraction Pass 2. **Fix:** Apply `NOISE_SIGNAL_TYPES = {"", "unknown", "?", "no_op", "forge_activity", "routine", "no_signal", "cron_error", "cron_errors", "observation", "success", "mentor_light"}` filter immediately after Pass 2 grounding, BEFORE writing to `lessons.jsonl`. This prevents noise from ever entering the lesson pool.

- **Mentor-light `low_coverage` is a measurement artifact — filter at extraction time** — The `evaluation_coverage` metric in mentor-light heartbeats (0.14–0.30) only counts skills with new journal entries in the scan window, NOT total active skills (which is 20+). The mentor correctly reports `active_skills_30d: 20` alongside `evaluation_coverage: 0.3` because only ~6 of 20 skills had new files. This is expected scan-yield behavior, NOT a system failure. When mentor-light journals produce `low_coverage` as their only non-success signal, emit `no_signal` instead of recording a `low_coverage` event. Do NOT add `low_coverage` globally to NOISE_SIGNAL_TYPES — it may be legitimate from other sources. Filter specifically: if `source_journal` matches `mentor-light-*` and `signal_type == "low_coverage"` and `outcome == "success"`, skip event recording. Discovered 2026-06-18: mentor-light `low_coverage` reached 11 events and produced a lesson + shift that is semantically meaningless. See `references/session_20260618_ingest_cron_z.md`.

- **Mentor-light `gap_detected` with `outcome: "success"` is a routine measurement — filter at extraction time** — The `gap_detected` flag in mentor-light heartbeats fires when the time since the last scan exceeds a threshold (typically 25-30 minutes). This is normal cron cadence behavior, NOT a system failure. The `gap_minutes` field (e.g., 27.2) is within expected range for 30-minute cron intervals. When mentor-light journals produce `gap_detected: true` with `outcome: "success"` and no other failure signals, emit `no_signal` instead of recording a `gap_detected` event. Filter specifically: if `source_journal` matches `mentor-light-*` and `signal_type == "gap_detected"` and `outcome == "success"`, skip event recording. Adding `gap_detected` globally to NOISE_SIGNAL_TYPES would hide genuine gap detections from other sources (e.g., custodian). The existing active shift `gap_detected | ocas-mentor | Execution` already covers gap detection behavior; adding routine cron-cadence events only creates duplicate noise. Discovered 2026-06-20: mentor-light `gap_detected` produced an event from a 27.2-minute gap that was pure cron cadence.

- **Mentor-light `failure_keyword` from generic summary scanner is a false positive — filter at extraction time** — Mentor-light heartbeat journals with `outcome: "success"` (or no `outcome` field) contain summary text like "0 errors detected", "2 historical error records in evidence", or "0 active anomalies". The generic summary scanner picks up the word "error" and emits a `failure_keyword` signal — but the journal is reporting SUCCESS, not failure. When mentor-light journals have `outcome in ("success", "", None)` and no explicit failure indicators (`gap_detected: true` or `metrics.errors > 0`), skip ALL generic signal extraction and return `no_signal`. Do NOT rely on the `signal_type` field alone — these journals may not have one, and the generic path assigns `failure_keyword` from summary text. Filter at the journal level, not the signal level. Discovered 2026-06-20: 8 false-positive `failure_keyword` events from mentor-light journals in a single ingest run. See `references/session_20260620_ingest.md`.

- **Custodian `action` journals with error mentions in summary are routine operational reports — filter at extraction time** — Custodian light-scan/action journals (type: `"action"`) routinely contain summary text like "All other error jobs are either transient (429), no-op exits, disabled, or already tracked" when reporting on known cron job states. The generic summary scanner picks up "error" and emits a `failure_keyword` signal — but the journal is reporting on known/tracked issues, not a new behavioral failure. When a custodian journal has `type: "action"` and the summary contains "error" but `escalation_needed` is absent or the journal is a routine scan (no new `findings` with `severity: "critical"`), skip generic signal extraction and return `no_signal`. The existing `observation` type filter only covers `type == "observation"` — the `action` type with error mentions is a distinct false-positive source. Discovered 2026-06-21: custodian light-scan action journal produced a `failure_keyword` event from summary text about known error jobs. A single event won't produce a lesson (needs ≥2), but it pollutes the event stream. See `references/session-20260621-dispatch-9.md`.

- **Custodian `type: "observation"` is a routine scan — emit `no_signal`**

- **Custodian `type: "observation"` is a routine scan — emit `no_signal`** — Custodian journals with `type: "observation"` are routine platform scans that check gateway status, disk usage, and job health. They do not represent behavioral signals. When a custodian journal has `type: "observation"`, emit `no_signal` and skip signal extraction. This is distinct from custodian `deep-scan` or `light-scan` types which may contain genuine signals. Confirmed 2026-06-21: custodian observation journal produced no actionable signals.
- **Lesson content dedup required** — The `lesson_id` includes a random/timestamp component, so dedup by `lesson_id` alone does NOT prevent semantic duplicates. Each ingest run generates different IDs for the same `(signal_type, phase)` group. **Always dedup by `(signal_type, failure_phase)` content fingerprint before writing lessons.** See `ingest-script-pattern.md` §Lesson Content Dedup. Without this, `lessons.jsonl` grows by ~9-49 duplicate entries per run.

- **Lesson dedup key must normalize `failure_phase` to lowercase** — The `(signal_type, failure_phase)` dedup key is case-sensitive. Existing lessons may have `failure_phase: "Planning"` (capitalized) while new lessons produce `failure_phase: "planning"` (lowercase), causing the dedup to miss the match and create a semantic duplicate. In the 2026-06-22 ingest, a `coverage_gap` lesson was duplicated because `"Planning" != "planning"`. **Fix:** Normalize both sides to lowercase before comparison:
  ```python
  def lesson_dedup_key(les):
      st = les.get("signal_type", "").strip().lower()
      phase = les.get("failure_phase", "execution").strip().lower()
      return (st, phase)
  ```
  Apply this to both the new lesson AND when building the existing-lesson dedup set. Also apply in Pass 1 event grouping — normalize `failure_phase` before grouping to prevent split groups across case variants. See `references/session_20260622_ingest_followup.md`.
- **Active shift cap is hard** — 12-shift cap enforced on every activation
- **Lessons require causal grounding** — "do X because Y" not just "do X"
- **Forge `result` field has multiple no-op variants** — Forge scan journals use `result: "no_op"`, `result: "clean"`, `"no-op"` (hyphenated), `"NO_UNPROCESSED_FILES"` (uppercase), and longer strings like `"clean — no pending VariantProposal or VariantDecision files"` or `"clean — no unprocessed VariantProposal or VariantDecision files found"` to indicate routine success (nothing to process). All are healthy system states. **Fix:** Define `FORGE_NO_OP_RESULTS = {"no_op", "clean", "no-op", "no_unprocessed_files"}` and check `result.lower().strip() in FORGE_NO_OP_RESULTS`. Do NOT rely on exact string matching against `"no_op"` alone. The status-less forge schema variant (no `result` key, no `status` key, or empty summary string) is also a no_signal — treat as routine no-op when no other failure indicators are present. See `references/session_20260616_ingest_cron_afternoon2.md` for the full variant catalog.
- **Forge no-op filter must use `startswith`, not exact match** — Forge result strings routinely include trailing detail text after the no-op keyword (e.g., `"clean \u2014 no unprocessed VariantProposal or VariantDecision files found"`). The `FORGE_NO_OP_RESULTS` set check with `result.lower().strip() in FORGE_NO_OP_RESULTS` does NOT match these longer strings, causing false-positive `forge_error` events. In the 2026-06-16 18:26 ingest, 2 false-positive events and 1 false lesson were produced before manual cleanup. **Fix:** Replace the exact-match check with a `startswith` loop:
  ```python
  def is_forge_no_op(result_val):
      if not result_val:
          return False
      r = str(result_val).lower().strip()
      return any(r.startswith(prefix) for prefix in FORGE_NO_OP_RESULTS)
  ```
  Or split on the em-dash/whitespace and check only the first token: `r.split('\u2014')[0].strip().split()[0] in FORGE_NO_OP_RESULTS`.
- **Forge no-op `FORGE_NO_OP_RESULTS` must include `"no unprocessed"` (with spaces)** — The set typically includes `"no_unprocessed_files"` (underscores), but forge journals write natural language with spaces: `"No unprocessed VariantProposal..."`. The `startswith` check against `"no_unprocessed_files"` does NOT match `"no unprocessed variant..."`. **Fix:** Add `"no unprocessed"` to the prefix set: `FORGE_NO_OP_RESULTS = {"no_op", "clean", "no-op", "no_unprocessed_files", "no unprocessed"}`.

- **Forge `actions_taken` can be an empty list `[]` with no `result` field** — Some forge journal variants (post-2026-06-19) have `actions_taken: []` (empty list), no `result` key, no `status` key, and `findings: {unprocessed_proposals: 0, ...}`. The forge no-op filter that only checks `result` and `status` fields misses this variant, causing it to fall through to signal extraction (where it produces no signals but is classified as `no_signal` instead of `forge_no_op`). **Fix:** In `is_forge_no_op()`, also check: (1) `actions_taken` as a string with `startswith` against `FORGE_NO_OP_RESULTS`, and (2) `actions_taken` as an empty list combined with zero findings. See `references/session_20260619_ingest_cron_c.md`.
- **Finch `action.result` instead of top-level `result`** — Newer forge journals (post-2026-06-16) nest the result under `action.result` (e.g., `{"action": {"result": "no_new_files"}}`). The forge no-op pre-filter only checks `data.get("result", "")` at the top level. **Fix:** Also check `data.get("action", {}).get("result", "")` in `is_forge_no_op()`. But note: `action` can also be a **string** (e.g., `"No unprocessed VariantProposal or VariantDecision files found..."`) — always guard with `isinstance(action, dict)` before `.get("result")`.

- **`finch_actionable_email` is a legitimate signal type — NOT noise** — Finch scan journals produce `actionable` email counts when new emails require attention (job opportunities, application updates, etc.). This is a genuine positive signal, not a no-op. **Do NOT add `finch_actionable_email` to `NOISE_SIGNAL_TYPES`.** The signal should produce events and, when ≥2 events accumulate, lessons. The only filter: if `actionable == 0`, skip (no new emails to act on). Discovered 2026-06-20: 12 finch_actionable_email events from 10 scans produced the first finch lesson.
- **Finch `new_tasks_added` is a list, not an int** — Finch scan journals store `new_tasks_added` as a list of task dicts, NOT as an integer. Checking `data.get("new_tasks_added", 0) > 0` crashes with `TypeError`. **Fix:** Use `len(new_tasks) if isinstance(new_tasks, list) else (new_tasks if isinstance(new_tasks, int) else 0)`.
- **Initialize ALL accumulator variables before any loop or conditional** — `truly_new`, `remaining_proposals`, and any accumulator must be initialized before the `if`/`for` block that might define it. A variable assigned only inside a `for/else` body does not exist when the loop iterates 0 times, causing `NameError` after data writes have already completed.
- **Cap enforcement must use a separate counter, not the mutable list** — When activating shifts in a loop, do NOT check `len(active_shifts)` if you're appending to `active_shifts` inside the same loop. The list grows on every iteration and the cap is never enforced. Use a separate `active_count` variable computed once before the loop, and increment it manually on each activation.

- **Cap enforcement must use full file rewrite, not append-only** — When the cap is exceeded and a shift is expired in-memory to make room for a new one, the expired shift's status change is NOT persisted if you only append new shifts to `shifts.jsonl`. The expired shift remains `active` on disk. **Fix:** After all in-memory modifications (reinforce, expire, activate), do a FULL rewrite of `shifts.jsonl` from the canonical in-memory state. Track new shifts separately and only append those if you must use append-only — but prefer full rewrite. See `references/session_20260618_ingest.md` for the repair procedure.

- **Shift file rewrite must not double-write** — When rewriting `shifts.jsonl` after modifying active shifts in memory, do NOT write `existing_shifts` (which includes all old shifts, already expired ones and all) AND then append `new_shifts`. Either: (a) rewrite the entire file from the merged in-memory list, or (b) append only new shifts to the existing file (don't re-write existing entries). In the 2026-06-18 repair, the rewrite wrote `existing_shifts` (78 entries) + `new_shifts` (12 entries) = 90 entries total. A subsequent re-read showed 78 + 12 = 90, but the old active shifts were already expired in-memory so the file was correct by accident. Be explicit: either full rewrite from canonical in-memory state, or append-only for new entries.

- **Domain must be the skill name, not the signal_type** — When proposing shifts from events, `domain` must be set to the skill that produced the events (e.g., `ocas-mentor`), NOT to the `signal_type` (e.g., `gap_detected`). Setting `domain = signal_type` produces meaningless shifts like "In gap_detected during Planning: gap_detected recurs" instead of "In ocas-mentor during Planning: gap_detected recurs". **Fix:** Use the `skill` field from the events that contributed to the lesson, or use the most common skill in the event group as the domain. Only fall back to `signal_type` as domain if no skill information is available.
- **Lesson extraction must filter events with null/None/empty failure_phase** — Before grouping events for lesson extraction, filter out events where `failure_phase` is `None`, `null`, `""`, or `"MISSING"`. These produce meaningless lessons like "Monitor and address X during None phase". In the 2026-06-16 ingest, 90 events with invalid phases produced 26 bad lessons. **Fix:** Add `valid_events = [e for e in all_events if e.get('failure_phase') and str(e.get('failure_phase')).lower() not in ('none', 'null', '', 'missing')]` before the grouping loop.
- **Inline ingest scripts must implement all documented gotcha filters** — When writing ad-hoc ingest scripts (rather than using the production `praxis_ingest_run.py`), it is NOT sufficient to follow only the basic scan/extract/append pattern. ALL gotcha-documented filters must be implemented: null-phase event filtering before lesson grouping, `NOISE_SIGNAL_TYPES` filtering before lesson write, forge no-op detection with `startswith`, spot no-op detection, summary string suppression, and `(source_journal, signal_type)` dedup. In the 2026-06-17 ingest, an inline script skipped the null-phase filter and the `success` noise type, producing 4 noise lessons and 2 noise shifts that required post-hoc cleanup. **Fix:** Before writing any ingest script, review the full gotcha catalog and implement every filter marked MANDATORY.

- **Lesson extraction must scope to NEW events only — re-processing full history creates stale lessons** — The lesson extraction Pass 1 groups events by `(signal_type, failure_phase)` and emits lessons for any group with ≥2 events. If `all_events` is loaded from the entire `events.jsonl` history (2,500+ events), every re-run re-creates lessons for stale patterns and produces noise lessons from historically-accumulated events. In the 2026-06-18 ingest, 8 lessons were created from the full history: `no_active_watches` (5 spot sweep events), `system_memory_drop` (2 finch events), `failure` (28 legacy events, domain: unknown), and 4 legitimate patterns. Only the 4 legitimate ones survived cleanup. **Fix:** Before Pass 1 grouping, filter `all_events` to only events recorded in the current ingest run (or since `last_lesson_extraction_event_id`). Track the last processed event ID in the ingest state file. This prevents stale lessons from being re-created and keeps the lesson pool focused on emerging patterns. See `references/session_20260618_ingest_cron_d.md`.

- **`tier_1_fixes_applied` field can be `int` or `list`** — Custodian journals store `tier_1_fixes_applied` as either an integer count (e.g., `3`) or a list of fix descriptions (e.g., `["fix1", "fix2"]`). Any ingest script that calls `len(data.get("tier_1_fixes_applied", []))` will crash with `TypeError: object of type 'int' has no len()` when the field is an integer. **Fix:** Check type before counting: `fixes = data.get("tier_1_fixes_applied", []); fixes_count = fixes if isinstance(fixes, int) else len(fixes) if isinstance(fixes, list) else 0`. Discovered 2026-06-17: ingest_cron_20260618_g.py crashed on first custodian journal with `tier_1_fixes_applied: 3`.

- **`new_errors` field can be `None`** — Custodian journals may have `new_errors: null` (JSON null → Python None) rather than `[]` or a list. Iterating over `None` raises `TypeError: 'NoneType' object is not iterable`. **Fix:** Use `data.get("new_errors", []) or []` to coerce None to empty list. This is the same class of bug as other nullable array fields in custodian journals.

- **Two journal directory paths exist — MUST scan both** — Journals are stored under BOTH `/root/.hermes/commons/journals/` (legacy/default profile) AND `/root/.hermes/profiles/indigo/commons/journals/` (indigo profile). Different skills write to different paths: forge/finch/spot write to legacy; custodian/mentor write to indigo. **Fix:** Maintain a `JOURNALS_DIRS` list with both paths and a `find_journal(jid)` helper that checks each. Walk BOTH directories when scanning for unevaluated journals. See `references/ingest-script-pattern.md` §Dual Journal Directory Scan.
- **Spot observation no-op handler must gate ALL signal paths** — When a spot journal has `type: "observation"` and the summary contains known transient platform phrases ("skipped", "permanently broken", "dead watch", "expired", "no new availability"), the handler must emit `no_signal` and skip signal extraction entirely. Use a `skip_signals = False` flag set BEFORE the signal extraction block, check it with `if skip_signals: continue` AFTER extraction, rather than relying on `continue` inside nested conditionals that may not execute. The `summary` variable must be initialized before the spot handler runs.
- **`execute_code` is blocked in cron context** — Use `terminal()` to run Python scripts. Do NOT use heredoc (`<< 'PYEOF'`) — shell metacharacters inside Python code (e.g., `&` in comparisons, backticks, `$()`) cause the shell to interpret them and the command fails with "Foreground command uses '&' backgrounding." The reliable pattern: **write the script to a `.py` file via `write_file()`, then execute it via `terminal(command="python3 /path/to/script.py")`. This works in both interactive and cron contexts.

- **`write_file` can corrupt Python syntax — always compile-check after writing `.py` files** — The `write_file` tool can escape braces in Python dict literals and f-strings (e.g., `{"key": "value"}` becomes `{\"key\": \"value\"}` or `"}` becomes `"}` with a stray closing brace). This produces `SyntaxError` on the affected line or the line after. **After writing any `.py` file via `write_file`, always run `python3 -c "compile(open('script.py').read(), 'script.py', 'exec')"` before execution.** If the compile fails, use `patch` with the correct old/new strings to fix the escaped characters. Confirmed 2026-06-21: Praxis dispatch ingest script had `"}` instead of `})` on two return statements, causing `SyntaxError: closing parenthesis '}' does not match opening parenthesis '['`. See `references/session-20260621-dispatch-8.md`.
- **`python3 -c "..."` silently corrupts Python variable names** — When passing Python code via `python3 -c "..."` inside `terminal()`, the shell can strip characters from variable names in f-strings (e.g., `f'{relpath}: ...'` becomes `f'{elpath}: ...'` because the `r` gets consumed). Variables then raise `NameError`. **Never inline complex Python logic in `python3 -c` strings.** Always write to a `.py` file via `write_file()` first. This also applies to `terminal(python3 -c "...">` and `execute_code`-style inline strings. Confirmed 2026-06-21: three consecutive failures from this pattern.
**CRITICAL: Cross-pipeline state collision fix** — When the dispatcher triggers Forge + Mentor + Praxis in sequence, a separate Praxis cron job (or the dispatcher's own file operations) may update `ingest_state.json`'s `last_ingest_run` timestamp AFTER a Mentor journal is written but BEFORE the Praxis dispatch can scan for it. This causes the dispatch ingest to find 0 new journals because the state timestamp moved forward. Note: the Mentor heartbeat script does NOT write to Praxis's `ingest_state.json` — the collision comes from parallel Praxis cron runs or dispatcher file operations, not from Mentor. **Fix for dispatch-triggered Praxis: capture `last_ingest_run` from `ingest_state.json` at the very start of the dispatch (before any sibling skill pipelines run), and use that captured timestamp as the mtime comparison baseline.** The dispatch ingest template already reads `last_ingest_run` from the state file — in dispatch mode, ensure no intermediate Praxis cron has run between Mentor's journal write and the template's state read. When in doubt, use an even earlier timestamp (e.g., the `latest_mtime` from the dispatch details) as the baseline. Confirmed 6+ times (2026-06-21).
- **Mismatched quote types in string literals within `write_file` content** — When writing Python scripts via `write_file`, a dict literal with mismatched quote types (e.g., `les.get('lesson_id", '')` — single-quote start, double-quote end) produces `SyntaxError: unterminated string literal`. This is NOT an f-string issue — it's a plain string literal with mismatched delimiters. The error message points to the line *after* the actual mismatch, making it hard to spot. **Fix:** After writing any `.py` file via `write_file`, always run `python3 -c "compile(open('script.py').read(), 'script.py', 'exec')"` before execution. In the 2026-06-18 ingest, this pattern on line 446 blocked the entire run until manually patched.
- **`write_file` OVERWRITES JSONL files** — Read-then-rewrite pattern required for appends
- **Disk-full blocks ingest** — Check `df -h /` before running; abort if <1G free. Recovery: `apt-get clean`, remove stale scripts. See `references/gotchas-praxis.md` Disk and Environment section.
- **Cross-skill contamination risk** — Verify Praxis content doesn't pick up artifacts from Finch
- **Lesson suppression false-positive** — When checking if an existing lesson covers a new pattern, keyword matching against `lesson_text` is NOT sufficient. An `ocas-sands` lesson about "Google OAuth token missing" (planning phase) will incorrectly suppress a new `ocas-custodian` lesson about "Google OAuth revoked" (execution phase) because both contain "token". Match on `domain` + `failure_phase` + semantic scope, not keywords. Default to extracting the lesson when in doubt — dedup belongs in shift activation (merge-before-cap), not in lesson suppression.
- **Malformed lesson cleanup** — Legacy ingest runs may create lesson entries with empty `signal_type` (e.g., `les-00000228995663230219-0001`). These stubs pass the `confidence: high` check and get proposed as shifts with `signal_type: "unknown"` and `domain: "unknown"`, polluting the active shift list. **Fix:** Before proposing shifts, validate that each lesson has a non-empty `signal_type` and `failure_phase`. Filter out any lesson where `signal_type` is empty, `"unknown"`, `"?"`, or `None`. If malformed lessons already exist in `lessons.jsonl`, remove them and any shifts that reference them. See `references/session_20260614_ingest.md` for the cleanup procedure.
- **Shift proposal must validate lesson quality** — The shift proposal loop iterates over `all_lessons` and checks `confidence == 'high'` and `lid not in covered_lesson_ids`. But if lessons have empty `signal_type`, they produce shifts with `signal_type: "unknown"` that are semantically meaningless. **Always validate `signal_type` is non-empty and meaningful before proposing a shift.** Add a guard: `if not lesson.get("signal_type") or lesson["signal_type"] in ("unknown", "?", ""): skip`.
- **Evaluated journal dedup must use canonical IDs** — When building the `seen_ids` set from `journals_evaluated.jsonl`, normalize each `journal_id` to include the `.json` extension. Without this, `skill/2026-06-13/filename` (no extension) won't match `skill/2026-06-13/filename.json` (with extension), causing journals to be re-evaluated every cycle and inflating the unevaluated set with already-processed files.
- **Ingest date window too narrow — scan ALL dates, not just today/yesterday** — The ingest script computes `today` and `yesterday` from `datetime.now(timezone.utc)` and only scans those two date directories. But cron jobs (especially forge journal-scan) write files to future-dated directories. These files exist on disk but are invisible to the scan. In the 2026-06-15 ingest, 15 forge June 15 journals were missed by the main run and required a manual secondary pass. **Fix:** Walk ALL date directories on disk — remove the `date_dir in (today, yesterday)` filter from the filesystem scan. The `journals_evaluated.jsonl` dedup is the actual gatekeeper; the date filter is an unnecessary optimization that causes misses. Alternatively, use mtime-based comparison as a secondary check.

- **Production script only scans legacy journal path — DUAL-JOURNAL FIX applied 2026-06-21** — `praxis_common.py` had `JOURNALS_DIR = "/root/.hermes/commons/journals"` (legacy, 4,016 journals) and `find_all_journals()` only walked that directory. The indigo profile path (`/root/.hermes/profiles/indigo/commons/journals`, 8,335 journals) was completely unscanned. On 2026-06-21, 30+ journals from today were found unevaluated. **Fix:** Added `JOURNALS_DIRS` list to `praxis_common.py`; updated `find_all_journals()` to walk both directories with dedup. All 30 journals were routine no-signals (no events lost). See `references/session-20260621-dual-journal-fix.md`.
- **Mentor journals frequently malformed — skip gracefully** — ocas-mentor lightweight heartbeat journals often contain unresolved shell template variables (`$(python3 -c "...")`), placeholder values (`RUN_ID_PLACEHOLDER`), control characters, or are 0 bytes. These are expected byproducts of the mentor script's dual-failure fallback path (primary Python write fails, shell backup writes don't fully resolve templates). **Fix:** Ingest scripts should catch `json.JSONDecodeError` for mentor journals and log a `malformed: mentor` counter rather than crashing or counting as error. Do not treat malformed mentor journals as a Praxis data quality issue — the signal is in ocas-mentor's journal production, not in Praxis ingestion. This pattern has been observed consistently from 2026-06-06 through 2026-06-15 (9+ runs).
- **Two journal directory paths exist — use profile-aware path** — Journals are stored under BOTH `/root/.hermes/commons/journals/` (legacy/default profile) AND `/root/.hermes/profiles/indigo/commons/journals/` (indigo profile, 7,667 files). The indigo path contains the active, up-to-date journals. **Always use the profile-aware path**: `/root/.hermes/profiles/<profile>/commons/journals/`. The `JOURNALS_DIR` constant in `ingest-script-pattern.md` references the wrong path (`/root/.hermes/commons/journals`). Fix: `JOURNALS_DIR = "/root/.hermes/profiles/indigo/commons/journals"`.

- **`tier_1_fixes_applied` field can be `int` or `list`** — Custodian journals store `tier_1_fixes_applied` as either an integer count (e.g., `3`) or a list of fix descriptions. Calling `len()` on an int raises `TypeError`. **Fix:** `fixes = data.get("tier_1_fixes_applied", []); fixes_count = fixes if isinstance(fixes, int) else len(fixes) if isinstance(fixes, list) else 0`.

- **`new_errors` field can be `None`** — Custodian journals may have `new_errors: null`. Iterating over `None` raises `TypeError`. **Fix:** `data.get("new_errors", []) or []`.

- **Remove `ocas-lucid` from SKIP_DIRS** — SKIP_DIRS should only contain `ocas-praxis`. Lucid journals are routine degraded-mode scans that produce `no_signal` — scanning them is harmless and keeps the eval file complete. Having `ocas-lucid` in SKIP_DIRS causes every cycle to rediscover and skip them without marked evaluated. **This also applies to `ingest-script-pattern.md` line 61-62** — the reference script's `JOURNALS_DIR` must use the indigo profile path (`/root/.hermes/profiles/indigo/commons/journals`) and `SKIP_DIRS` must only contain `{"ocas-praxis"}`.

- **`journals_evaluated.jsonl` contains mixed formats — plain strings AND JSON dicts** — The eval file accumulates entries from different rebuild operations. Some entries are plain strings (from shell rebuild scripts), others are JSON dicts (from Python ingest scripts). After `json.loads()`, plain strings become `str` objects. Calling `.get("journal_id")` on a `str` raises `AttributeError`, crashing the ingest. **Fix:** Check `isinstance(e, dict)` before `.get()`. For plain string entries, use the string itself as the ID. See `references/session_20260625_ingest.md`.

- **Finch journal schema varies — `actionable`/`new_tasks_added` fields not always present** — Some finch scans use `findings`/`tasks_updated` instead. Use `data.get("new_tasks_added") or []` to coerce None to empty list before `len()`.
- **Signal extraction script pattern** — The production-proven approach for cron ingest: write a Python script to a `.py` file via `write_file()`, then execute via `terminal(command="python3 /path/to/script.py")`. Script should: (1) load evaluated IDs from `journals_evaluated.jsonl`, (2) walk ALL date directories, (3) extract signals per journal schema, (4) dedup by `(source_journal, signal_type)`, (5) append new events to `events.jsonl`, (6) append new journal IDs to `journals_evaluated.jsonl`, (7) write evidence + decision records. See `references/session_20260615_fullscan.md` for the full signal extraction function and the schemas it handles.
- **`events.jsonl` dual schema: `outcome_type` vs `signal_type`** — Legacy events (pre-2026-06-15) use `outcome_type` + `domain` + `source_journal` (no `signal_type`, no `skill` key). Current events use `signal_type` + `skill` + `source_journal`. When reading events for lesson extraction, direct `evt["signal_type"]` access crashes on legacy events. **Fix:** Define and use a `get_signal_type()` helper:
  ```python
  def get_signal_type(evt):
      return evt.get("signal_type") or evt.get("outcome_type") or "unknown"
  ```
  Use this helper for ALL event grouping, filtering, and lesson extraction. See `references/session_20260616_ingest_cron_praxis_v5.md` for the full context.
- **Write evidence BEFORE eval entries (crash safety)** — If the script crashes after writing eval entries but before evidence, the audit trail is incomplete: journals are marked evaluated but no evidence record exists. **Fix:** Write the evidence record immediately after signal extraction completes, BEFORE lesson extraction or eval entry appends. At minimum, write evidence before the first `append_jsonl(EVAL_FILE, ...)` call. See `references/session_20260616_ingest_cron_praxis_v5.md` for the crash scenario.
- **Non-dict journal format** — Some journals store data as a JSON array (`[...]`) instead of a JSON object (`{...}`). Calling `.get()` on a list raises `AttributeError`. **Fix:** After `json.load()`, check `if not isinstance(data, dict):` and skip with `action_taken: "skipped_non_dict"`.
- **Evidence variable initialization** — The `evidence` variable must be initialized BEFORE the conditional write (`evidence_id = "none"`). If the condition is false, downstream references to `evidence["evidence_id"]` raise `NameError`.
- **Eval ID format normalization** — The eval file stores IDs as `skill/YYYY-MM-DD/filename` (no `.json`), but `find`/`os.walk` produces `skill/YYYY-MM-DD/filename.json`. **Fix:** When building the evaluated set, add both the raw ID and the ID with `.json` appended.
- **Batch limiting for large unevaluated sets** — When thousands of journals are unevaluated, cap batch at ~500 per run. Prioritize active skills, sample non-active at 1/10th. The eval dedup ensures no journal is permanently missed.

## OKRs

See `references/okrs-praxis.md` for full OKR definitions and targets.

Key OKRs: `event_coverage` (≥0.90), `lesson_extraction_precision` (≥0.80), `shift_activation_accuracy` (≥0.75), `shift_decay_compliance` (≥0.95), `cap_efficiency` (≥0.80).

## Self-Update

See `references/self-update-praxis.md`.

## 2026-06-20 Ingest Findings

**New gotcha: Mentor-light `failure_keyword` false positives**
- Mentor-light heartbeat journals with `outcome: "success"` (or no `outcome` field) contain summary text like "0 errors detected" or "2 historical error records in evidence"
- Generic summary scanner picks up "error" and emits `failure_keyword` — a false positive
- Fix: skip ALL generic signal extraction for mentor-light journals with `outcome in ("success", "", None)` unless explicit failure indicators (`gap_detected: true` or `metrics.errors > 0`)
- 8 noise events produced in one run before fix was applied
- Patched in `ingest_cron_20260622.py` and gotcha section above

## Support File Map

| File | When to read |
|------|-------------|
| `references/data_model.md` | Before creating events, lessons, shifts; for schemas and storage layout |
| `references/okrs-praxis.md` | During OKR evaluation |
| `references/ingest-script-pattern.md` | Before writing ingest scripts; production-proven Python pattern for scan/dedup/extract/shift-activate workflow |
| `references/journal_ingestion.md` | Before scanning skill journals; signal extraction rules |
| `references/gotchas-praxis.md` | Before any Praxis operation; full gotcha catalog |
| `references/session_20260616_gotchas.md` | 2026-06-16 new gotchas: dual event schema, forge path canonicalization, evidence-before-eval crash safety |
| `references/gotcha_cross_skill_corroboration.md` | Before recording events; cross-skill dedup rules |
| `references/gotcha_custodian_findings_schema.md` | When ingesting custodian journals |
| `references/gotcha_unknown_signal_type.md` | During lesson extraction; noise filtering |
| `references/gotcha_escalation_fingerprint.md` | During escalation signal extraction |
| `references/gotcha_oauth_corruption.md` | When detecting auth-related events |
| `references/gotcha_evidence_field_schema.md` | When reading events.jsonl for pattern detection |
| `references/lesson_rules.md` | Before lesson extraction; confidence thresholds |
| `references/session_20260613_ingest_cron11.md` | 2026-06-13 ingest run: spot type case sensitivity, all_skipped_observation filter |
| `references/session_20260616_ingest_cron_praxis_v3.md` | 2026-06-16 cron ingest v3: batch pre-filter optimization, `cron_errors` new signal type |
| `references/session_20260616_ingest_cron_praxis_v5.md` | 2026-06-16 cron ingest v5: dual event schema (`outcome_type` vs `signal_type`), forge path canonicalization, evidence-before-eval crash safety |
| `references/session_20260616_ingest_cron.md` | 2026-06-16 cron ingest: mentor malformed journal pattern (9/16 unparseable), no_op + no_active_watches signals, no new lessons/shifts |
| `references/session_20260615_fullscan.md` | 2026-06-15 full scan: 476 journals, 197 events, shift merge 12→5, all gotchas validated |
| `references/session_20260616_ingest_cron_afternoon.md` | 2026-06-16 afternoon cron: forge `files_processed` list-vs-int bug, 14 journals, no new patterns |
| `references/session_20260616_ingest_cron_afternoon2.md` | 2026-06-16 afternoon cron: forge no-op variant expansion (NO_UNPROCESSED_FILES, no-op), future-dated journal handling |
| `references/session_20260616_ingest_cron.md` | 2026-06-16 cron ingest: 592 journals, 35 events, date-window fix validated at scale |
| `references/session_20260617_ingest.md` | 2026-06-17 full Praxis loop: journal ingest, lesson extraction, shift activation, debrief; cap enforcement via priority, noise filter at lesson creation, case-insensitive phase norm |
| `references/session_20260618_ingest_cron_m.md` | 2026-06-18 cron ingest: mentor-light "escalations" false positive, dual-path journal notes |
| `references/session_20260618_ingest_cron_d.md` | 2026-06-18 evening cron ingest: shift merge-before-cap fix, noise lesson filter, debrief template |
| `references/session_20260618_ingest_cron_d.md` | 2026-06-18 evening cron ingest: shift merge-before-cap fix, noise lesson filter, debrief template |
| `references/session_20260618_ingest_cron_o.md` | 2026-06-18 cron ingest: cap saturation at 12/12, new stale_counters + tier2_open signal types, lesson re-extraction inefficiency |
| `references/session_20260618_ingest_s.md` | 2026-06-18 cron ingest: mentor `evaluation_coverage` vs `coverage` schema variation, phase case normalization gap confirmed |
| `references/session_20260618_ingest.md` | 2026-06-18 cron ingest: non-dict journals, evidence init, eval ID format mismatch, batch limiting, old journal sampling |
| `references/session_20260618_ingest_cron_z.md` | 2026-06-18 cron ingest: mentor-light `low_coverage` measurement artifact, domain garbling fix, phase case normalization |
| `references/session_20260618_ingest.md` | 2026-06-18 cron ingest: `events.jsons` filename typo, cap saturation at 12/12, custodian tier2_open signals |
| `references/session_20260618_ingest_cron_aa.md` | 2026-06-18 cron ingest: noise filter gap in lesson extraction Pass 1 — mentor_light and coverage_gap lessons produced from event backlog despite noise filter at event recording stage |
| `references/session_20260619_ingest.md` | 2026-06-19 cron ingest: dual-directory scan, shift cap bug, lesson/shift cleanup |
| `references/session_20260619_ingest_cron_b.md` | 2026-06-19 second cron ingest: stale script cleanup incident (production scripts deleted from data root), mentor-light filtering validation |
| `references/session_20260620_ingest.md` | 2026-06-20 cron ingest: mentor-light `gap_detected` routine cadence finding, 7 journals, 1 event, cap at 12 |
| `references/session_20260620_ingest_b.md` | 2026-06-20 cron ingest B: finch_actionable_email pattern (12 events), 1 new lesson, cap at 12 blocks shift activation |
| `references/session-20260621_ingest.md` | 2026-06-21 cron ingest: forge `action` field as string bug, 5 events, cap at 12 |
| `references/mentor-light-noise-filters.md` | During journal ingest — mandatory filters for mentor-light false positives |
| `references/session-20260621-dispatch.md` | 2026-06-21 dispatch ingest: mtime-based discovery validation, 70 journals, 0 events |
| `references/session-20260621-dispatch-3.md` | 2026-06-21 dispatch ingest: 7 journals, 0 events, all pipelines clean |
| `references/session-20260621-dispatch-4.md` | 2026-06-21 dispatch ingest: cross-pipeline state collision, shell corruption bug, 1 journal, 0 events |
| `references/session-20260621-dispatch-6.md` | 2026-06-21 dispatch: all 3 pipelines clean, pre-run timestamp captured before Mentor |
| `references/session-20260621-dispatch-7.md` | 2026-06-21 dispatch: mtime-based discovery validation, 4 journals, 0 events |
| `references/session-20260621-dispatch-9.md` | 2026-06-21 dispatch: custodian action error mention false positive (NEW gotcha), all pipelines clean |
| `templates/dispatch_ingest_template.py` | Copy-and-adapt template for dispatch-triggered Praxis ingest — includes all noise filters, mtime-based discovery, mixed-format eval handling |
| `references/session_20260621_ingest_cron.md` | 2026-06-21 cron ingest: production script date-filter bug confirmed again, `find -newermt` timezone bug (NEW), custodian observation filter (NEW), 7 journals found by mtime, 0 events |
| `references/session-20260621-dispatch-8.md` | 2026-06-21 dispatch: write_file Python brace escaping bug, 0-event clean ingest, cross-pipeline timing validation |
| `references/session-20260622_ingest.md` | 2026-06-22 cron ingest: dual-path scan validation, 5 no-signal journals, all legacy paths already evaluated |
| `references/session-20260621-dual-journal-fix.md` | 2026-06-21: Production script dual-journal fix — praxis_common.py updated to scan both journal paths |
| `references/session_20260620_ingest.md` | 2026-06-20 cron ingest: mentor-light failure_keyword false positive, 8 noise events, fix applied |
| `references/session_20260625_ingest.md` | 2026-06-25 cron ingest: mixed-format eval file crash, finch schema variance, 16 journals, 0 events |
| `references/shift-cap-repair.md` | When active shifts exceed cap: repair procedure, curated rebuild, prevention patterns |
| `references/session-notes.md` | Historical production session findings (25+ sessions) |
| `references/storage-layout-praxis.md` | During initialization or path resolution |
| `references/self-update-praxis.md` | Before running praxis.update |
| `scripts/debrief_20260617.py` | When generating daily debrief; production-proven template |
| `scripts/praxis_debrief.py` | Manual debrief generation; use when running `praxis.debrief.generate` outside cron |