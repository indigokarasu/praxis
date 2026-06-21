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

### 2. Decay Analysis

Flag shifts where:
- `reinforcement_count == 0` AND age > 10 days → "approaching decay"
- Age computed from `last_reinforced_at` (fallback to `activated_at`, then `created_at`)

### 3. Overlap Scan

Group active shifts by `domain + failure_phase`. Within each group, check text similarity (>3 shared words = potential overlap). These are consolidation candidates.

### 4. Event Analysis

Count last 200 events by `skill/signal_type` to identify emerging patterns. Check if any signal types have reached the ≥2 threshold for lesson extraction but haven't produced lessons yet.

### 5. Cap Headroom

- If active shifts ≥ 10: flag "approaching cap"
- If active shifts = 12: list weakest shift (0 reinforces) for potential manual expiry
- New shift proposals blocked at cap

### 6. Write Debrief

**CRITICAL**: Use `open(DEBRIEFS_FILE, 'a')` — NEVER `write_file()` on JSONL files.

```python
with open(DEBRIEFS_FILE, "a") as f:
    f.write(json.dumps(debrief) + "\n")
```

### 7. Update Ingest State

Update `ingest_state.json` with `last_debrief_run` timestamp.

## Debrief JSON Schema

```json
{
  "debrief_id": "debrief-YYYYMMDDTHHMMSS",
  "generated_at": "ISO timestamp",
  "period": "YYYY-MM-DD to YYYY-MM-DD",
  "active_shift_count": 12,
  "cap_usage": "12/12 (at cap)",
  "new_shifts": 0,
  "expired_shifts": 0,
  "new_lessons": 1,
  "summary": "Plain-language summary",
  "findings": ["finding 1", "finding 2"],
  "recommendations": ["rec 1", "rec 2"],
  "events_ingested": 0,
  "lessons_extracted": 0,
  "shifts_proposed": 0,
  "shifts_activated": 0,
  "shifts_expired": 0
}
```

## Common Findings

- **Custodian Tier 1 fixes applied**: Genuine positive signal, reinforces existing shifts
- **Mentor-light false positives**: `failure_keyword` from success summaries, `gap_detected` from cron cadence
- **Cap saturation**: New lessons cannot become shifts until decay releases slots
- **Eval file dedup broken**: 21,082 entries don't match disk paths (known issue 2026-06-19)
