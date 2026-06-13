# Session 2026-06-05 — Praxis Ingest Run 1

## Summary

Routine 30-min cron ingest. 5 unevaluated journals found, 1 event recorded, 0 new lessons, shift cleanup performed.

## Journals Processed

| Journal | Signal | Action |
|---------|--------|--------|
| `ocas-finch/2026-06-04/scan-2022.json` | `platform_failure` | Event recorded |
| `ocas-vesper/2026-06-04/r_20260604_evening.json` | none | no_signal |
| `ocas-elephas/2026-06-05/run_cron_20260605_024818.json` | none | no_signal |
| `ocas-elephas/2026-06-05/run_cron_20260605_034557.json` | none | no_signal |
| `ocas-spot/2026-06-04/sweep_20260604_204000.json` | none | no_signal |

## Event Details

- `platform_failure` / execution phase — Finch scan-2022 detected 17 error cron jobs (6 upstream 401s, 5 rate-limit 429s, 6 script-path failures). Google Calendar OAuth expired. Recurring pattern already covered by active `shift-finch-http429`.

## Shift Cleanup

- **Before**: 12 active + 150 proposed (133 spurious from proposal dedup bug)
- **After**: 12 active + 6 proposed + 144 expired
- Expired 144 redundant proposals: domain+phase overlap with active (45), non-actionable domains (68), lesson already covered by active shift (16), domain+phase overlap from second pass (15)
- 6 remaining proposed shifts are genuinely novel but cannot activate (at cap)

## Bugs Found

1. **Shift proposal dedup field mismatch** — The ingest script built `lessons_with_shifts` by checking only `lesson_id` and `lesson_ref`, but active shifts use `source_lesson_ids` (array) and `source_lesson` (string). This caused 133 spurious proposals. Fixed in `gotchas-praxis.md` and `ingest-script-pattern.md`.

2. **Post-write dedup loses multi-signal events** — Dedup by `source_journal` only keeps 1 event per journal. A single journal can have multiple distinct signal types. Should dedup by `(source_journal, signal_type)` composite key. Documented in `gotchas-praxis.md`.

## State After Run

- Events: 207 total (86 valid, 121 legacy noise)
- Lessons: 142 (134 high, 1 low)
- Shifts: 12 active / 6 proposed / 144 expired
- Evaluated journals: 5,895

## Recommendations

- Patch the ingest script's shift proposal dedup to check all lesson reference fields
- Consider expiring the 6 novel proposed shifts' domain+phase pairs that are adjacent to active ones (e.g., `finch/execution` proposed vs `finch/execution` active — merge rather than keep separate)
- The 121 legacy noise events (`signal_type: "?"`) could be cleaned up to reduce file bloat
