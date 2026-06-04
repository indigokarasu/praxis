# Praxis — Full Gotcha Catalog

## Shift Management

- **Active shift cap is hard** — The 12-shift cap is enforced on every activation. When at cap, new shifts must merge with existing ones, replace a weaker shift, or be rejected.
- **Shift activation dedup and merge before cap enforcement** — Before proposing a new shift, check for semantically overlapping active shifts. Merge-first, check cap-second.
- **Shift decay without reinforcement** — Active shifts not reinforced in 14+ days auto-expire. The noon `praxis:decay_check` cron runs this daily.
- **Shift decay check must handle missing `last_reinforced_at`** — Legacy shifts (created before v3.0.0) may lack `last_reinforced_at` and `reinforcement_count` fields. When checking decay, fall back to `created_at` if `last_reinforced_at` is absent. In one decay check, only 2 of 9 shifts were visible because 7 legacy shifts had no `last_reinforced_at`. Use: `lra = s.get('last_reinforced_at') or s.get('created_at')` and treat missing `reinforcement_count` as 0.
- **Shift semantic dedup before activation** — Compare new shift's `shift_text` against all active shifts. If an active shift already addresses the same intervention, reinforce it instead of creating a variant.
- **Shift reinforcement must be domain/phase-scoped** — Only reinforce shifts whose domain/phase actually matches the new events. Don't over-reinforce unrelated shifts.
- **Reinforcement text-matching precision** — Require BOTH domain overlap AND semantic relation. Keyword-only false positives pollute reinforcement counts.

## Lesson Extraction

- **Lessons require causal grounding** — `[LESSON] What: <pattern>. Why: <cause>. When: <conditions>`. Lessons without "why" get `confidence: low`.
- **Failure-phase tagging is mandatory** — Events from journal ingestion must include `failure_phase`. Untagged events can't participate in phase-aligned extraction.
- **Skip unknown/null domain lessons** — Do not extract lessons where domain is `unknown`, `None`, `null`, or empty.
- **Pattern detection must not rely solely on `context_summary` keywords** — Legacy events (pre-v3.0) often have empty or null `context_summary` fields. When grouping events for pattern detection, use `outcome_type == 'failure'` + `domain` as the primary matching signal, with `context_summary` keyword matching as secondary enrichment. In one ingest run, 6 of 9 domain events had empty context_summary, causing a real failure pattern (N=2+) to be missed on first pass. Always filter by `e.get('outcome_type') == 'failure' and e.get('domain') == target_domain` first, then enrich with keyword scanning on non-empty summaries.
- **Re-read events.jsonl after writing new events before running lesson extraction** — After appending new events to events.jsonl, re-read the file before the lesson extraction pass. Events written in the same run must be visible to the pattern detector. In this session, the first extraction pass found 0 lessons because a newly-written event wasn't visible until a second pass re-read the file.
- **Cross-skill phase lessons are too generic** — Patterns spanning 20+ skills produce non-actionable shifts. Record as observations only.
- **Lesson inference quality** — Gate `infer_cause` on `(domain is real skill name) AND (failure_phase in {planning, execution, response})`. Return `None` otherwise.
- **Lesson id field variance** — Production uses `lesson_id`; schema specifies `id`. Use `les.get('lesson_id', les.get('id', ''))`.
- **Ad-hoc scan scripts must deduplicate lesson keys** — Load existing lessons first, build key set, check before extracting.
- **Reject empty stub lessons at extraction time** — Lessons with empty `lesson_text` or missing `what`/`why`/`when` fields are not "low confidence" — they are incomplete extractions that should be rejected immediately. Do not write them to `lessons.jsonl` where they accumulate as noise. In one ingest run, 3 empty stubs from prior sessions had to be manually rejected. If Pass 1 produces a stub that Pass 2 cannot ground (no events with meaningful summaries), reject it on the spot.

## Event Recording

- **Do not record observation events for signal-free journals** — Only record events when there is a real signal (not routine no-op journals).
- **Cross-skill corroboration** — When two skills detect the same fingerprint within 30 min, create one corroboration event, not two.
- **Same-skill temporal dedup** — Check events.jsonl for same fingerprint within 6 hours before recording.
- **Batch event ID collision** — Use `time.monotonic_ns()` or monotonically incrementing counter, not `datetime.now()` in loops.
- **Event/lesson/shift ID format mixing** — Always use timestamp-based IDs and verify uniqueness regardless of format.
- **Domain normalization** — Use canonical skill names, not raw filesystem directory names.

## Journal Ingestion

