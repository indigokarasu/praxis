# Session 2026-06-20 Dispatch (Second Run — 17:45 UTC)

## Dispatch Summary
- 4 new journals detected: ocas-rally, ocas-dispatch, ocas-praxis, ocas-mentor
- All 3 pipelines executed successfully

## Pipeline 1 — Forge Journal Scan
- All 10 proposals already processed, 0 unprocessed
- No new VariantProposal or VariantDecision files

## Pipeline 2 — Mentor Light Heartbeat
- 1800 journals scanned (dual-path, 3-day window)
- 7 new files ingested
- `active_skills_30d` corrected: 13 → 14
- Script succeeded on all 3 writes (evidence, ingestion, journal)
- Corrected evidence record appended
- Commons sync: 2 evidence + 7 ingestion lines synced

## Pipeline 3 — Praxis Journal Ingest
- **Issue**: `ingest_state.json` is a JSON object (not JSONL), but the ingest script used `load_jsonl()` to read it
- This caused `last_ingest_run` to default to epoch, triggering a bulk re-scan of 4596 "unevaluated" journals
- Only 2 new events from old journals (ocas-sands auth_failure from April 14, ocas-finch disk_warning from June 1)
- No current issues detected

## New Gotcha: ingest_state.json Format

**The `ingest_state.json` file is a JSON object, NOT JSONL.**

The file is written with `json.dump(data, f, indent=2)` which produces multi-line JSON. Using `load_jsonl()` (which calls `json.loads()` per line) fails to parse it, causing `last_ingest_run` to default to epoch ("2026-06-01T00:00:00+00:00"). This triggers a bulk re-scan of ALL unevaluated journals.

**Fix**: Read `ingest_state.json` with `json.load(open(path))`, NOT line-by-line JSONL parsing.

**Verification**: After reading state, assert `last_ingest_run` is NOT epoch. If it is, use mtime-based detection only.

## Eval File Path Mismatch (Confirmed Again)
- Eval file stores IDs without date directory: `skill/filename.json`
- Filesystem scan produces IDs with date directory: `skill/YYYY-MM-DD/filename.json`
- This causes every journal to appear "unevaluated" on each scan
- Workaround: Use mtime-based comparison against `ingest_state.json:last_ingest_run`
