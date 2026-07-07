# Dispatch-Triggered Journal Ingest

When the cron dispatcher triggers Praxis as part of a multi-skill dispatch (Forge + Mentor + Praxis), Praxis owns the `journals_evaluated.jsonl` file and the `ingest_state.json` state.

## Trigger condition

The dispatcher calls Praxis when `has_work: true` and the dispatch details include `type: "new_journals"` with a list of `new_files` in `details`.

## Procedure

### 1. Check eval file for each `new_file` individually

```
EVAL="{agent_root}/commons/journals/ocas-praxis/journals_evaluated.jsonl"
for fname in "${new_files[@]}"; do
  count=$(grep -q "$fname" "$EVAL" 2>/dev/null && echo 1 || echo 0)
  echo "$fname → $count"
done
```

**Critical:** Never infer that because one journal from a cycle is present, another from the same cycle must be too. Always grep each individually. Confirmed 2026-06-26 dispatch #146.

### 2. Decision: Genuine new dispatch vs second-wave

| Signal | Second-wave | Genuine dispatch |
|--------|-------------|-----------------|
| ANY `new_file` NOT in eval? | No (all found) | Yes |
| Eval file last entry age | < 30 min | 60-120+ min |
| `last_ingest_run` in state | Recent | Stale / missing |

**If genuine new dispatch (any file not in eval):**
1. Add each missing `new_file` to `journals_evaluated.jsonl`:
   ```json
   {"journal": "skill/YYYY-MM-DD/filename.json", "filename": "skill/YYYY-MM-DD/filename.json", "source": "dispatch-new-journal-<dispatcher_ts>", "evaluated_at": "<ISO.now>", "status": "healthy", "events": 0}
   ```
2. **Cross-skill gap scan:** After processing all `new_files`, run a broader scan for ANY `.json` file in `{agent_root}/commons/journals/` with mtime after the PREVIOUS `last_ingest_run` that is NOT in the eval file. This catches journals from skills the dispatcher didn't detect (e.g., `ocas-rally` uses `jrn_YYYYMMDD_HHMMSS.json` naming, which the dispatcher's pattern may not match). Add any found gaps to the eval file.
3. **Post-dispatch cleanup scan:** AFTER writing all dispatch-output journals and third-wave mitigation entries to the eval file, do ONE MORE `find` for any `.json` file in the journals directory with mtime after `last_ingest_run` that is NOT in the eval file. The cron pipeline can write journals between our eval backfill and our third-wave mitigation. Add any found entries with source `post-dispatch-cleanup`. This prevents the next dispatch from detecting these as "new" and triggering an unnecessary genuine dispatch. Confirmed 2026-06-26 dispatch #155.
4. Advance state `last_ingest_run` → `datetime.now(utc).isoformat()`.
5. Third-wave mitigation: add own dispatch-output journals:
   ```json
   {"journal": "skill/YYYY-MM-DD/filename.json", "filename": "skill/YYYY-MM-DD/filename.json", "source": "dispatch-output-third-wave-mitigation", "evaluated_at": "<ISO.now>", "status": "healthy", "events": 0}
   ```
6. Advance `last_ingest_run` past own journal mtimes.

**Eval file path format:** ALWAYS use relative paths from `commons/journals/` (e.g., `ocas-forge/2026-06-26/forge-scan-TS.json`). NEVER use absolute paths (`/root/.hermes/profiles/indigo/commons/journals/...`). Absolute paths break the dispatcher's grep-based eval checks. Confirmed 2026-06-26 dispatch #154.

**If second-wave (all files already in eval):**
1. Third-wave mitigation only: add own dispatch-output journals.
2. Advance state.
3. Write no-op dispatch journal. Done.

### 3. State file format

`{agent_root}/commons/journals/ocas-praxis/ingest_state.json`:

