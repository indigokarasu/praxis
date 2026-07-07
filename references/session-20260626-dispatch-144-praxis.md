# Session 2026-06-26 Dispatch #144 — Dispatch-Output Eval Gap (Second-Wave)

**Trigger:** Cron dispatcher at 07:07Z detected 5 new journal files + 1 email thread.

## Signals

### 1. Eval file gap on dispatch-output journals

**Scenario:**
- Dispatcher detected `forge-scan-20260626T070643Z.json` and `praxis-dispatch-20260626T070643Z.json` as "new"
- `last_ingest_run` in state was `2026-06-26T07:06:55+00:00` — AFTER the journal file timestamps (07:06:43)
- But grep revealed these 2 journals were NOT in `journals_evaluated.jsonl`
- `mentor-light-20260626T070339Z.json` WAS in the eval file (different sibling from same wave survived)

**Root cause:** Prior dispatch wave's Praxis ingest evaluated mentor-light but not forge-scan/praxis-dispatch before completing. `last_ingest_run advancement happens at END of ingest, not per-journal.

**Resolution:**
1. Added 2 missing dispatch-output journals to eval file
2. Wrote 3 no-op journals (current wave) and added them to eval file
3. Advanced `last_ingest_run` to `2026-06-26T07:11:07+00:00`
4. Eval file count: 39,527

### 2. Email triage (GitGuardian)

- **Thread:** `19f02babc12a3dae` — "indigokarasu/indigo - 5 internal incidents detected"
- **Sender:** GitGuardian Team (automated)
- **Intent:** Informational security alert — JWT + 4 high-entropy secrets in commit 49c0132
- **Decision:** No action required (internal repo, automated notification)

## Consolidated Eval Gap Pattern Reference

All 3 known sub-variants confirmed as of dispatch #144:

| Gap Type | Missing Journals | Source | First Seen |
|----------|-----------------|--------|------------|
| Cron journal gap | `praxis-cron-*`, `mentor-light-*` (cron pipeline output) | Cron pipeline between dispatch waves | #141, #143 |
| Dispatch-output gap | `forge-scan-*`, `praxis-dispatch-*` (dispatch pipeline output) | Prior dispatch wave's own output | #144 |
| Partial cycle gap | 1+ journals from a cron cycle absent, others present | Incomplete cron ingest | #143 |

**Universal rule:** During second-wave handling, `grep -q "filename" eval_file` EACH `new_file` individually. Never infer coverage from:
- `last_ingest_run` timestamp (timestamp-after-file doesn't guarantee eval)
- Sibling journal presence (one journal being in eval doesn't mean siblings are)
- Wave membership (same-wave journals can have different eval status)

## Results

- **Forge:** no_op, 0 unprocessed proposals
- **Mentor:** no_op, 0 new signals
- **Praxis:** 2 journals gap-backfilled, 3 no-op written, 0 events
- **Email:** 1 thread reviewed, action=none (GitGuardian informational)
- **Third-wave mitigation:** Applied (3 journals added to eval file)
- **No phantom files detected**
