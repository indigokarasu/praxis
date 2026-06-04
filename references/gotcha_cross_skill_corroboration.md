# Gotcha: Cross-Skill Corroboration Signals

## Problem
When two independent skill scans detect the same issue within a short time window (e.g., <5 minutes), the ingest may record two events for what is essentially the same occurrence. Without explicit handling, this produces duplicate events that inflate pattern counts and can trigger spurious lessons.

## Production Example (2026-05-31)
- `ocas-custodian` light-scan at 18:08 UTC: detected `finch:weekly` HTTP 401 from Manifest.build provider (Tier 3, escalation_needed)
- `ocas-finch` scan-1800 at 18:10 UTC: independently detected the same `finch:weekly` HTTP 401
- Both journals had `escalation_needed: true` and the same fingerprint (`oc_http_401_manifest_provider`)
- Without corroboration logic, both would produce separate events, doubling the pattern count

## Detection Rule
When recording an event from a journal, check whether an event with the **same fingerprint** (or same `issue_id` in metadata) already exists in `events.jsonl` from a different source journal within the last 30 minutes. If yes:

1. **Do NOT create a duplicate event** — instead, create a single "corroboration" event that references both source journals
2. The corroboration event's `metadata.corroborates_event` field should point to the first event
3. The corroboration event's `metadata.issue_id` should match the shared fingerprint
4. Use `signal_type: "escalation"` with `outcome: "escalation_confirmed"`

## When Corroboration Matters
Corroboration increases confidence when:
- Both sources are independent (different skills, different scan mechanisms)
- The fingerprint/issue_id matches exactly
- The time window is short (<30 minutes)
- Both sources flag escalation

Corroboration does NOT apply when:
- One journal is a re-read of the other's output (e.g., lucid curating praxis journals)
- The events are from the same skill (same `domain`)
- The time gap is >24 hours (likely a recurrence, not corroboration)

## Where Applied
- `references/journal_ingestion.md` — signal extraction rules (cross-reference check)
- SKILL.md — gotcha section (this file)
