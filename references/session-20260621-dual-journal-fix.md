# Session 2026-06-21: Dual-Journal Directory Scan Fix

## Problem

The production `praxis_ingest_run.py` script (via `praxis_common.py`) only scanned the legacy
journal path (`/root/.hermes/commons/journals`, 4,016 journals) and completely missed the indigo
profile path (`/root/.hermes/profiles/indigo/commons/journals`, 8,335 journals).

This caused 30+ journals from today (2026-06-21) to remain unevaluated across multiple ingest
runs. These were all routine no-signal journals (forge no-ops, mentor-light success, custodian
observations), so no events were lost — but the eval file was incomplete.

## Root Cause

`praxis_common.py` had:
```python
JOURNALS_DIR = "/root/.hermes/commons/journals"
```

And `find_all_journals()` only walked that single directory.

## Fix Applied

1. Added `JOURNALS_DIRS` list with both paths (indigo first, legacy second)
2. Updated `find_all_journals()` to walk both directories, deduplicating by canonical ID
3. Added `NOISE_SIGNAL_TYPES` constant to the shared module
4. Added `FORGE_NO_OP_RESULTS` with all known no-op variants including `"no unprocessed"`

The fix was written to `scripts/praxis_common.py` in the ocas-praxis skill directory.

## Verification

After the fix, a manual dual-dir scan found 31 unevaluated journals (all from today), processed
them, and confirmed 0 new events — all were routine no-signals.

## Production Script Note

The production `praxis_ingest_run.py` imports from `praxis_common`, so it will automatically
pick up the dual-directory fix on next run. However, the production script also has a date filter
(`today in cid or yesterday in cid`) that may still miss some journals. The mtime-based discovery
approach (comparing `os.path.getmtime(fp)` against `last_ingest_run` timestamp) is more reliable
and should be considered as a replacement for the date filter in future updates.
