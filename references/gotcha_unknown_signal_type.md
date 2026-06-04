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
