# Praxis ingest CLI pitfall: `--help` is not safe

Observed in a dispatch cleanup session: invoking `python3 skills/ocas-praxis/scripts/praxis_ingest_run.py --help` did **not** print usage and exit. The script ignored/accepted the extra argument and executed a full ingest run, processing journals, writing events, extracting lessons, and writing a praxis-cron journal.

## Durable rule

Treat `praxis_ingest_run.py` as an action script with no safe dry-run/help mode unless the script source has been inspected and a non-mutating option is confirmed.

## Safe pattern

1. Do not probe it with `--help` during cron dispatch.
2. If you need to know its interface, inspect the script source instead of executing it with guessed flags.
3. Before running it, assume side effects: eval entries, event records, lessons, evidence, and a praxis journal may be written.
4. After running it, locate the actual journal it wrote on disk and bridge/register that real filename, not an assumed dispatch filename.

## Why this matters

In explicit Forge + Mentor + Praxis dispatch waves, a mistaken `--help` probe can become the Praxis run. That is acceptable only if treated as a real completed ingest and followed by normal verification and eval bridging.