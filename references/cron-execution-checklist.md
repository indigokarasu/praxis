# Cron Execution Checklist — Production Script Pattern

After `praxis_ingest_run.py` completes, the caller must complete these steps. The script intentionally delegates state management to the caller.

## Step 1: Update `ingest_state.json`

```python
import json
from datetime import datetime, timezone

state_path = '/root/.hermes/profiles/indigo/commons/data/ocas-praxis/ingest_state.json'
with open(state_path) as f:
    state = json.load(f)

now = datetime.now(timezone.utc)
state['last_ingest_run'] = now.isoformat()
state['last_ingest_mtime'] = now.timestamp()
state['journals_processed'] = state.get('journals_processed', 0) + journals_processed_count
state['total_ingests'] = state.get('total_ingests', 0) + 1
state['last_ingest_events_added'] = events_recorded_count
state['last_ingest_journals_evaluated'] = journals_processed_count
state['last_evaluated_count'] = state.get('last_evaluated_count', 0) + journals_processed_count
state['last_ingest_file_count'] = journals_processed_count
state['last_event_id'] = 'evt-...' if events_recorded_count > 0 else None
state['note'] = 'cron ingest HH:MMZ: N journals, M events, summary'
state['events_recorded'] = events_recorded_count
state['last_run'] = now.isoformat()

with open(state_path, 'w') as f:
    json.dump(state, f, indent=2)
```

**CRITICAL:** If updating `last_ingest_run` with a timestamp that includes `+00:00`, do NOT append another `+00:00`. `datetime.isoformat()` already includes the offset. Double suffix (`+00:00+00:00`) causes `datetime.fromisoformat()` to fail with `ValueError`. Fix: `re.sub(r'\+00:00\+00:00$', '+00:00', ts)`.

## Step 2: Gap Journal Backfill

```python
import os, json
from datetime import datetime, timezone

# Load evaluated IDs
eval_ids = set()
with open('/root/.hermes/profiles/indigo/commons/data/ocas-praxis/journals_evaluated.jsonl') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            entry = json.loads(line)
            if isinstance(entry, dict):
                eval_ids.add(entry.get('journal_id', ''))
            elif isinstance(entry, str):
                eval_ids.add(entry)
        except:
            eval_ids.add(line)

# Load last_ingest_run from state
with open('/root/.hermes/profiles/indigo/commons/data/ocas-praxis/ingest_state.json') as f:
    state = json.load(f)
last_ingest_run = state.get('last_ingest_run', '')
try:
    li_dt = datetime.fromisoformat(last_ingest_run)
    li_ts = li_dt.timestamp()
except:
    li_ts = 0

# Scan both journal directories
journals_dirs = [
    '/root/.hermes/profiles/indigo/commons/journals',
    '/root/.hermes/commons/journals',
]

gap_entries = []
now_iso = datetime.now(timezone.utc).isoformat()

for jdir in journals_dirs:
    if not os.path.isdir(jdir): continue
    for root, dirs, files in os.walk(jdir):
        dirs[:] = [d for d in dirs if d not in ('ocas-praxis', '.archive')]
        for fname in files:
            if not fname.endswith('.json'): continue
            fpath = os.path.join(root, fname)
            canonical = os.path.relpath(fpath, jdir)
            
            lookup = canonical if canonical.endswith('.json') else canonical + '.json'
            alt = canonical[:-5] if canonical.endswith('.json') else canonical
            
            if lookup not in eval_ids and canonical not in eval_ids and alt not in eval_ids:
                mtime = os.stat(fpath).st_mtime
                if mtime < li_ts:
                    gap_entries.append({
                        'journal_id': lookup,
                        'evaluated_at': now_iso,
                        'action_taken': 'backfill'
                    })

if gap_entries:
    with open('/root/.hermes/profiles/indigo/commons/data/ocas-praxis/journals_evaluated.jsonl', 'a') as f:
        for e in gap_entries:
            f.write(json.dumps(e) + '\n')

**Large_batch awareness:** A single gap backfill can write thousands of entries if the eval file has a backlog of unevaluated historical journals (confirmed 2026-06-29: 5,817 entries). This is expected and correct — it journals that were never evaluated, not duplicates. After this initial catchup, subsequent runs should see near-zero gap journals. Always record the `backfill_count` in `ingest_state.json:gap_journals_backfilled`.

## Step 3: Write Praxis Journal

**CRITICAL PATH:** The journal directory is `.../journals/ocas-praxis/{date}` — NOT `.../jraxis/{date}`. A typo here writes the journal to a non-standard path where it won't be discovered by future ingest runs or gap backfill. Always verify the path contains `journals/ocas-praxis/` before writing.

**Shell heredoc template available:** See `templates/praxis_cron_journal.sh` for a ready-to-source shell heredoc template that handles timestamp composition correctly and avoids the double-Z pitfall. This is the recommended approach for cron-mode journal writing (avoids Python heredoc corruption).

```python
import json, os
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
today = now.strftime('%Y-%m-%d')
ts = now.strftime('%Y%m%dT%H%M%S')

