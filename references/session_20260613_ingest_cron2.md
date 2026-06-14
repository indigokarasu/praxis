# Praxis Ingest Session Notes — 2026-06-13 (Cron #2)

## What Happened

Ran two-pass journal ingest: first with standard today+yesterday window, then a supplemental broad scan to catch timezone-offset files.

## Key Findings

### Standard Window Scan (6 journals)
All 6 journals from 2026-06-12/13 were routine no-ops:
- 3 ocas-forge journal-scans (no unprocessed files)
- 2 ocas-spot watch sweeps (no new availability)
- 1 ocas-elephas ingest (0 signals created)

No new behavioral signals from current window.

### Supplemental Broad Scan (390 journals)
The supplemental scan walked ALL journal directories and found 390 unevaluated journals. This was **too aggressive** — it included journals from April-May and extracted 12 events from old data:

- **custodian escalations** (2): `escalation_needed: true` from April 26 and May 31
- **ocas-taste spotify-sync failures** (6): `status: failed` from April 13-17, May 15, May 17
- **ocas-weave sync partial failures** (4): `status: completed_with_errors` from June 4, June 6

### Result
- 12 new events recorded (all from backlog)
- 1 new lesson: `escalation/execution` (3 events from custodian/ocas-custodian)
- 1 new shift activated: `shf_20260613_044459_40137a4a`
- Active shifts: 7/12

## Lessons Learned

1. **Broad scans are dangerous**: Walking ALL journal directories without an mtime filter floods the system with stale events. Future supplements should filter by `mtime > now - 48h`.
2. **Timezone-offset files**: Journals written by processes using PDT timezone can end up in future-dated directories (e.g., June 15 when UTC is June 13). The standard today+yesterday window misses these. mtime-based filtering catches them without historical backfill.
3. **Evaluated file grows fast**: The supplemental scan added 390 entries to `journals_evaluated.jsonl`, bringing it to 664. Compaction at 5,000 entries is still far off but worth monitoring.

## Actions Taken for Next Time

- Added gotcha entry: "Broad supplemental scans flood events from stale journals"
- Added mtime-based filtering pattern to `ingest-script-pattern.md` §3b
- All future supplemental scans should use `os.path.getmtime()` filter instead of full walk
