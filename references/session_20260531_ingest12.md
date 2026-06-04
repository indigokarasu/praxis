# Session: 2026-05-31 Ingest Run (journal_ingest #12)

## Run Summary
- **Date**: 2026-05-31T17:19:27Z
- **Journals scanned**: 4,805 total, 7 unevaluated
- **Journals with signals**: 3 (ocas-taste, ocas-custodian)
- **Routine journals**: 4 (no events)
- **Events recorded**: 4 (2 deduped out)
- **Lessons extracted (net)**: 0 new; 8 written then cleaned up as duplicates
- **Shifts activated**: 1 (ocas-taste auth-failure, proposed to active)
- **Shifts reinforced**: 1 (ocas-custodian auth-token, r=3 to 4)
- **Active shifts after**: 6/12

## New Events
1. **ocas-taste auth_failure** — empty Google token file (0 bytes, json.loads fails)
2. **ocas-custodian escalation** — email auth token corrupt, kanban SQLite I/O error
3. **ocas-custodian routine light scan** — no new issues, known items unchanged
4. **ocas-custodian routine light scan** — single Tier 2 disk I/O

## Bugs Found

### 1. Ad-hoc scan script re-extracted duplicate lessons
**Problem**: The ad-hoc scan script (`/tmp/praxis_scan.py`) ran lesson extraction against ALL events in the store without checking `existing_lesson_keys`. This produced 8 lessons, all of which were re-extractions of patterns already captured by existing lessons with different IDs.

**Fix**: The production ingest script (`scripts/praxis_ingest_run.py`) has the correct pattern:
```
existing_lesson_keys = set()
for les in existing_lessons:
    k = (les.get('domain', ''), les.get('failure_phase', ''), les.get('pattern_key', ''))
    existing_lesson_keys.add(k)
# ... before extracting ...
if lesson_key in existing_lesson_keys:
    continue
```
**Lesson**: When writing any lesson extraction code (ad-hoc scripts, helper files, or manual extraction), ALWAYS load existing lessons first and skip any (domain, phase, signal_type) key that already exists. Never extract lessons from the full event store without deduplicating against existing lessons.

### 2. Domain normalization gap in event recording
**Problem**: The scan script extracted domain directly from journal path (`jid.split("/")[0]`). When the journal directory name did not match the canonical skill name (e.g., `custodian/` instead of `ocas-custodian/`), events were recorded with an incorrect domain that did not match any shift.

**Fix applied post-hoc**: 2 events fixed with Python script to normalize `custodian` -> `ocas-custodian`.

**Lesson**: When recording events from journals, maintain a canonical domain mapping. If a directory name does not match a known skill name, check aliases before recording the raw directory name as the domain.

## Cleanup Actions
- events.jsonl: 2 duplicates removed
- lessons.jsonl: 20 to 10 (removed re-extractions, noise, and domain-mismatch entries)
- Fixed 2 events: domain=custodian -> domain=ocas-custodian

## System State Post-Run
| Metric | Value |
|--------|-------|
| events.jsonl | 214 |
| lessons.jsonl | 10 |
| shifts.jsonl | 6 (6 active / 12 cap) |
| journals_evaluated.jsonl | 5,085 |

## SKILL.md Updates
- Added gotcha: **Ad-hoc scripts must deduplicate lesson keys against existing lessons before extraction**
- Added gotcha: **Domain normalization when recording events from journal paths**
