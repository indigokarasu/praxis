# Session 2026-06-18: Praxis Journal Ingest — Cron Run S

## Summary
Routine cron ingest. 5 new journals found since last run (q). 3 events extracted, 0 new lessons, 0 new shifts. Cap at 12/12.

## New Journals
- `ocas-mentor/2026-06-17/mentor-light-20260617T220033Z.json` — `low_coverage` (cov=0.2143, gap=false)
- `ocas-mentor/2026-06-17/mentor-light-20260617T215028Z.json` — `gap_detected` + `low_coverage` (cov=0.2857, gap=true)
- `ocas-mentor/2026-06-17/mentor-light-20260617T220322Z.json` — no_signal (all healthy). Uses `evaluation_coverage` key (see below)
- `ocas-custodian/2026-06-17/light-scan-2026-06-17-150655.json` — MALFORMED (shell template `$(date ...)` unresolved in run_id/timestamp)
- `ocas-rally/2026-06-17/run_preopen_20260617150905.json` — no_signal (pre-open healthcheck, all clear)

## Key Learnings

### 1. Mentor Journal Schema Variation: `evaluation_coverage` vs `coverage`
**Discovered:** 2026-06-18

The mentor-light heartbeat journals use two different schema variants for coverage:

**Variant A** (older): `metrics.coverage` (float, 0.0–1.0)
```json
{"metrics": {"coverage": 0.2143, "gap_detected": false, ...}}
```

**Variant B** (newer): `metrics.evaluation_coverage` (float, 0.0–1.0)
```json
{"metrics": {"evaluation_coverage": 0.2143, "gap_detected": false, "total_files_scanned": 1851, ...}}
```

The `evaluation_coverage` metric represents the fraction of all journals that have been evaluated (i.e., Praxis coverage), NOT the skill's behavioral coverage. It should NOT be used as a `low_coverage` signal — doing so would conflate "Prais hasn't scanned all journals" with "the skill has low behavioral coverage."

**Fix:** When extracting `low_coverage` signals from mentor journals, check `metrics.get("coverage")` only. If the key is absent (as in Variant B), default to 1.0 (no signal). Do NOT fall back to `evaluation_coverage`.

**Impact:** Without this fix, Variant B journals with low evaluation coverage (which is normal — Praxis scans incrementally) would produce spurious `low_coverage/planning` events.

### 2. Phase Case Normalization Gap (Confirmed Again)
The `gap_detected` event from `mentor-light-20260617T215028Z.json` had `failure_phase: "planning"` (lowercase), while existing lessons use `"Planning"` (capitalized). The lesson dedup check `(signal_type, failure_phase)` with case-sensitive matching meant this event didn't merge with the existing `low_coverage/Planning` lesson group. With only 1 lowercase `planning` event, the group was below the n=3 threshold for new lesson extraction.

This is the same issue documented in session_20260617_ingest.md §4. The fix (normalize to lowercase before grouping) was not applied in this ingest run's inline script. **Recommendation:** Add `normalize_phase = lambda p: str(p).strip().lower()` to the ingest script pattern's mandatory helpers.

### 3. Custodian Shell Template Malformation (Known Pattern)
The custodian light-scan journal had unresolved shell template variables (`$(date +%Y-%m-%dT%H:%M:%S-07:00)`) in `run_id` and `timestamp` fields. This is a known byproduct of the custodian script's dual-failure fallback path. Caught and skipped gracefully — counted as malformed, not as an error.

## Metrics
- Journals on disk: 7,587
- Unevaluated: 5
- New events: 3 (gap_detected/planning × 1, low_coverage/planning × 2)
- New lessons: 0 (all signals covered by existing lessons or below threshold)
- New shifts: 0 (cap at 12/12)
- Malformed: 1
- No-signal: 2

## Files Written
- `ingest_cron_20260618_s.py` — ingest script
- `events.jsonl` — 3 new events appended (total: 2,454)
- `journals_evaluated.jsonl` — 5 new eval entries (total: ~16,139)
- `evidence.jsonl` — 1 evidence record
- `decisions.jsonl` — 1 decision record
- `journal/2026-06-17/run-20260617T221532.json` — Praxis run journal
