# Praxis Journal Ingest — 2026-05-31 01:24 UTC (Run 2)

## Summary

3 new journals processed. 2 events recorded. 0 lessons extracted. 1 shift reinforced.

## New Journals

### 1. ocas-custodian `light-20260530-1808`
- **Signal:** 2 new HTTP 429 errors (dispatch:briefing-deliver, spot:watch-sweep) since last scan
- **Pattern:** Known transient rate-limit pattern — no new failure modes
- **MCP google-search:** Persistent connection failure continues (escalation active)
- **Decision:** Record observation event, reinforce existing shift

### 2. ocas-finch `scan-1810`
- **Signal:** bones:paper-trade Telegram delivery failure — "message too long"
- **Pattern:** NEW — first occurrence of response-phase content-length delivery failure
- **Other signals:** Google OAuth expired (6+ days), elephas:ingest timeout — both already tracked
- **Decision:** Record failure event (response phase, user relevance). Hold for pattern (need 1 more occurrence)

### 3. ocas-spot `sweep_20260530_181000`
- **Signal:** None — routine sweep, no new availability
- **Known patterns:** Vagaro silent click, Meevo Angular change detection (both déjà vu)
- **Decision:** No event. Mark journal as consumed.

## Shift Reinforced

`shf-20260530025622916433` — "When a cron job makes API calls to external services, verify it uses exponential backoff on HTTP 429"
- Reinforcement count: 2 → 3
- Trigger: Custodian light scan detected 2 new HTTP 429 errors from manifest.build rate limiting

## Gotcha Discovery

**Near-duplicate journal IDs:** `journals_evaluated.jsonl` had 5100 lines but only 5095 unique IDs (5 duplicates). The JSON exact-match dedup script found 0 duplicates because the 5 extra entries have *slightly different* `journal_id` strings — not exact matches. The ingest's set-based pre-filter caught these correctly because it normalizes both sides to canonical form. Added new gotcha to SKILL.md.

## State After Run

- Events: 116 → 118
- Active shifts: 11/12 (unchanged, 1 slot open)
- Lessons extracted: 0 (no new patterns at threshold)
- journals_evaluated.jsonl: 5100 → 5103 entries
