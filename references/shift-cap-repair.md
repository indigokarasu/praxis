# Shift Cap Repair Pattern

## When to Use

When the active shift count exceeds the configured cap (default 12) due to an ingest bug or manual error.

## Root Causes (Known)

1. **Mutable list cap check** — Checking `len(active_shifts)` while appending to it in the same loop. The list grows each iteration; the cap is never hit.
2. **Counter not decremented after expiry** — After expiring a shift to make room, `active_count` must be decremented. If not, the next iteration sees the same count and expires the same shift again.
3. **No gate on append** — Even with a correct counter, if the `else` branch (under cap) doesn't check `active_count < MAX` before appending, shifts get added past the cap.

## Repair Procedure

```python
# 1. Load all shifts
all_shifts = load_jsonl(SHIFTS_FILE)
active = [s for s in all_shifts if s.get("status") == "active"]

# 2. If over cap, sort by priority and expire lowest
if len(active) > MAX_ACTIVE:
    # Sort: lowest reinforced_count first, then oldest activated_at
    active.sort(key=lambda s: (s.get("reinforced_count", 0), s.get("activated_at", "")))
    keep = active[-MAX_ACTIVE:]
    expire = active[:-MAX_ACTIVE]
    keep_ids = {s["shift_id"] for s in keep}
    
    # 3. Rewrite: expire over-cap, keep rest
    with open(SHIFTS_FILE, "w") as f:
        for s in all_shifts:
            if s.get("status") == "active" and s["shift_id"] not in keep_ids:
                s["status"] = "expired"
                s["expired_at"] = now
                s["expired_reason"] = "Cap consolidation"
            f.write(json.dumps(s) + "\n")
```

## Curated Rebuild (when domain quality is poor)

If the over-cap shifts also have poor domain assignments (e.g., `domain == signal_type`), do a full curated rebuild:

1. Group all events by `(signal_type, failure_phase)`
2. For each group, find the most common `skill` field -> this is the correct `domain`
3. Filter to meaningful signal types (exclude NOISE_SIGNAL_TYPES, require >=3 events)
4. Sort by event count descending, take top 12
5. Expire ALL currently active shifts
6. Write 12 new active shifts with proper skill-based domains

## Prevention in Ingest Scripts

```python
active_count = len([s for s in all_shifts if s.get("status") == "active"])

for lesson in candidate_lessons:
    if active_count >= MAX_ACTIVE:
        # Expire oldest/lowest-reinforced
        oldest = min(active_shifts, key=lambda s: (s.get("reinforced_count", 0), s.get("activated_at", "")))
        oldest["status"] = "expired"
        active_count -= 1  # MUST decrement
    
    # Now under cap - propose shift
    new_shift = {"status": "active", ...}
    active_count += 1  # MUST increment
```

**Key rule:** `active_count` must be a separate integer variable, never `len(active_shifts)` if `active_shifts` is being mutated in the loop.