```json
{
  "last_ingest_run": "2026-06-26T08:01:37+00:00",
  "last_ingest_source": "dispatch-20260626T080024Z",
  "journals_added": 234,
  "journals_evaluated": 234
}
```

**Pitfall: double timezone suffix.** `datetime.isoformat()` already includes `+00:00`. Never append it again. Use `ts.isoformat()` directly, never concatenate.

## Pitfalls

- **`grep -c` exits 1 on no-match** which breaks `if [ "$count" -eq 0 ]`. Use `grep -q` for boolean checks. Confirmed dispatch #142.
- **Missing `ingest_state.json`** is not fatal — write a fresh one. Don't error out.
- **`journals_evaluated.jsonl` path**: check both `{profile}/commons/journals/ocas-praxis/` and `/root/.hermes/commons/journals/ocas-praxis/`.
- **Heredoc trailing commands leak into file**: never put `echo "done"` or `cat file` after JSON in a heredoc. Use separate terminal calls.
- **Post-dispatch cron gap**: After writing third-wave mitigation entries, the cron pipeline may have written additional journals. Always do a final `find` + grep check AFTER writing all own-output journals. Add any late-arriving cron journals to eval with source `post-dispatch-cleanup`. Confirmed 2026-06-26 dispatch #155.
- **Path resolution pitfall in gap detection scripts**: When running `os.walk` + `os.path.getmtime` gap detection, the working directory of the Python script affects `os.path.relpath()` output. If the script is run via `python3 << 'PYEOF'` from a different CWD than expected, `os.path.relpath(fpath, "commons/journals")` may produce malformed paths like `../../../../../.hermes/profiles/indigo/commons/journals/...` instead of the correct `ocas-mentor/2026-06-26/file.json`. **Fix:** Always use absolute paths for the `journals_dir` base, and verify the first few gap results look correct (clean relative paths starting with `ocas-*`) before proceeding. Confirmed 2026-06-26 dispatch #167.
- **Cross-directory gap scan false positive (confirmed 2026-06-27T23:20Z):** When the gap backfill `find` scans BOTH the profile journals dir and the non-profile commons dir (`/root/.hermes/commons/journals/`), files from commons produce `../../../../commons/journals/...` paths via `os.path.relpath(fpath, profile_dir)`. These NEVER match eval entries (which use clean `ocas-mentor/...` relative paths), producing 100+ false-positive "missing" journals. **Fix:** Verify eval membership by **filename only** (`grep -qF "$basename" eval_file`), or skip the commons directory entirely — it's monitored by a different dispatcher instance.
- **Third-wave timestamp mismatch (confirmed 2026-06-27T19:40Z):** When the dispatch pipeline performs multiple steps — gap backfill, journal writing, third-wave mitigation — each step that calls `datetime.now()` independently gets a slightly different timestamp. The third-wave mitigation eval entries end up with different timestamps than the actual journal filenames → false "gap" detection on next dispatch. **Root cause:** Three separate `datetime.now()` calls across steps. **Fix:** Call `datetime.now(datetime.timezone.utc)` EXACTLY ONCE at the start of the dispatch pipeline. Store as `ts_file = now_ts.strftime("%Y%m%dT%H%M%SZ")` for filenames and `now_iso = now_ts.isoformat()` for JSON content. Pass these to every step. Never call `datetime.now()` again — seconds of drift produce mismatched eval entries.
- **Verification grep false negative from timestamp micro-differences:** When verifying that dispatch-output journals are in the eval file, the eval entry's timestamp may differ from the journal filename's timestamp by seconds. A `grep "forge-scan-20260626T092740Z"` check fails if the eval entry has `T092806Z`. **Fix:** Use partial timestamp matching: `grep "forge-scan-20260626T0927"` (drop last 2-3 chars). Or use `grep "dispatch-third-wave-mitigation"` to find all third-wave entries regardless of timestamp. This is a symptom of the above pitfall — the root-cause fix (single `datetime.now()` call) prevents it entirely.
