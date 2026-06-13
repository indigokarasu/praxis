#!/usr/bin/env python3
"""Praxis journal ingest scanner - finds unevaluated journal files."""
import os
import json

JOURNALS_DIR = "/root/.hermes/commons/journals"
EVAL_FILE = "/root/.hermes/commons/data/ocas-praxis/journals_evaluated.jsonl"
SKIP_DIRS = {"ocas-praxis", "ocas-lucid"}

today = "2026-06-09"
yesterday = "2026-06-08"

# Step 1: Deduplicate journals_evaluated.jsonl
eval_entries = []
seen_ids = set()
if os.path.exists(EVAL_FILE):
    with open(EVAL_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                jid = entry.get("journal_id", "")
                if jid not in seen_ids:
                    seen_ids.add(jid)
                    eval_entries.append(entry)
            except json.JSONDecodeError:
                continue

# Write deduped eval file
with open(EVAL_FILE, 'w') as f:
    for e in eval_entries:
        f.write(json.dumps(e) + "\n")

print(f"Evaluated entries after dedup: {len(eval_entries)}")

# Step 2: Scan filesystem for journal files
all_files = []
for root_dir, dirs, files in os.walk(JOURNALS_DIR):
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    parts = root_dir.replace(JOURNALS_DIR, "").strip('/').split('/')
    if parts and parts[0] in SKIP_DIRS:
        continue
    for fname in files:
        if fname.endswith('.json'):
            full_path = os.path.join(root_dir, fname)
            rel_path = os.path.relpath(full_path, JOURNALS_DIR)
            path_parts = rel_path.split('/')
            if len(path_parts) >= 3:
                date_dir = path_parts[1]
                if date_dir in (today, yesterday):
                    skill = path_parts[0]
                    canonical = f"{skill}/{date_dir}/{fname}"
                    all_files.append((canonical, full_path))

print(f"Total journal files for {today} + {yesterday}: {len(all_files)}")

# Step 3: Compute unevaluated set
unevaluated = [(c, p) for c, p in all_files if c not in seen_ids and os.path.exists(p)]
print(f"Unevaluated journals: {len(unevaluated)}")

# List them with file sizes
for c, p in unevaluated:
    size = os.path.getsize(p)
    print(f"  [{size:>6}B] {c}")
