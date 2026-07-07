# Dispatch Quick Path (Praxis)

For the common case in a multi-skill dispatch (Forge + Mentor + Praxis):

## The 5-Line Pattern

When the dispatcher provides `details.new_files` and the Mentor heartbeat just ran:

```bash
# 1. Check if dispatcher's new_files are already evaluated (second-wave detection)
for jid in "${new_files[@]}"; do
    if grep -q "$jid" journals_evaluated.jsonl; then
        echo "  $jid: already evaluated (skip)"
    fi
done

# If ALL new_files are already evaluated → fast no-op:
#    - Update last_ingest_run timestamp
#    - Write dispatch journal (no_op)
#    - Exit. Do NOT re-add to eval file.
python3 -c "import json; f='ingest_state.json'; s=json.load(open(f)); s['last_ingest_run']=''"$NOW"'"; json.dump(s,open(f,'w'),indent=2)"

# 2. For journals NOT in eval file: evaluate (load JSON, extract signals, apply noise filters)
#    For mentor-light with outcome=success: no_signal, skip
#    For forge scan with result starting with "no_op"/"clean": no_signal, skip

# 3. Append to journals_evaluated.jsonl
echo '{"journal_id":"'"$jid"'","evaluated_at":"'"$NOW"'","action_taken":"evaluated"}' >> journals_evaluated.jsonl

# 4. Third-wave mitigation: add dispatch-output journals (forge-scan, mentor-light)
#    Check eval file for the forge-scan journal from THIS dispatch wave.
#    If missing, add with action_taken="third_wave_mitigation"
for jid in forge-scan-"$TODAY"T*.json mentor-light-"$TODAY"T*.json; do
    if ! grep -q "$jid" journals_evaluated.jsonl; then
        echo '{"journal_id":"'"$jid"'","evaluated_at":"'"$NOW"'","action_taken":"third_wave_mitigation"}' >> journals_evaluated.jsonl
    fi
done
```

## Cron-Output Journals in Dispatch (confirmed 2026-06-26 dispatch #141)

When the dispatcher's `new_files` includes journals from **cron pipelines** (not dispatch pipelines), those journals will NOT be in `journals_evaluated.jsonl`. This is distinct from second-wave (dispatch detecting its own prior output).

**Detection:** Journal source matches a dispatched skill, timestamp is BEFORE dispatch `detected_at`, and `grep -c "<journal_id>" journals_evaluated.jsonl` returns 0.

**Resolution:** Add the cron journal to eval file as `action_taken: "cron_output_skip"`, then proceed with normal third-wave mitigation.

**Example (2026-06-26):**
- Dispatcher detected `ocas-praxis/2026-06-26/praxis-cron-20260626T060522Z.json` as "new"
- This was written by Praxis cron at 06:05Z, not by a prior dispatch
- Not in eval file → added as `cron_output_skip`

## Partial Cycle Gap Between Sibling Pipelines (confirmed 2026-06-26 dispatch #146)

A sub-variant of the cron-output gap where one cron pipeline's journal is in the eval file but another cron pipeline's journal from the SAME cycle is absent.

**Example:** `mentor-light-20260626T073205Z` present in eval, but `praxis-cron-20260626T073343Z` (written 90 seconds later) missing.

**Root cause:** Two cron pipelines (mentor and praxis) write independently. Their journals can straddle an ingest boundary — one gets picked up, the other doesn't. The `last_ingest_run` timestamp reflects the last ingest OPERATION, not the last journal CREATION.

**Fix:** Check EVERY `new_file` individually against the eval file with `grep -q "filename" eval_file`. Never infer that "if mentor-light from cycle X is evaluated, praxis-cron from cycle X must be too." Sibling pipelines have independent ingest timing.

**Universal rule (all gap variants):** During second-wave or cron-output handling, `grep -q "filename" journals_evaluated.jsonl` for EACH `new_file` individually. Never assume coverage based on `last_ingest_run` timestamp or sibling journal status.

## Second-Wave / Third-Wave Detection (confirmed 2026-06-25, 40+ occurrences)

When the dispatcher fires multiple waves in rapid succession (same day), journals from prior waves are typically **already in `journals_evaluated.jsonl`** — ingested by sibling Praxis heartbeats between waves.

