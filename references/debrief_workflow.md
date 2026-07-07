# Debrief Generation Workflow

## When to Run

- Scheduled cron `praxis:debrief` runs at 6am daily
- Manual run via `praxis.debrief.generate` when outside cron context
- After any significant ingest run that produces new lessons or shifts

## Steps

### 1. Load Active Shifts

Read `shifts.jsonl`, filter `status == "active"`. For each:
- `reinforcement_count`: how many times the shift has been reinforced by new events
- `activated_at` / `last_reinforced_at`: for age calculation
- `shift_text`: the behavioral rule text

### 2. Historical Context (Last 7 Days)

Read `debriefs.jsonl` (last 10 entries) to understand recent trajectory:
- Are shifts accumulating or expiring?
- Were there prior open questions resolved?
- Any prior decay warnings that materialized?

Also read `ingest_state.json` for `last_ingest_run`, `total_events_in_store`, and `active_shifts_count`.

**⚠ Gotcha:** `ingest_state.json:active_shifts_count` may not match `shifts.jsonl` filtered count. The state file is updated by ingest scripts which may count proposed+active, or use different status values. Always use `shifts.jsonl` filtered by `status == "active"` as the ground truth.

### 3. Decay Analysis

Flag shifts where:
- `reinforcement_count == 0` AND age > 10 days → "approaching decay"
- Age computed from `last_reinforced_at` (fallback to `activated_at`, then `created_at`)
- Config TTL: 14 days (from `config.json:shifts.ttl_days`)

**Zombie Shift Detection:** Shifts with `reinforcement_count == 0` AND no `last_reinforced_at` field at all are "zombie shifts" — they were created (usually during a bulk rebuild or migration) but the reinforcement pipeline has never touched them. These are distinct from "young" shifts that haven't had time to be reinforced. Zombie shifts:
- Typically share identical `created_at` timestamps (batch-created)
- Have overlapping template text with same-domain/sibling shifts
- Consume cap space without evidence of ongoing behavioral relevance
- **Action:** Recommend consolidation or expiration. If >50% of active shifts are zombies, flag as "cap occupied by stale batch" in debrief summary.

### 4. Overlap Scan

Group active shifts by `domain + failure_phase`. Within each group, check text similarity (>3 shared words = potential overlap). These are consolidation candidates.

### 5. Lessons Pipeline Health

Check `lessons.jsonl` size. If it has 0 entries across multiple ingest runs, the lesson extraction pipeline is dormant. This is distinct from low signal velocity — it means either:
- Bug-2 noise cleanup is too aggressive (legitimate lessons are being filtered)
- Signal density is genuinely too low for pattern extraction
- The extract pipeline itself has a failure

**Action:** If `lessons.jsonl` is empty and there were ≥10 non-no_signal events in the ingest window, flag as "possible pipeline issue — events present but no lessons extracted".

### 6. Event Analysis

Count last 200 events by `skill/signal_type` to identify emerging patterns. Check if any signal types have reached the ≥2 threshold for lesson extraction but haven't produced lessons yet. Also review `lessons.jsonl` for recent extractions that may be ready for shift promotion.

**Signal Velocity Check:** Compare events-per-day over the last 7 days vs. the prior 7 days. If real-signal events drop >80% between windows, flag as "signal velocity collapse" — this could indicate either genuine system stability (positive) or an ingest pipeline gap (negative). Check `ingest_state.json:last_ingest_run` recency and journal eval counts to distinguish.

### 6. Cap Headroom

- If active shifts ≥ 10: flag "approaching cap"
- If active shifts = 12: list weakest shift (0 reinforces) for potential manual expiry
- New shift proposals blocked at cap

### 7. Shift Population Collapse Audit

Before writing the debrief, compare current active shift count against the last debrief's count (from `debriefs.jsonl`, last entry). A drop of ≥3 shifts between consecutive debriefs is a **"shift collapse"** event that must be:
- Noted in `findings` (e.g., "Shift population collapsed: 9 → 3 (-6) since last debrief. Mass expiry of June-18 rebuild batch suspected.")
- Included in the `expired_shifts` count if it explains the drop
- Flagged in `recommendations` if the collapse freed cap space for new proposals

This audit trail prevents silent loss of behavioral coverage that would otherwise be invisible until the next lesson extraction produces patterns the expired shifts would have handled.

### 8. Write Debrief

**CRITICAL**: Use `open(DEBRIEFS_FILE, 'a')` — NEVER `write_file()` on JSONL files.

```python
with open(DEBRIEFS_FILE, "a") as f:
    f.write(json.dumps(debrief) + "\n")
```

### 7. Update Ingest State

Update `ingest_state.json` with `last_debrief_run` timestamp.

**Note:** Do NOT trust `ingest_state.json:active_shifts_count` — always recompute from `shifts.jsonl`. See `references/gotcha_ingest_state_shift_count.md`.

## Debrief JSON Schema

```json
{
  "debrief_id": "debrief-YYYYMMDDTHHMMSS",
  "generated_at": "ISO timestamp",
  "period": "YYYY-MM-DD to YYYY-MM-DD",
  "active_shift_count": 9,
  "cap_usage": "9/12",
  "new_shifts": 0,
  "expired_shifts": 2,
  "new_lessons": 27,
  "summary": "Plain-language summary",
  "findings": ["finding 1", "finding 2"],
  "recommendations": ["rec 1", "rec 2"],
  "shifts_approaching_decay": [
    {"shift_id": "...", "domain": "...", "signal": "...", "reinforcement_count": 0, "status": "never_reinforced"}
  ],
  "consolidation_candidates": [
    {"shifts": ["id1", "id2"], "reason": "...", "suggested_action": "..."}
  ],
  "events_ingested": 463,
  "lessons_extracted": 27,
  "shifts_proposed": 0,
  "shifts_activated": 0,
  "shifts_expired": 2
}
```

## Common Findings

- **Custodian Tier 1 fixes applied**: Genuine positive signal, reinforces existing shifts
- **Mentor-light false positives**: `failure_keyword` from success summaries, `gap_detected` from cron cadence
- **Cap saturation**: New lessons cannot become shifts until decay releases slots
- **Eval file dedup broken**: 21,082 entries don't match disk paths (known issue 2026-06-19)
