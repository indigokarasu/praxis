# ⚙️ Praxis

  <img src="./assets/readme/hero.jpg" width="100%" alt="Praxis">

Bounded behavioral refinement loop. Records outcomes, extracts micro-lessons from repeated patterns, consolidates them into capped active behavior shifts, applies shifts at runtime, and generates plain-language debriefs. Use for recording task outcomes, extracting lessons from repeated patterns, managing active behavior shifts, generating runtime briefs, or producing debriefs. Not for: general memory (use Chronicle), preference tracking (use Taste), real-time task execution, content generation, system health monitoring (use Custodian), or skill evaluation scoring (use Mentor).

**Skill name:** `ocas-praxis`
**Version:** 3.2.4
**Type:** 
**Layer:** productivity
**Author:** Indigo Karasu

---

## 📖 Overview

Bounded behavioral refinement loop. Records outcomes, extracts micro-lessons from repeated patterns, consolidates them into capped active behavior shifts, applies shifts at runtime, and generates plain-language debriefs. Use for recording task outcomes, extracting lessons from repeated patterns, managing active behavior shifts, generating runtime briefs, or producing debriefs. Not for: general memory (use Chronicle), preference tracking (use Taste), real-time task execution, content generation, system health monitoring (use Custodian), or skill evaluation scoring (use Mentor).

---

## 🔧 Capabilities

- `praxis.event.record` — record a completed event or outcome with evidence
- `praxis.lesson.extract` — derive micro-lessons from recorded events
- `praxis.shift.propose` — propose a new behavior shift from lessons
- `praxis.shift.list` — list all shifts with status
- `praxis.shift.activate` — activate a proposed shift (enforces cap)
- `praxis.shift.expire` — expire or reject a shift with reason
- `praxis.runtime.brief` — generate runtime brief with active shifts only
- `praxis.debrief.generate` — produce a plain-language debrief
- `praxis.status` — event count, active shifts, cap usage, last debrief
- `praxis.journal` — write journal for the current run; called at end of every run
- `praxis.update` — pull latest from GitHub source; journals and data preserved
- `journals_evaluated.jsonl` — append-only log of all evaluated journals
- `ingest_state.json` — `last_ingest_run` timestamp and counters
- `execute_code` is blocked in cron mode — use `terminal()` with scripts written via `write_file()`
- **`finch_actionable_email` is a legitimate signal type — NOT noise** — Finch scan journals produce `actionable` email counts when new emails require attention (job opportunities, application updates, etc.). This is a genuine positive signal, not a no-op. **Do NOT add `finch_actionable_email` to `NOISE_SIGNAL_TYPES`.** The signal should produce events and, when ≥2 events accumulate, lessons. The only filter: if `actionable == 0`, skip (no new emails to act on). Discovered 2026-06-20: 12 finch_actionable_email events from 10 scans produced the first finch lesson.
- **`patch` corrupts multi-line JSON replacements in `ingest_state.json` (2026-07-01)** — The `patch` tool's fuzzy matching can mangle JSON structure when replacing multi-line blocks. During this cron ingest, a `patch` call targeting lines 50-52 of `ingest_state.json` successfully replaced the targeted fields but **dropped the `stale_script_cleanup` sub-object that immediately followed**, producing invalid JSON that wouldn't parse. Root cause: fuzzy matching matched and replaced a block boundary that included context from the next object, and the `new_string` didn't re-declare it. **Fix:** For multi-line edits to `ingest_state.json` (or any nested JSON state file), prefer full file rewrite via `write_file()` over `patch()`. If `patch` must be used, ensure the `old_string` includes ALL content between the target lines and the start of the next top-level key — or better, verify JSON validity with `python3 -c "import json; json.load(open(...))"` immediately after applying. Confirmed 2026-07-01: 2-step patch (journal path + decay timestamp) broke the file; had to recover via full `write_file` rewrite.
- **`ingest_state.json` has two gap-backfill counters — read `eval_gaps_backfilled`, not `gaps_backfilled`** — After `gap_backfill.py` runs, its stdout prints `gaps_backfilled=N`, but the field it actually writes is `eval_gaps_backfilled`. The separate `gaps_backfilled` key is a stale duplicate that stays at `0` and is NOT updated by the script. When you read state and see `gaps_backfilled: 0` immediately after a backfill that printed `gaps_backfilled=26`, that is NOT corruption — `eval_gaps_backfilled` holds the real cumulative count. Always read `eval_gaps_backfilled` for the authoritative backfill total; treat the bare `gaps_backfilled` key as dead. Confirmed 2026-07-07: gap_backfill printed `gaps_backfilled=26`; on-disk `eval_gaps_backfilled` became 26 while `gaps_backfilled` stayed 0 — the discrepancy looked like state clobbering until the two-field split was identified.
- **`os.walk` can return phantom files that don't exist (2026-06-29)** — During gap backfill, `os.walk` may list files deleted by concurrent processes between the directory listing and your `os.stat()` call. Always guard with `os.path.exists(fpath)` before stat or gap classification. A phantom gap entry that can't be opened is a race artifact, not a real gap — skip silently.
- `references/praxis-ingest-cli-pitfall.md` — Before invoking `praxis_ingest_run.py` in dispatch/cron: `--help` is not guaranteed non-mutating; inspect source for interface details and treat any invocation as a real ingest with side effects.

---

## 📊 Outputs

See `SKILL.md` for outputs, journals, and persistence rules.

---

## 📄 Files

| File | Purpose |
|---|---|
| `SKILL.md` | Skill definition |
| `references/` | Supporting documentation |
| `scripts/` | Helper scripts |


## Changelog

- [2.6.5] - 2026-04-26
- Changed
- [2026-04-04] Spec Compliance Update
- Changes
- Validation
- [2.6.1] - 2026-04-08
- Storage Architecture Update
- [2.6.0] - 2026-04-08

---

## 📚 Documentation

Read `SKILL.md` for operational details, schemas, and validation rules.

Read `references/` for detailed specifications and examples.


---

## 📄 License

MIT License — see `LICENSE` for details.
