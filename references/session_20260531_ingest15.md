# Praxis Ingest — 2026-05-31 22:20 UTC (ingest15)

## Summary

6 new journals processed. 7 events recorded. 2 lessons extracted. 1 shift reinforced.

## Journals Processed

| Journal | Skill | Signal |
|---|---|---|
| custodian-light-20260531-160000 | ocas-custodian | Tier 3 escalations (2), HTTP 429 (4 jobs), MCP failures |
| light-scan-2026-05-31-130000 | ocas-custodian | Same fingerprints — same-skill temporal dedup applied |
| mentor-light-20260531-204926 | ocas-mentor | sands MCP failure observed; heartbeat gap (info, skipped) |
| conflict-scan-2026-05-31 | ocas-sands | Degraded 46+ days, OAuth stale |
| morning-brief-20260531 | ocas-sands | Failed — ClosedResourceError |
| sweep_20260531_1446 | ocas-spot | Routine success, no signals |

## Events Recorded

1. `system/escalation` — Google OAuth token missing (Tier 3 confirmed)
2. `ocas-finch/escalation` — finch:weekly 401 reconfirmed (Tier 3)
3. `system/error` — HTTP 429 on 4 cron jobs (7-10 AM burst)
4. `system/error` — MCP mempalace/stealth-browser persistent failure
5. `ocas-sands/observation` — morning brief failed, ClosedResourceError
6. `ocas-sands/escalation` — conflict scan degraded 46+ days
7. `ocas-sands/escalation` — morning brief failed (cross-skill corroboration)

## Lessons Extracted

| ID | Domain | Pattern | Confidence |
|---|---|---|---|
| les-...-008 | ocas-finch | HTTP 429 rate limiting on burst-window scans | high |
| les-...-009 | ocas-sands | OAuth token missing → calendar operations fail | high |

## Gotchas Encountered

### Same-skill temporal dedup
Custodian 13:00 + 16:00 journals reported identical fingerprints. Before recording, checked events.jsonl for same fingerprint within 6 hours — skipped duplicates.

### Shift overlap not merged
Two ocas-custodian auth-token shifts overlap (rc=4 specific + rc=1 generic). Merge-before-cap rule not enforced this run.
