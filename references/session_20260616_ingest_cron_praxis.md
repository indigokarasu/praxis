# 2026-06-16 Praxis Journal Ingest (Cron Run — praxis:journal_ingest)

## Summary
- 2487 journal files on disk, 2498 unique evaluated entries
- 10 unevaluated journals found and processed
- 4 forge no-ops batched (pre-filter optimization)
- 6 journals individually processed
- 2 new events: `cron_errors`, `calendar_conflict`
- 0 new lessons, 0 new shift proposals
- Active shifts: 12/12 (at cap, no changes)
- Malformed: 0

## Key Observations

1. **Batch pre-filter for forge no-ops works** — Instead of fully parsing every forge journal through `extract_signals_from_dict`, the script first does a lightweight `is_forge_no_op()` check that inspects only the `result` and `status` fields. This avoids the overhead of full signal extraction for the ~400+ routine forge scan journals. The 4 forge no-ops were batch-marked as evaluated in a single append operation. This pattern should be the default for all future ingest runs.

2. **New `cron_errors` signal type** — Finch scan-1013 produced a `cron_errors` signal (plural), distinct from the existing `cron_error` (singular) events. 4 different cron jobs failing:
   - `custodian:deep` — RuntimeError: Response truncated after 3 continuation attempts
   - `dispatch:email_check` — ModuleNotFoundError: No module named google_auth_mcp
   - `ocas-weave` — RuntimeError: HTTP 429 Provider error
   - `bones:research` — RuntimeError: Upstream idle timeout exceeded
   This is the first occurrence — needs 3+ events to warrant a lesson. Tracked for pattern emergence.

3. **`calendar_conflict` already covered** — UCSF/TheTopaz scheduling conflict. Existing lesson `les-20260615083557-0001` covers this pattern. No new lesson needed.

4. **Cap at 12/12 — no shift proposals** — All 12 active shifts are 1-2 days old with 0 reinforcements. The `cron_errors` signal is new but at cap, no shift was proposed. If `cron_errors` recurs in future runs, it will accumulate events and eventually warrant a lesson + shift.

5. **Eval file growth** — `journals_evaluated.jsonl` now at 2513 entries. The `.json` extension normalization continues to work correctly for dedup. No compaction needed (under 5000 threshold).

6. **No gotchas encountered** — All known patterns (forge no-ops, spot observations, mentor malformed) handled correctly by existing code paths.

## No Action Needed
- Journal backlog is clean
- `cron_errors` tracked for pattern emergence (1/3 toward lesson threshold)
- System operating in steady state
