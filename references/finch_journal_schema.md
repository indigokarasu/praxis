# Finch Journal Schema Reference

## Full Rescan Journals

Finch full rescan journals (e.g., `scan-2335.json`) use this structure:

```json
{
  "scan_time": "2026-05-31T23:35:00Z",
  "scan_type": "full_rescan",
  "findings": {
    "cron_health": { "status": "unavailable", "detail": "..." },
    "email": { "status": "blocked", "detail": "..." },
    "calendar": { "status": "blocked", "detail": "..." },
    "sessions": { "status": "ok", "detail": "..." },
    "drive": { "status": "blocked", "detail": "..." },
    "system": { "status": "ok", "detail": "..." }
  },
  "changes_since_last_scan": {
    "new_items": 0,
    "resolved_items": 0,
    "status_changes": 0,
    "notes": "..."
  },
  "active_blockers": [
    {
      "id": "google-oauth-reauth-needed",
      "impact": "email scan, calendar scan, drive scan, ...",
      "fresh_consent_urls_issued": true,
      "recommendation": "..."
    }
  ],
  "recommendations": [...]
}
```

## Key Signal Sources

| Field | Signal Type | Notes |
|-------|-------------|-------|
| `active_blockers[].id` + `fresh_consent_urls_issued: true` | `auth_failure` | Google OAuth consent needed |
| `active_blockers[].id` (other) | `platform_failure` | Other blocking issue |
| `findings.*.status == "blocked"` | context | Use to validate blocker signal, not as standalone event |
| `changes_since_last_scan.status_changes > 0` | observation | State changed since last scan |

## Routine Scan Journals

Routine finch light scans use a different structure (not documented here — see finch scan-0 through scan-N series under the finch routine cron). Those have `sources_scanned` dict and `jobs_in_error` array at the top level.

## Praxis Ingestion Notes

- The production `praxis_ingest_run.py` `find_all_journals()` SKIPS `ocas-praxis` and `ocas-lucid` directories. Finch is NOT skipped.
- Finch journals are read by `extract_signals()` which checks `escalation_needed`, `execution_result`, `summary`, `actions_taken`, and now `active_blockers`.
- Signal dedup should check fingerprint against events from the same domain within 6 hours.