# VERIFY: path must contain 'journals/ocas-praxis/' — not 'jraxis/'
journal_dir = f'/root/.hermes/profiles/indigo/commons/journals/ocas-praxis/{today}'
os.makedirs(journal_dir, exist_ok=True)

journal = {
    'journal_id': f'ocas-praxis/{today}/praxis-cron-{ts}Z',
    'run_type': 'cron_ingest',
    'run_id': f'praxis-cron-{ts}Z',
    'timestamp': now.isoformat(),
    'not_activity_reason': 'routine cron ingest: N journals, M events, summary',
    'metrics': {
        'journals_evaluated': 0,
        'events_recorded': 0,
        'events_deduped': 0,
        'lessons_extracted': 0,
        'shifts_proposed': 0,
        'shifts_activated': 0,
        'active_shifts': 0,
        'cap_usage': '9/12',
        'gap_backfill': 0,
    },
    'entities_observed': [],
    'relationships_observed': [],
    'preferences_observed': [],
    'data_quality': {
        'malformed_journals': 0,
        'false_positive_filtered': 0,
        'noise_events': 0,
    },
}

fpath = os.path.join(journal_dir, f'praxis-cron-{ts}Z.json')
with open(fpath, 'w') as f:
    json.dump(journal, f, indent=2)
```

## Step 3b: Third-Wave Mitigation (MANDATORY)

After writing the Praxis journal, add its ID to `journals_evaluated.jsonl` so a subsequent cron run in the same dispatch wave doesn't re-discover it as "new":

```python
import json
from datetime import datetime, timezone

EVAL_FILE = '/root/.hermes/profiles/indigo/commons/data/ocas-praxis/journals_evaluated.jsonl'
now_iso = datetime.now(timezone.utc).isoformat()

with open(EVAL_FILE, 'a') as f:
    entry = {
        'journal_id': f'ocas-praxis/{today}/praxis-cron-{ts}Z.json',
        'evaluated_at': now_iso,
        'action_taken': 'self_reference_skip',
        'source': 'praxis_self'
    }
    f.write(json.dumps(entry) + '\n')
```

Without this, the next cron run discovers the just-written journal via mtime comparison, re-evaluates it (finding 0 signals), writes a duplicate journal entry, and inflates the eval count. Confirmed 2026-06-24 dispatch #33.

## Step 4: Post-Ingest Decay-Risk Scan

Mandatory after every cron ingest run. Check active shifts for decay risk:

```python
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
decay_risk = []
for s in active_shifts:
    act = s.get('activated_at', '')
    try:
        act_dt = datetime.fromisoformat(act)
    except:
        continue
    age_days = (now - act_dt).days
    reinf = s.get('reinforcement_count', 0)
    if reinf == 0 and age_days > 7:
        decay_risk.append(f"{s.get('signal_type','?')}|{s.get('domain','?')} age={age_days}d")
```

Include `decay_risk_shifts` count in journal metrics. Flag in debrief when any shift >10 days without reinforcement.

## Step 5: Noise Lesson Cleanup

**CRITICAL CONTEXT:** The production script's lesson extraction scoping bug (processes full 3,400+ event history) means that "new lessons" with high event counts (n=9, n=10, etc.) are almost always **stale noise**, not genuine new patterns. After every run:

1. Check the script output for "NEW LESSONS" — if they show `confidence: low` or high event counts from historical dates, they are noise.
2. Remove all `confidence: low` lessons — they lack causal grounding and cannot produce shifts.
3. Genuine new patterns will have `confidence: high` and events from the current run's date range only.

**Fast pre-filter (2026-06-29):** Before iterating lessons individually, check if ALL events recorded in the current run are `no_signal`. If yes, ALL lessons produced in the same run are Bug-2 noise — archive and clear `lessons.jsonl` immediately without per-lesson inspection. This avoids the expensive per-lesson `signal_type` check when the answer is already determined. Confirmed 2026-06-29: 13 lessons produced from 4 events (3 no_signal, 1 failure_keyword) — all had `signal_type=None` (key missing entirely), all were noise. The fast pre-filter would have skipped 13 individual checks.

```python
import json, os
from datetime import datetime, timezone

