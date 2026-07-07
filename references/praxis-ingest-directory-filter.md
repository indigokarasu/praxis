# Praxis Ingest Script Directory Filter

## Issue
The `praxis_ingest_run.py` script only processes journals located under the `ocas-praxis/` directory (its own self-referential journals). It does NOT evaluate journals from:
- `ocas-mentor/`
- `ocas-dispatch/`
- `ocas-forge/`
- Any other non-Praxis skill

## Root Cause
The script uses a directory-based filter when scanning for journals. It looks at journal file paths and only picks up those under its own skill directory (`ocas-praxis/`). This means cross-skill journals referenced by the dispatcher are silently ignored.

## Impact
When the dispatcher triggers a multi-skill dispatch and lists journals from non-Praxis skills in `new_files`, the Praxis ingest step appears to succeed but actually evaluates 0 journals. The unevaluated journals remain unmarked in `journals_evaluated.jsonl`, causing them to be re-detected as "new" by the next dispatcher wave.

## Workaround
After running the ingest script, the dispatch caller must manually:
1. Check `journals_evaluated.jsonl` for each non-Praxis journal listed in `new_files`
2. If missing, add an entry:
   ```json
   {"journal_id": "ocas-mentor/2026-06-24/file.json", "evaluated_at": "<ISO timestamp>", "action_taken": "cross_skill_mitigation", "note": "Praxis directory filter excludes non-Praxis journals. Manually added by dispatch caller."}
   ```
3. Update `ingest_state.json:last_ingest_run` to a timestamp past the journals' mtime

## Confirmed
- Dispatch #55 (2026-06-24): Mentor-light + dispatch journal both needed manual addition
- Dispatch #67 first wave (2026-06-25 03:50Z): 3 journals from ocas-dispatch/ and ocas-mentor/ added manually
- Dispatch #67 second wave (2026-06-25 04:12Z): 6 journals from ocas-mentor/ (×2), ocas-praxis/, ocas-custodian/, ocas-forge/, ocas-dispatch/ added manually. Confirms the pattern scales to larger journal counts.
- Dispatch #78 (2026-06-25 06:01Z): Dispatcher `new_files` already evaluated by concurrent heartbeat (fast no-op). Only own output journals (forge-scan + mentor-light) needed third-wave mitigation. Confirms "grep eval file before mtime discovery" shortcut.
- This is a recurring pattern on every multi-skill dispatch containing non-Praxis journals

## See Also
- `session-20260624-dispatch-55.md` in `ocas-dispatch` skill — worked example
- `session-20260625-dispatch-067-praxis.md` in `ocas-praxis` skill — cross-skill mitigation confirmation #6
- `session-20260625-dispatch-078-praxis.md` in `ocas-praxis` skill — dispatcher new_files already-evaluated pattern confirmation #7
- `cron-dispatch-ingest-pattern.md` in `ocas-dispatch` skill — dispatch workflow pitfall entry
