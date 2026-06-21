# Mentor-Light Journal Ingest: Noise Filter Pattern

## Problem

Mentor-light heartbeat journals are routine operational records. When ingested by Praxis, they produce false-positive behavioral signals because:

1. Summary text contains words like "error" in success context ("0 errors detected")
2. `gap_detected: true` fires from normal cron cadence (27min gaps in 30min cron)
3. `low_coverage` (0.14-0.30) reflects scan-yield math, not system failure
4. `evaluation_coverage` undercounts by design (only counts skills with new files)

These false positives produce noise events, noise lessons, and noise shifts that pollute the behavioral refinement loop.

## Noise Filters (Mandatory)

Apply these filters at event-recording time. If ANY filter matches, skip the journal entirely or emit `no_signal`.

### Filter 1: Success with No Failure Indicators

```python
if outcome in ("success", "", None) and not gap_detected and errors_count == 0:
    skip  # routine success, no behavioral signal
```

### Filter 2: Gap Detected + Success (Cron Cadence)

```python
if gap_detected and outcome in ("success", "", None):
    skip  # gap is normal cron interval, not a real failure
```

### Filter 3: Mentor-Light Low Coverage (Measurement Artifact)

```python
if source_journal.startswith("ocas-mentor/") and signal_type == "low_coverage":
    skip  # coverage <1.0 is expected when only some skills have new files
```

### Filter 4: Failure Keyword from Summary Text

```python
if source_journal.startswith("ocas-mentor/") and outcome in ("success", "", None):
    # Summary text like "0 errors detected" or "2 historical error records"
    # produces failure_keyword via generic scanner. These are FALSE positives.
    skip ALL signal extraction for this journal
```

### Filter 5: Active Anomalies Count of 0

```python
if data.get("active_anomalies", 0) == 0 and outcome == "success":
    # No anomalies detected — no signal to extract
    skip
```

## Expected Outcome

For a typical dispatch ingest of 3-35 mentor-light journals: **0 events recorded**. All journals are routine success with no behavioral signal. This is the expected and correct result.

## When to Record Events from Mentor-Light

Only record an event from a mentor-light journal if:
- `outcome == "error"` or `outcome == "failed"` (explicit failure)
- `metrics.errors > 0` (actual errors detected)
- `gap_detected: true` AND `outcome != "success"` (gap with failure — not just cron cadence)

## Integration with Ingest Script

In the production ingest script (`praxis_ingest_run.py` or inline scripts), implement filters as early as possible — ideally before signal extraction to avoid wasted processing:

```python
# Early-exit for routine mentor-light success
if skill == "ocas-mentor" and data.get("type", "").startswith("mentor-light"):
    outcome = data.get("outcome", data.get("status", ""))
    if outcome in ("success", "", None):
        metrics = data.get("metrics", {})
        if not data.get("gap_detected", False) and metrics.get("errors", 0) == 0:
            continue  # skip to next journal
```

## Pitfall: Do NOT Add These to NOISE_SIGNAL_TYPES Globally

`low_coverage` and `gap_detected` may be legitimate signals from other skills (e.g., custodian, finch). Filter specifically at the journal level for mentor-light only, not globally.