DATA_DIR = '/root/.hermes/profiles/indigo/commons/data/ocas-praxis'
LESSONS_FILE = os.path.join(DATA_DIR, 'lessons.jsonl')

now = datetime.now(timezone.utc)
# CRITICAL: lesson_id format is les-YYYYMMDDHHMMSSXXXXX-NNNNN (NO hyphens in date).
# Do NOT use now.strftime('%Y-%m-%d') — that produces '2026-06-28' which will never
# match the 'les-20260628...' prefix. Use the underscore-free date prefix instead.
today_prefix = 'les-' + now.strftime('%Y%m%d')  # e.g. 'les-20260628'

kept = []
removed = 0
with open(LESSONS_FILE) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        les = json.loads(line)
        conf = les.get('confidence', 'low')
        lid = les.get('lesson_id', '')
        # Remove low-confidence lessons produced by THIS run's historical reprocessing
        if conf == 'low' and lid.startswith(today_prefix):
            removed += 1
            continue
        kept.append(line)

with open(LESSONS_FILE, 'w') as f:
    for line in kept:
        f.write(line + '\n')

print(f'Lessons kept: {len(kept)}, removed (low conf, today): {removed}')
```

**PITFALL — Date format mismatch (confirmed 2026-06-28):** The first attempt used `today_str = now.strftime('%Y-%m-%d')` (hyphenated) and matched with `today_str in lid`. Lesson IDs use `les-20260628183201755195-21211` — the date portion has NO hyphens. Result: 0 matches, stale lessons survived. Fix: use `lid.startswith('les-' + now.strftime('%Y%m%d'))`.

## Step 5b: Malformed & Noise-Signal Lesson Cleanup (MANDATORY — 2026-06-27)

Step 5 removes `confidence: low` lessons. But the production script's full-history reprocessing also produces `confidence: high` lessons that are still noise — either with **empty `signal_type`** (legacy events lacking a `skill` field) or with **noise signal types** that pass the ≥2 threshold from historical accumulation.

After Step 5, run this second cleanup pass:

```python
import json, os

DATA_DIR = '/root/.hermes/profiles/indigo/commons/data/ocas-praxis'
LESSONS_FILE = os.path.join(DATA_DIR, 'lessons.jsonl')

# Noise signal types that produce meaningless lessons even at confidence: high
NOISE_SIGNAL_TYPES = {
    '', 'unknown', '?', 'no_op', 'routine', 'no_signal', 'cron_error',
    'cron_errors', 'observation', 'success', 'mentor_light', 'low_coverage',
    'gap_detected', 'correction', 'anomaly', 'stale_counters', 'fixes_applied',
    'new_tasks_found', 'task_resolved', 'directive', 'parse_error',
    'security_alert', 'calendar_conflict', 'auth_failure', 'coverage_gap',
}

kept = []
removed = 0
with open(LESSONS_FILE) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        les = json.loads(line)
        st = les.get('signal_type', '').strip().lower()
        if not st or st in NOISE_SIGNAL_TYPES:
            removed += 1
        else:
            kept.append(line)

with open(LESSONS_FILE, 'w') as f:
    for line in kept:
        f.write(line + '\n')

print(f'Malformed/noise cleanup: removed {removed}, kept {len(kept)}')
```

**Expected outcome:** After Steps 5, 5b, and 5c, `lessons.jsonl` should contain only lessons with meaningful signal types (e.g., `execution_error`, `escalation`, `failure_keyword`, `platform_failure`, `tier2_open`, `failure`, `finch_actionable_email`). Count should stabilize around 15-20.

**Why this matters:** Without Step 5b, malformed lessons with empty `signal_type` accumulate and eventually produce shifts with `signal_type: "unknown"` — polluting the active shift list. Noise signal types like `low_coverage` and `gap_detected` produce semantically meaningless shifts that waste cap space.

## Step 5c: Stale-History Lesson Purge (MANDATORY — 2026-06-28)

The production script's Bug #2 (full-history lesson extraction) produces `confidence: high` lessons with event counts far exceeding what the current ingest could have produced. After Steps 5 and 5b, run this third pass:

```python
import json, os

DATA_DIR = '/root/.hermes/profiles/indigo/commons/data/ocas-praxis'
LESSONS_FILE = os.path.join(DATA_DIR, 'lessons.jsonl')

 ingested_events_count = 3  # from this run's ingest — adjust accordingly
