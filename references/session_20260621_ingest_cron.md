# Session 2026-06-21 Praxis Cron Ingest

## Summary

Cron ingest run at `2026-06-21T06:14:29Z`. Production script `praxis_ingest_run.py` found 0 new journals due to date-filter bug. Manual mtime-based discovery found 7 new journals. After dedup, 3 were newly evaluated, all producing `no_signal`. 0 events, 0 lessons, 0 shifts.

## New Journals Found (mtime > last_ingest_run)

| File | mtime (UTC) | Status | Signals |
|------|-------------|--------|---------|
| `ocas-custodian/2026-06-20/light-scan-20260620T230500-0700.json` | 06:06:29 | Already evaluated | — |
| `ocas-mentor/2026-06-21/mentor-light-20260621T061238Z.json` | 06:12:38 | Already evaluated | — |
| `ocas-mentor/2026-06-21/mentor-light-20260621T061343Z.json` | 06:13:43 | Already evaluated | — |
| `ocas-mentor/2026-06-21/mentor-light-20260621T061606Z.json` | 06:16:07 | Already evaluated | — |
| `ocas-forge/2026-06-21/forge-journal-scan-20260621T061812Z.json` | 06:18:12 | **New** | no_signal (forge_no_op) |
| `ocas-mentor/2026-06-21/mentor-light-20260621T061812Z.json` | 06:18:12 | **New** | no_signal (mentor_light_success) |
| `ocas-mentor/2026-06-21/mentor-light-20260621T062116Z.json` | 06:21:16 | **New** | no_signal (mentor_light_success) |

## Key Findings

### 1. Production Script Date Filter Bug (CONFIRMED AGAIN)

The production `praxis_ingest_run.py` uses a `today/yesterday` date directory filter that found **0 new journals** even though 7 had mtime > last_ingest_run. This is the same bug documented in the "Ingest date window too narrow" gotcha, but the production script still has it.

**Workaround used this session:** Wrote ad-hoc `ingest_cron_20260621.py` with mtime-based discovery.

### 2. `find -newermt` Timezone Bug (NEW GOTCHA)

`find -newermt "2026-06-21T06:02:14"` interprets the timestamp as **local time**, not UTC. With the system at UTC-7, this makes the comparison ~7 hours off, missing all journals written in the actual window.

**Fix:** Use numeric mtime comparison in Python: `os.path.getmtime(fp) > last_ingest_mtime`

### 3. Custodian `type: "observation"` Filter (NEW GOTCHA)

Custodian journals with `type: "observation"` are routine platform scans. Emit `no_signal` and skip signal extraction.

## State After Run

- Events: 0 new (2,625 total)
- Lessons: 0 new (74 total)
- Shifts: 0 new (12 active / 12 cap)
- Journals evaluated: 3 new (23,910 total)
