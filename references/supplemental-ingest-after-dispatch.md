# Supplemental Ingest After Dispatch

**Pattern:** Cron ingest runs on schedule, but dispatch-triggered journals can arrive in the same minute. The cron's `last_ingest_mtime` may be before the dispatch journal's mtime, leaving unevaluated journals.

**Confirmed:** 2026-06-25 dispatch #112 — `praxis-cron-20260625T171821Z.json` had mtime after `last_ingest_run` but wasn't in `journals_evaluated.jsonl`.

**Symptoms:**
- `last_ingest_run` timestamp < journal file mtime
- Journal not in `journals_evaluated.jsonl`
- `last_dispatch_run` < journal timestamp

**Fix:**
1. After dispatch journal processing, check for praxis journals newer than `last_ingest_run`
2. Ingest any missed journals into `journals_evaluated.jsonl`
3. Update `ingest_state.json` with new `last_ingest_mtime` and incremented `total_ingests`

**Why it matters:** Without supplemental ingest, Praxis misses events from dispatch-triggered runs, creating gaps in behavioral refinement data. The `last_ingest_events_added` counter becomes inaccurate.

**Detection command:**
```bash
find /root/.hermes/profiles/indigo/commons/journals/ocas-praxis/ \
  -name "*.json" \
  -newer /root/.hermes/profiles/indigo/commons/data/ocas-praxis/last_ingest_run
```

**Integration with dispatch workflow:** After writing dispatch-wave journal, always run the detection command above. If any files appear, ingest them before completing the dispatch.