# Any lesson with event_count > ingested_events_count * 2 must be from history backfill

kept = []
removed = 0
with open(LESSONS_FILE) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        les = json.loads(line)
        ec = les.get('event_count', 0)
        # If event count is impossibly high for this run's ingest, it's stale history
        if ec > max(ingested_events_count * 2, 5):
            removed += 1
            continue
        # Also remove domain:unknown (legacy malformed)
        if les.get('domain', '').lower() in ('unknown', ''):
            removed += 1
            continue
        kept.append(line)

with open(LESSONS_FILE, 'w') as f:
    for line in kept:
        f.write(line + '\n')

print(f'Stale-history purge: removed {removed}, kept {len(kept)}')
```

**Why this matters:** Even after noise-signal filtering (Step 5b), the full-history bug produces lessons like `failure|unknown (n=4)` or `escalation|ocas-custodian (n=18)` from events accumulated over weeks. These have valid signal types but are stale — the pattern is not active. Without this purge, they accumulate and eventually produce shifts for patterns that no longer exist. Confirmed 2026-06-28: 3 lessons with n=4-18 survived Steps 5+5b but were clearly from historical reprocessing (only 3 no_signal events were actually ingested).

## Step 6: Shift Consolidation Pass (Proactive — 2026-06-28)

After noise cleanup and decay-risk scan, check for semantically duplicate shifts sharing `(domain, failure_phase)`. Consolidating these proactively prevents mass expiry at the 14-day decay threshold and frees cap space.

**When to run:** Always. Cheap operation (reads `shifts.jsonl`, groups by key). Skip if active shifts < 5.

**Trigger:** Any group of ≥2 active shifts with the same `(domain.lower(), failure_phase.lower())` and combined `reinforcement_count ≤ 3` can be safely merged.

```python
import json, os
from collections import defaultdict
from datetime import datetime, timezone

DATA_DIR = '/root/.hermes/profiles/indigo/commons/data/ocas-praxis'
SHIFTS_FILE = os.path.join(DATA_DIR, 'shifts.jsonl')
now = datetime.now(timezone.utc)
now_iso = now.isoformat()

all_shifts = []
with open(SHIFTS_FILE) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        all_shifts.append(json.loads(line))

active = [s for s in all_shifts if s.get('status') == 'active']
groups = defaultdict(list)
for s in active:
    key = (s.get('domain', '?').lower(), s.get('failure_phase', '?').lower())
    groups[key].append(s)

expired_count = 0
for (dom, phase), shifts in groups.items():
    if len(shifts) <= 1:
        continue
    total_reinf = sum(s.get('reinforcement_count', 0) for s in shifts)
    if total_reinf > 3:
        continue  # Keep separate if collectively reinforced
    
    # Keep the one with most reinforcements
    shifts.sort(key=lambda s: s.get('reinforcement_count', 0), reverse=True)
    keeper = shifts[0]
    
    # Merge signal types
    merged_sigs = sorted(set(s.get('signal_type', '?') for s in shifts))
    prefix = '+'.join(merged_sigs[:3])
    if len(merged_sigs) > 3:
        prefix += f'+{len(merged_sigs)-3}more'
    keeper['signal_type'] = prefix
    keeper['shift_text'] = f'In {dom} during {phase}: {", ".join(merged_sigs)} patterns require monitoring.'
    keeper['last_reinforced_at'] = now_iso
    keeper['reinforcement_count'] = keeper.get('reinforcement_count', 0) + 1
    
    # Expire the rest
    for s in shifts[1:]:
        s['status'] = 'expired'
        s['expired_at'] = now_iso
        s['expire_reason'] = f'Consolidated into {keeper.get("shift_id", "?")}: same {dom}/{phase}'
        expired_count += 1

# Only rewrite if something changed
if expired_count > 0:
    with open(SHIFTS_FILE, 'w') as f:
        for s in all_shifts:
            f.write(json.dumps(s) + '\n')
    print(f'Consolidated {expired_count} shifts across {sum(1 for g in groups.values() if len(g) > 1)} groups')
```

**Result:** 9 active shifts → 3 active shifts, 0 decay-risk remaining. Confirmed 2026-06-28 cron.

## Step 7: Stale Script Cleanup

```python
import glob, os

