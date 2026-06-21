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

### 2026-06-14 Sessions

- `session_20260614_ingest.md` — **`break` vs `continue` bug**: forge/spot no-op handlers used `break` instead of `continue` in the per-journal loop, causing early exit that left 4 of 7 journals unprocessed and skipped lesson extraction. Fixed both handlers to `continue`. Also added `should_suppress_summary_signals` coverage for spot sweep journals with no summary. 7 journals total (5 forge + 2 spot), all no-signal. Active shifts stable at 4/12. System steady-state — 10+ consecutive runs with 0 new events.
- `session_20260614_ingest_cron16.md` — **Path bug**: `os.path.isdir(date_dir)` vs `os.path.isdir(date_path)` — checking directory name string instead of full path caused first run to find 0 journals. Fixed in v2. **Finch weekly dedup**: 8 of 10 corrections already covered by active shifts; only `directive/planning` and `correction/response` were new. Correct double-counting prevention. 3 journals scanned, 2 events, 2 lessons, 0 shifts (cap 12/12). All shifts age 0d — no decay concern.

### 2026-06-13 Sessions (continued)

- `session_20260613_ingest_cron8.md` — Finch dict-summary false positive pattern (cron_health "No new error data" matched as execution_error). 6 journals scanned, 0 new events.
- `session_20260613_ingest_cron9.md` — Forge `result: "no_op"` false positive pattern. 5 journals scanned, 0 new events.
- `session_20260613_ingest_cron10.md` — Finch dict-style `findings` schema observation (dict vs array). 5 journals scanned, all no-signal. Steady-state confirmed (8+ consecutive runs with 0 new events). Active shifts at 4/12.
- `session_20260613_ingest_cron11.md` — Spot type case sensitivity fix, all_skipped_observation filter.
- `session_20260613_ingest_cron12.md` — **Legacy lesson `signal_type` missing**: shift proposal crashed with `KeyError: 'signal_type'` on 3 domain-only lessons. Fixed with `.get()` guard. 6 journals scanned (first pass), all no-signal. Steady-state confirmed. Active shifts at 4/12.

### 2026-06-18 Sessions

- `session_20260618_ingest_cron_c.md` — Routine cron ingest: 2559 journals, 7 unevaluated (5 forge no-op + 2 praxis self-journal). 0 new events, 0 lessons, 0 shifts. Steady-state confirmed (15+ consecutive runs with 0 new signals). All gotcha filters validated. Active shifts at 9/12. Eval file at 2609 entries, growing ~7/cycle.

### 2026-06-16 Sessions

- `session_20260616_ingest.md` — Routine cron ingest: 524 journals on disk, 4 unevaluated (3 forge no-op + 1 finch no-signal). 0 new events, 0 lessons, 0 shifts. System steady-state at 12/12 cap with 43 proposed shifts queued. Evaluated journals at 5,941. Production ingest pattern (write_file + terminal) continues reliable. No gotchas encountered.

- `session_20260616_ingest_cron_praxis.md` — **Batch pre-filter optimization**: 10 unevaluated journals (4 forge no-ops batched, 6 individual). 2 new events: `cron_errors` (first occurrence — 4 failing cron jobs: custodian:deep, dispatch:email_check, ocas-weave, bones:research) and `calendar_conflict` (already covered). Cap at 12/12, no new shifts. Key learning: lightweight `is_forge_no_op()` pre-filter before full signal extraction avoids unnecessary processing of ~400+ routine forge scans. `cron_errors` tracked at 1/3 toward lesson threshold.

### 2026-06-15 Sessions

- `session_20260615_ingest_cron0210.md` — Routine ingest: 5 journals scanned (custodian + forge + spot), 1 event (custodian `execution_error`: bones:paper-trade transient upstream timeout), 0 lessons, 0 shifts. System steady-state at 12/12 cap, 250 events, 36 lessons, 32 proposed shifts. All shifts age 1d. Script had SyntaxError from escaped quotes in set literal inside list comp — caught by lint, fixed via patch. Already-known gotcha pattern. `journals_evaluated.jsonl` at 5,839 entries (above 5,000 compaction threshold — monitor).

### 2026-06-14 Sessions (continued)

- `session_20260614_ingest_1832.md` — **Ingest script arithmetic + syntax bugs**: (1) Compaction `removed = len(eval_entries) - compacted` (int-list=TypeError) → fix `len(eval_entries) - len(compacted)`. (2) `'final_shifts' in dir()` in f-string returns false positives → use `locals()` or pre-initialize. (3) Stray `else:` at wrong indent → SyntaxError. (4) Forge no-op `result: "no_files_found"` not in FORGE_NO_OP_RESULTS → added substring fallback. 5 journals scanned (4 forge + 1 spot), all no-signal. Cleaned 9 stale scripts. Added "Python Anti-Patterns" section to `ingest-script-pattern.md`. State: 247 events, 28 lessons, 12 active / 20 proposed shifts, all 0d old.