**Before running mtime-based discovery or evaluating any journal:** always grep `journals_evaluated.jsonl` for each dispatcher `new_file` filename. If all are present → **fast no-op** (update state, write journal, exit). Do NOT re-add or re-evaluate.

**Steady-state expectation:** In a healthy system running multiple daily dispatch waves, the fast-no-op path is the **default outcome** for Praxis. Finding all dispatcher `new_files` already evaluated is not an error or stale state — it indicates the pipeline is running correctly with concurrent heartbeats processing journals between waves. Confirmed 2026-06-25 dispatch #134: 0 gap backfill, eval file 38,953 entries — fully caught up (confirmation #46+).

**Taste signals boundary:** Taste dispatch journals contain consumption signals (DoorDash, Instacart, etc.) that are self-contained in the Taste pipeline. Praxis does NOT process Taste signals — Praxis handles behavioral refinement from mentor/custodian/finch journals only. When a Taste dispatch journal appears in `new_files`, mark it as `action_taken: "taste_signal_skip"` in the eval file.

## When to Use Quick Path vs Full Ingest

| Condition | Path |
|---|---|
| Dispatcher provides `new_files`, all already in `journals_evaluated.jsonl` | **Fast no-op** (grep check → update state → write journal → exit) |
| Dispatcher provides `new_files`, all are routine no-signal journals (not in eval) | **Quick path** (5 lines) |
| `new_files` contains cron-pipeline journals (not in eval) | **Quick path** — add as `cron_output_skip`, then evaluate remaining |
| No `new_files` list, need mtime-based discovery | Use `dispatch_ingest_template.py` with CAPTURED_TS |
| `new_files` contains unknown journal types (custodian, finch, spot) | Full template (noise filters needed) |
| `new_files` contains journals with `outcome: "error"` or `escalation_needed: true` | Full template (signal extraction needed) |
| `new_files` contains Taste dispatch journals | Mark as `taste_signal_skip`, no Praxis processing needed |

## Key Insight

Most dispatch Praxis ingests are: "check eval file → all already evaluated → fast no-op." The second-wave pattern is the **expected default** when multiple dispatch waves fire in the same day. The quick path handles this without 150 lines of edge-case filters. Only invoke the full template when journals contain genuine signals (errors, escalations, anomalies).

## Path Typo Phantom Files (confirmed 2026-06-25 dispatch #107)

When manually appending to `journals_evaluated.jsonl` via `python3 -c "..."` in `terminal()`, a typo in the filename (e.g., `journals_evaligated.jsonl` instead of `journals_evaluated.jsonl`) creates a parallel file that:
1. Silently fails to register the evaluation
2. Gets detected as "new" by the next dispatcher wave
3. Causes spurious re-processing

**Detection:** After every eval file write, verify the entry landed in the correct file:
```bash
grep -c "pattern" /correct/path/journals_evaluated.jsonl  # Should be > 0
ls /path/to/ | grep -i eval  # Check for duplicate filenames
```

**Fix:** Append correct entry to the real file, delete the typo file immediately.

## Commons Eval File Sync Drift (confirmed 2026-06-25 dispatch #134)

When using `comm -13 <(sort commons) <(sort profile) >> commons` to sync eval files, commons can accumulate MORE entries than profile over many dispatches. This happens because `comm -13` only appends — it never removes. If profile was ever behind commons (e.g., after a `cp` reset), the "missing" lines get re-appended.

**Detection:** After major ingests, compare line counts:
```bash
wc -l /root/.hermes/commons/data/ocas-praxis/journals_evaluated.jsonl
wc -l /root/.hermes/profiles/indigo/commons/data/ocas-praxis/journals_evaluated.jsonl
```

**Fix:** If commons > profile, force-sync profile→commons:
```bash
cp /root/.hermes/profiles/indigo/commons/data/ocas-praxis/journals_evaluated.jsonl \
   /root/.hermes/commons/data/ocas-praxis/journals_evaluated.jsonl
```

Profile is authoritative after a complete dispatch ingest. Do NOT rely solely on `comm -13` for eval file sync.