data_dir = '/root/.hermes/profiles/indigo/commons/data/ocas-praxis'
stale_patterns = [
    'ingest_cron_*.py', 'ingest_*.py', 'scan_*.py', 'cleanup_*.py',
    'lesson_extract_*.py', 'lesson_cleanup_*.py', 'shift_cleanup_*.py',
    'shift_repair_*.py', 'debrief_*.py', 'analyze_patterns*.py',
    'post_ingest_*.py',
]
# CRITICAL: Only clean the data directory root, NOT the scripts/ subdirectory
removed = 0
for pattern in stale_patterns:
    for f in glob.glob(os.path.join(data_dir, pattern)):
        if '/scripts/' in f:
            continue
        os.remove(f)
        removed += 1
if removed:
    print(f'Cleaned {removed} stale scripts')
```

## Step 6b: Concurrent Dispatch Wave Recovery (2026-06-26)

After updating `ingest_state.json` and writing the Praxis journal, verify that a concurrent dispatch wave did NOT overwrite your state. This happens when the dispatcher triggers Forge + Mentor + Praxis in parallel with a cron-triggered Praxis run.

**Detection:** Compare `ingest_state.json:note` or `ingest_state.json:last_ingest_run` against what you just wrote. If the `note` references "dispatch wave" or "second-wave" but your run was a cron ingest, a dispatch wave ran concurrently and overwrote your state. Alternatively, check `journals_evaluated.jsonl` line count — if it jumped by 30+ entries immediately after your run, a dispatch wave appended eval entries.

**Recovery:**
1. Do NOT re-run the ingest script — the dispatch wave's scan was authoritative and covered the same journals.
2. Your Praxis journal entry (already written) serves as the audit trail for the cron run. Verify it exists in the journal directory.
3. If the dispatch wave's state update has a later `last_ingest_run` than yours, accept it — the dispatch processed at least as many journals.
4. If your cron run found events that the dispatch missed (unlikely but possible if the dispatch's mtime comparison used a future timestamp), manually append those events to `events.jsonl` and add the corresponding eval entries.
5. Log the collision in the Praxis journal with `concurrent_dispatch: true`.

**Prevention:** There is no clean prevention for this — cron runs and dispatch waves are independent triggers. The collision is inherently racy. The audit trail (both the cron journal and the dispatch journal) ensures no signals are lost.

## Step 7: Eval File Integrity Check (MANDATORY — 2026-06-26)

After all eval file writes, verify no corruption from `append_jsonl` dict-key bug:

```python
import json

EVAL_FILE = '/root/.hermes/profiles/indigo/commons/data/ocas-praxis/journals_evaluated.jsonl'
corrupted = 0
with open(EVAL_FILE) as f:
    for i, line in enumerate(f):
        line = line.strip()
        if not line: continue
        try:
            obj = json.loads(line)
            if not isinstance(obj, dict):
                corrupted += 1
                print(f'  CORRUPTED line {i+1}: {line[:50]}')
        except json.JSONDecodeError:
            corrupted += 1
            print(f'  INVALID JSON line {i+1}: {line[:50]}')

if corrupted == 0:
    print('Eval file integrity OK')
else:
    print(f'WARNING: {corrupted} corrupted entries detected')
```

This catches the `append_jsonl` dict-key corruption bug where passing a single dict instead of a list causes Python to iterate over keys, writing bare strings like `"journal_id"` instead of JSON objects.

Production scripts live in `scripts/` and must NOT be removed.

## Step 8: Inline Mtime-Based Discovery (Alternative to Production Script)

When the production script's bugs (narrow date filter, full-history lesson reprocessing, no state update) cause journal misses or excessive noise, use an inline Python script with mtime-based discovery instead. This was the production pattern on 2026-06-27 when the cron window was tight and the production script's date filter missed 50% of journals.

**When to use inline script:**
- Last ingest was <10 min ago (very few new journals expected)
- Production script reports 0 journals but you suspect new ones exist
- Production script produces >5 noise lessons from stale events
- Gap backfill needs to run with a custom mtime threshold

**Pattern:**
1. Load `last_ingest_run` from `ingest_state.json` → convert to timestamp
2. Walk BOTH journal directories (`/root/.hermes/profiles/indigo/commons/journals` and `/root/.hermes/commons/journals`)
3. For each `.json` file: check if `mtime < li_ts` AND not in `journals_evaluated.jsonl` (handle mixed formats)
4. Read each found journal, apply gotcha filters (mentor-light success, custodian observation, etc.), classify as signal or no_signal
5. Append eval entries, update state, write journal, run decay scan

**Key advantage over production script:** Mtime-based discovery finds journals regardless of which date directory they were written to. The production script's date filter (`today` + `yesterday` only) misses journals written to other date directories by forge journal-scan or dispatch waves.

See `references/session-20260627-cron-ingest-2032.md` for the full working example.