- **`journals_evaluated.jsonl` mandatory pre-scan dedup** — Deduplicate by `journal_id` before EVERY filesystem scan.
- **Near-duplicate journal IDs evade exact-match dedup** — Run normalization pass if line count differs from unique-ID count.
- **Unknown signal_type filter** — Skip events with `signal_type` in `("unknown", "?", None, "")` before pattern grouping.
- **Journal directory scan pattern** — Use `find -path` covering today and previous day, diff against `journals_evaluated.jsonl`.
- **Non-standard journal paths** — Some skills write outside canonical pattern. Walk ALL subdirectories and filter at evaluate time.
- **Stale eval entries** — Filter unevaluated list through `os.path.exists()` before processing.
- **Signal extraction — validate structure first** — Check field existence before keyword matching. Treat summary-only hits as `confidence: low`.
- **Finch escalations array** — Finch journals use `"escalations": [{"type": "new_item", "id": ..., "title": ..., "description": ...}]` instead of top-level `escalation_needed: true`. Always check for `escalations` arrays in addition to the boolean. Without this, finch scan escalations (e.g., workspace-mcp-down) are silently dropped and only captured indirectly via weaker keyword paths.
- **Dict-format summaries with success status = noise filter required** — Many custodian/finch scan journals store `summary` as a dict containing failure counts/data for *other* systems (e.g., `"error_jobs": 7, "error_breakdown": {"transient_429": [...]}`). When `status` is `"ok"`/`"success"`/`"completed"` OR `type` is `"observation"`, the scan itself succeeded — do NOT extract failure_keyword signals from its data fields. Only keyword-match dict summaries when the top-level status/type indicates an actual failure. Prevents false-positive events from successful scan reports.
- **`find -not -path` glob pitfall**: Shell `find` with `-not -path "*/\.*"` may return 0 results even when matching files exist, due to shell glob interpretation of the `\*` pattern. The `*` in `*/\.*` can be expanded by the shell before `find` sees it. Either single-quote the pattern or, preferably, use Python `pathlib`/`os.walk()` for filesystem scanning. The skill already recommends Python scripts for journal scanning — this gotcha explains **why** the shell approach is unreliable.
- **`escalation_flagged` array noise in custodian journals**: Custodian light scan journals store internal tracking state as `"escalation_flagged": ["issue_id_1", "issue_id_2", ...]` arrays. These are NOT new escalations — they are references to previously-known issues being tracked. When signal-extraction code keyword-scans the journal JSON and hits the word "escalation" inside this array key, it produces false-positive `escalation/planning` events. In one ingest run, all 5 `escalation/planning` events were this noise. **Fix**: When scanning custodian journals, skip `escalation_flagged` arrays — only treat top-level `escalation_needed: true` or `escalations` arrays with `type: "new_item"` as real escalation signals. Do not keyword-match against JSON key names.
- **"Correction keywords in summary" false positives**: Some journal summaries contain the word "correct" or "fixed" in contexts that are NOT behavioral corrections (e.g., "correctly handled", "fixed-width format", "correction to prior estimate"). When the only signal is a keyword match on a summary string and the `execution_result.status` is `ok`, do NOT record a correction event. Require either `status: "partial"/"error"` OR an explicit `fixes_applied > 0` OR `actions_taken[].outcome` indicating a fix was applied. In one ingest run, 6 "correction" events (dispatch + elephas) were all keyword artifacts from routine nominal journals.

## Cron and Execution Context

- **`execute_code` is blocked in cron context** — Use `terminal()` with heredoc for JSONL processing.
- **`write_file` OVERWRITES JSONL files** — Read-then-rewrite pattern required. Never append via `write_file`.
- **Shell-embedded Python fails in cron** — Write `.py` file first with `write_file`, then run via `terminal()`.
- **Path traversal bug** — Use absolute paths, never `../` relative traversal from inside data directories.
- **F-string backslash escaping in write_file** — Use `.format()` instead of f-strings, or write script to file first.
- **Sibling agent file contention** — Use unique temp filenames per run.
- **Zero new journals is healthy** — `len(unevaluated) == 0` means the 30-min cron is keeping up.

## Schema Variance

- **`evidence` field may be dict or list** — Check `isinstance(ev, dict)` before accessing fields.
- **Legacy events use `id` instead of `event_id`** — Use `evt.get('event_id', evt.get('id', ''))`.
- **`summary` field can be dict or string** — Check `isinstance()` before accessing sub-fields.
- **`outcome`/`status` can be str OR dict** — Check `isinstance(outcome, str)` before comparing.
- **Config may be incomplete** — Merge defaults on init, don't assume full schema.
- **Shifts use mixed ID and field names** — Some shifts use `shift_id`, others use `id`. Some use `failure_phase`, others use `phase`. Some use `source_lesson`, others use `source_lesson_ids`. Always use `s.get('shift_id') or s.get('id', '?')` and `s.get('failure_phase') or s.get('phase', 'execution')` before any comparison. In one ingest run, a `KeyError` on `shift_id` crashed the merge-overlap check because one shift used `id` as its key.
- **Lessons use mixed ID field names** — Same pattern as events: use `les.get('lesson_id', les.get('id', ''))` before any lesson ID comparison or lookup.

## Lesson Extraction Workflow

- **Two-pass lesson extraction is mandatory** — The initial extraction pass groups events by signal_type+phase and produces lesson stubs. A second "upgrade" pass must then add full causal grounding (what/why/when) to each lesson. Without the upgrade pass, all lessons are `confidence: low` and cannot produce shifts. Do not skip the upgrade pass. In one ingest run, the first pass produced 7 low-confidence lessons; the upgrade pass converted all 7 to high confidence with proper causal grounding.
- **Empty `skills_affected` produces empty domain** — When extracting lessons, if `skills_affected` is empty or missing, the resulting shift will have `domain: ""`. Empty domains cause the merge-overlap check to either miss real overlaps or falsely match on empty strings. Always default to the lesson's `skill` field or the source journal's skill directory name when `skills_affected` is empty.

## Cross-Skill Contamination

- **Core loop is distinct from Finch** — Verify no Finch artifacts in Praxis content during rewrites.
- **Journal ingestion scans ALL skills** — Track consumed IDs to avoid reprocessing.

## Misc

- **Review script exists** — `scripts/praxis_review.py`. Keep sync with SKILL.md.
- **Proposed shift activation delay** — Activate promptly with solid evidence. Don't let shifts linger.
- **`comm` sort order pitfall** — Pipe both inputs through `sort` before `comm -23`.
- **`find -newer` scan misses journals** — Use date-based directory scanning instead.
