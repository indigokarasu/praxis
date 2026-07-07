# Cron Ingest Session — 2026-06-27 15:32Z

## Summary

Routine cron ingest. Production script executed, post-processing revealed need for two-pass lesson cleanup (new finding).

## Results

- **Journals on disk:** 12,341
- **New journals processed:** 3 (all routine no-signals)
- **Events recorded:** 0
- **Lessons extracted (raw):** 27
- **Pass 1 cleanup (low-conf):** removed 15, kept 59
- **Pass 2 cleanup (malformed/noise):** removed 43, kept 16
- **Active shifts:** 9/12
- **Gap backfill:** 0 (clean)
- **Decay-risk shifts:** 7 (all at 9d, 0 reinforcements)

## Key Finding: Two-Pass Lesson Cleanup Required

The existing single-pass cleanup (remove `confidence: low`) was insufficient. After Pass 1, 43 high-confidence lessons remained that were still noise:

- **Empty `signal_type`:** Lessons like `|ocas-custodian/execution`, `|system/execution`, `|ocas-sands/execution` — produced by legacy events that lack a `skill` field. The domain was extracted but signal_type was empty.
- **Noise signal types at high confidence:** `low_coverage` (n=13), `gap_detected` (n=3-6), `correction` (n=4-39), `anomaly` (n=2-662), `no_signal` (n=662), `success` (n=6) — all from historical accumulation meeting the ≥2 threshold.

**Root cause:** The production script's lesson extraction groups ALL 3,430 events by `(signal_type, failure_phase)`. Events with empty `signal_type` group together (n=12+), producing a "lesson" with an empty signal type. Noise signal types accumulate 10-662 events historically, easily passing the threshold.

**Fix applied:** Added Step 5b to `cron-execution-checklist.md` — a second cleanup pass that removes lessons where `signal_type` is empty or in the `NOISE_SIGNAL_TYPES` set. Updated `recurring-noise-lesson-cleanup.md` to document the two-pass pattern.

## Decay Risk

7 shifts at 9 days with 0 reinforcements:
- `execution_error|ocas-custodian` age=9d
- `escalation|ocas-custodian` age=9d
- `correction|ocas-custodian` age=9d
- `failure_keyword|ocas-custodian` age=9d
- `failure|ocas-spot` age=9d
- `platform_failure|ocas-spot` age=9d
- `anomaly|ocas-mentor` age=9d

Only `tier2_open|ocas-custodian` (reinf=3) and `gap_detected|ocas-mentor` (reinf=1) have been reinforced. Mass expiry at 14d if not reinforced.

## Production Script Bugs Confirmed (again)

- **Bug 2 (lesson scoping):** Full 3,430-event history reprocessed → 27 lessons (58 total noise/malformed across both cleanup passes)
- **Bug 3 (state update):** Script does not update `ingest_state.json` — manual update required
