# Gotcha: Unknown Signal Type Filter

## Problem
Legacy events (pre-v3.0) store `signal_type` as `"?"` or omit the field entirely. When the pattern grouper reads `evt.get('signal_type', 'unknown')`, hundreds of legacy events cluster into `(domain, phase, "unknown")` groups that reach `min_pattern_count` and produce low-confidence lessons with no causal grounding.

## Production Impact
- ocas-custodian: 42 legacy events with `signal_type: "?"`
- ocas-elephas: 22 legacy events with `signal_type: "?"`
- ocas-mentor: 12 legacy events with `signal_type: "?"`
- These generated 3 useless low-confidence lessons per ingest cycle until the filter was added

## Fix
Skip events with `signal_type` in `("unknown", "?", None, "")` before building pattern groups for lesson extraction. This applies to both the ingest script AND manual lesson extraction.

## Where Applied
- `scripts/praxis_ingest_run.py` — pattern grouping loop
- `references/journal_ingestion.md` — lesson extraction rules
- `references/lesson_rules.md` — When NOT to extract section

## Variant: Post-v3.0 Schema Regression (2026-06-25)

Lessons extracted with `signal_type: '?'` from recent ingest runs (June 25-26) — these are NOT legacy events. The ingest script's lesson extraction pass is producing lessons without populating `signal_type`, causing them to fail the unknown-signon filter AND block the shift proposal pipeline entirely (27 lessons on June 25 alone, 0 shifts proposed).

**Detection:** `grep -c '"signal_type": "?"' lessons.jsonl` — if count grows between runs, the extraction pass is regressed.

**Fix:** In the lesson extraction Pass 2 (upgrade pass), if `signal_type` is missing or `'?'`, skip the lesson. Do NOT write lessons without a valid `signal_type` to `lessons.jsonl`.
