# Escalation Fingerprint Enrichment

## Problem

Some journals (especially custodian light scans) set `escalation_needed: true` at the top level but do NOT have a top-level `escalation_fingerprint` field. The existing `praxis_ingest_run.py` reads:

```python
journal_data.get('escalation_fingerprint', '')
```

This returns `""`, producing events with fingerprint `"unknown"` — even when the journal contains rich escalation data in `findings[]`.

## How to detect

A custodian light journal with detailed findings looks like:

```json
{
  "run_id": "light-2026-05-30-200000",
  "escalation_needed": true,
  "summary": {"total_jobs": 104, "error_jobs": 10, ...},
  "findings": [
    {
      "issue": "Auxiliary Nous client unavailable - payment/credit error",
      "fingerprint": "oc_auxiliary_nous_payment_error",
      "tier": 3,
      "escalation_needed": true,
      "fix_applied": false
    },
    {
      "issue": "MCP server connection failures",
      "fingerprint": "oc_mcp_connection_failure",
      "tier": 2,
      "already_tracked": true
    }
  ]
}
```

## Extraction rule

When `escalation_needed: true` at the top level:

1. Check for `escalation_fingerprint` at top level — if present, use it
2. If absent/empty, scan `findings[]` for items where `tier == 3` OR `finding.escalation_needed == true`
3. For each such finding, create a **separate signal** with:
   - `fingerprint`: `finding.fingerprint`
   - `summary`: `finding.issue` (human-readable title)
   - `phase`: `"planning"` for tier-3, `"execution"` for tier-2
   - `severity`: `"high"` for tier-3, `"medium"` for tier-2
   - `already_tracked`: `finding.already_tracked` (if `true`, lower priority)
4. If `findings[]` is also absent, fall back to `"unknown"` fingerprint (current behavior)

## Production observation

In the 2026-05-31 ingest, the custodian `light-2026-05-30-200000.json` had two tier-3 escalations:
- `oc_auxiliary_nous_payment_error` (116+ occurrences/day)
- Implicit tier-3 in findings

The ingest produced a single generic "Escalation: unknown" event because the top-level fingerprint was missing. The `findings[]` data was not consulted. This means the Nous payment error fingerprint never got reinforced correctly.

## Related gotcha

See SKILL.md "System escalation signals from custodian scans" for the broader escalation handling rule.
