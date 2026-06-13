# Praxis — Session Notes Reference

## Session Ingestion Notes

### 2026-05-30 Sessions

- `session_20260530_review.md` — Schema variance discoveries, creation of scripts/praxis_review.py
- `session_20260530_ingest.md` — Lesson inference quality issues, unknown-domain noise, cross-skill lesson scoping
- `session_20260530_ingest3.md` — Sibling agent file contention, eval dedup (121 duplicates), observation event noise floor, shift activation dedup
- `session_20260530_ingest4.md` — Reinforcement text-match false positive (orphaned-cron shift incorrectly matched to custodian execution event)

### 2026-06-01 Sessions

- `session_20260601_ingest1.md` — Lesson suppression false-positive gap (keyword-only matching), stale root-level journal filtering, mentor coverage critically low (0.87%), dispatch security alert first-seed
- `session_20260601_ingest2.md` — `-not -path` glob pitfall confirmation (shell find returning 0 results), sibling agent file contention on ingest_run.py, 8 routine journals no-signal correctly skipped, OAuth token invalid_grant confirmed persistent (3rd day), cap at 12/12

### 2026-05-31 Sessions

- `session_20260531_ingest.md` — Canonical ID vs filesystem path confusion, 133 duplicate events removed, shift semantic flooding
- `session_20260531_ingest2.md` — Near-duplicate journal ID detection, bones:paper-trade Telegram delivery failure, HTTP 429 shift reinforcement
- `session_20260531_ingest3.md` — Legacy `id` vs `event_id` KeyError in lesson extraction, system state verification
- `session_20260531_ingest4.md` — Two-pass lesson extraction category-shifted pattern blind spot, escalation-seed event handling, system health signals
- `session_20260531_ingest5.md` — Unknown signal_type noise filter, praxis_ingest_run.py rewrite, shift semantic flooding
- `session_20260531_ingest6.md` — Escalation fingerprint enrichment gap, non-standard journal schema confirmation, runtime typo
- `session_20260531_ingest7.md` — Batch event ID collision, lesson source_event_ids referencing phantom events, shift activation at 12/12 cap
- `session_20260531_ingest9.md` — OAuth token corruption from ENOSPC, expired→reauth_needed state escalation
- `session_20260531_ingest10.md` — Steady-state zero-new-journals confirmation, scan-window race condition, lesson_id vs id schema variance
- `session_20260531_ingest11.md` — datetime import namespace collision, dual-call datetime.now() timestamp drift, taste scan auth failure
- `session_20260531_ingest12.md` — Ad-hoc scan script lesson re-extraction bug, domain normalization gap, shift activation for ocas-taste auth-failure
- `session_20260531_ingest13.md` — Stale eval entries referencing deleted journal files, HTTP 429 rate-limit pattern lesson, cross-domain auth_failure observation
- `session_20260531_ingest14.md` — Cross-skill corroboration detection (custodian + finch both detecting finch:weekly 401 within 2 minutes)
- `session_20260531_ingest15.md` — Same-skill temporal dedup, shift merge-before-cap enforcement gap

### 2026-06-05 Sessions

- `session_20260605_ingest1.md` — **Shift proposal dedup field mismatch**: ingest script checked only `lesson_id`/`lesson_ref` when building `lessons_with_shifts` set, but active shifts use `source_lesson_ids` (array) and `source_lesson` (string). Produced 133 spurious proposed shifts. Fixed by scanning all reference fields. Also confirmed post-write dedup by `source_journal` loses multi-signal events — should use `(source_journal, signal_type)` composite key. 5 journals scanned, 1 event, 0 lessons. Cap at 12/12.

### 2026-06-06 Sessions

- `session_20260606_ingest1.md` — **Finch dedup key fix**: post-write dedup by `source_journal` alone collapsed `cron_errors` and `auth_failure` signals from the same finch scan journal. Recovered 1 missed auth_failure event. Dedup key changed to `(source_journal, signal_type)`. Also recovered missed signals from `sources.*.error_breakdown` nested scan. 2 journals scanned, 2 events recovered. Cap at 12/12.
- `session_20260606_ingest2.md` — **Stale script accumulation**: 47 stale ingest/fix/scan scripts had accumulated in data directory over weeks of cron runs. Cleaned up. Added stale script cleanup gotcha to `gotchas-praxis.md`. 5 journals scanned, 0 signals (all clean routine ops). `journals_evaluated.jsonl` at 6,196 entries — compaction threshold (5,000) was exceeded but compaction didn't fire; needs investigation. Cap at 12/12, 214 proposed shifts.

### 2026-06-07 Sessions

- `session_20260607_ingest1.md` — **Lesson content dedup gap**: `lesson_id` includes random/timestamp component, so dedup by ID alone produced 49 "today" lessons for the same 16 `(signal_type, phase)` groups already in `lessons.jsonl`. Fixed by adding content-based dedup (group by signal_type+phase) in ingest-script-pattern.md §Lesson Content Dedup. 7 journals scanned, 1 new event, 9 lessons (before dedup). Cap at 12/12, 214 proposed shifts queued.

### 2026-06-04 Sessions

- `session_20260604_ingest1.md` — **Nested signal scan gap**: initial pass only checked top-level fields, missed 5 signals in `findings[].escalation_needed` (custodian) and `sources.*.error_breakdown` (finch). Targeted re-extraction recovered them. Fixed by adding nested scan steps 8+10 to ingest-script-pattern.md checklist. All 9 patterns already had lessons; 0 new lessons/shifts. Cap at 12/12.
- `session_20260604_ingest2.md` — Compaction step missing from pattern (fixed), os.path.exists() guard added, typo fixes. 8 journals scanned, 1 escalation signal. Cap at 12/12.
- `session_20260604_ingest3.md` — **Schema-ambiguous journal noise filter gap**: elephas journal with no top-level `status` field fell through noise filter, got incorrectly marked "event_recorded". Fixed with explicit `no_signal` fallback after signal loop. Also documented post-write dedup limitation (drops multiple signals from same journal). 2 journals scanned, 1 escalation event, 1 new lesson (escalation_planning). Cap at 12/12.

### 2026-06-07 Sessions (continued)

- `session_20260607_ingest2.md` — **os.path.join dot-strip bug**: ingest script used `os.path.join("/root", "hermes/commons/...")` which produced `/root/hermes/...` (missing the dot in `.hermes`). All JSONL writes silently went to the wrong path, then crashed on first `FileNotFoundError` read-back. Fixed by switching to absolute string literals. Script was re-run successfully with 2 unevaluated journals (both no-signal routine scans). 0 new events, 0 new lessons, 44 proposed shifts merged into active, 123 held at cap (12/12). Also: `write_file` cleanup removed `ingest_run.py` from data directory root (matched `ingest_*.py` pattern); fixed by writing to `scripts/` subdirectory instead. Function `get_lesson_id_from_proposal()` was called before definition in shift section — moved to top of script. All three path/function-ordering pitfalls documented in ingest-script-pattern.md §File Path Pitfall. Proposed pool at 173 entries (12 active at cap). `journals_evaluated.jsonl` at 6,250 entries — compaction at >5,000 was applied but entries remain near threshold due to new additions aging in. Steady-state run: all 18 event groups already have lessons.
