#!/bin/bash
# Shell heredoc template for writing JSON journal files in cron mode.
# Avoids Python heredoc corruption (smart-quote conversion, variable truncation, SyntaxError).
# Usage: source this template, set TS/NOW/JOURNAL_DIR, then cat the heredoc.

# Compose timestamps ONCE in shell, reuse for filename and content
TS=$(date -u +%Y%m%dT%H%M%SZ)
NOW=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
TS_SHORT="${TS%Z}"  # strip trailing Z for filename, re-add below
JOURNAL_DIR="/root/.hermes/profiles/indigo/commons/journals/ocas-praxis/$(date -u +%Y-%m-%d)"
mkdir -p "$JOURNAL_DIR"

cat > "$JOURNAL_DIR/praxis-cron-${TS_SHORT}Z.json" <<EOF
{
  "run_type": "cron_ingest",
  "run_id": "praxis-cron-${TS}",
  "timestamp": "${NOW}",
  "journals_scanned": ${JOURNALS_SCANNED:-0},
  "journals_evaluated": ${JOURNALS_EVALUATED:-0},
  "events_recorded": ${EVENTS_RECORDED:-0},
  "lessons_extracted": ${LESSONS_EXTRACTED:-0},
  "lessons_removed_noise": ${LESSONS_REMOVED_NOISE:-0},
  "active_shifts": ${ACTIVE_SHIFTS:-0},
  "cap_usage": "${CAP_USAGE:-0/12}",
  "gap_journals_backfilled": ${GAP_JOURNALS_BACKFILLED:-0},
  "eval_file_lines": ${EVAL_FILE_LINES:-0},
  "not_activity_reason": "${NOT_ACTIVITY_REASON:-Routine cron ingest}"
}
EOF

# Verify
ls -la "$JOURNAL_DIR/praxis-cron-${TS_SHORT}Z.json"