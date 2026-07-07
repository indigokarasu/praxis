# Praxis Cron Journal Template

## Shell Heredoc Template for Cron-Mode Journal Writing

**Location:** `templates/praxis_cron_journal.sh`

**Purpose:** Avoids Python heredoc corruption (smart-quote conversion, variable truncation after closing quotes, `SyntaxError: invalid decimal literal` from mangled dict literals) when writing JSON journal files in cron mode.

**Usage:**
```bash
# Source the template or copy the pattern
TS=$(date -u +%Y%m%dT%H%M%SZ)
NOW=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
TS_SHORT="${TS%Z}"
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
```

**Key points:**
- Compose timestamps ONCE in shell, reuse for filename and content
- Strip trailing Z from timestamp for filename (`TS_SHORT="${TS%Z}"`), re-add in template
- Use `cat > file <<EOF` heredoc (not Python `<< 'PYEOF'`)
- Shell variable expansion handles JSON structure naturally
- Always `ls` output to verify filename (catches double-Z pitfall)

**Double-Z pitfall:** If `TS` already ends in `Z` and template uses `${TS}Z.json`, result is `...ZZ.json`. The `${TS%Z}` strip prevents this.

**When to use:** Every cron-mode Praxis journal write. Reserve Python heredocs for eval file reads/writes with programmatic content (no raw double-quoted JSON).