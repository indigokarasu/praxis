# Praxis Support File Map

| File | When to read |
|------|-------------|
| `references/cron-execution-checklist.md` | After running production script in cron mode — state update, gap backfill, journal write, decay scan, stale script cleanup |
| `references/data_model.md` | Before creating events, lessons, shifts; for schemas and storage layout |
| `references/okrs-praxis.md` | During OKR evaluation |
| `references/ingest-script-pattern.md` | Before writing ingest scripts; production-proven Python pattern for scan/dedup/extract/shift-activate workflow |
| `references/dispatch-quick-path.md` | **Read when triggered by dispatcher** — 5-line quick path for routine `new_files` that are all no-signal (80% of dispatches). Only use full template for journals with errors/escalations. |
| `references/journal_ingestion.md` | Before scanning skill journals; signal extraction rules |
| `references/gotchas-praxis.md` | Before any Praxis operation; full gotcha catalog |
| `references/mentor-light-noise-filters.md` | During journal ingest — mandatory filters for mentor-light false positives |
| `references/recurring-noise-lesson-cleanup.md` | After every cron ingest — mandatory cleanup of low-confidence noise lessons |
| `references/shift-cap-repair.md` | When active shifts exceed cap: repair procedure, curated rebuild, prevention patterns |
| `references/storage-layout-praxis.md` | During initialization or path resolution |
| `references/self-update-praxis.md` | Before running praxis.update |
| `references/inline-examples.md` | Before writing/repairing `ingest_state.json` (bootstrap vs null/empty-string fix), Bug 2 noise-lesson cleanup, or lesson dedup — holds the exact code snippets extracted from SKILL.md |
| `templates/dispatch_ingest_template.py` | Copy-and-adapt template for dispatch-triggered Praxis ingest |

## Session Notes (historical reference)

| File | When to read |
|------|-------------|
| `references/session-20260629-dispatch-1221Z.md` | Dispatch with gap_backfill.py path fix + concurrent cron gap pattern |
| `references/session-20260629-dispatch-1240Z-praxis.md` | **Massive legacy eval backfill** — 12,087 journals backfilled in one dispatch. One-time catchup pattern. |
| `references/session-20260629-cron-ingest-0207.md` | 5,817 gap backfill catchup, 14 noise lessons cleaned |
| `references/session-20260629-cron-ingest-0308.md` | Phantom gap journal detected (os.walk race), 14 Bug-2 noise lessons cleaned |
| `references/session-20260629-cron-ingest-1231.md` | 13 Bug-2 noise lessons with MISSING signal_type key — cleanup filter bug discovered and fixed |
| `references/session-20260701-cron-ingest-0735Z.md` | **Cron ingest 2026-07-01:** `last_lesson_extraction_event_id: ""` (empty string) is as broken as `null`. Phantom finch journal produced unverifiable event. Fast pre-filter vs per-lesson comparison. |
| `references/session-20260707-cron-ingest-0205z.md` | **Steady-state confirmation:** All 4 production bugs active but mitigated. Fast pre-filter (3rd validation), noise cleanup fix works (missing signal_type), decay check uses last_reinforced_at correctly. 3/12 active shifts stable. |

For other session-specific gotchas and incident reports, see `references/session_*.md` files. Read only when debugging a specific past issue mentioned in those sessions.

## Additional files

| File | Notes |
|------|-------|
| `references/debrief_templates.md` | Praxis Debrief Templates |
| `references/finch_journal_schema.md` | Finch Journal Schema Reference |
| `references/gotcha_cross_skill_corroboration.md` | Gotcha: Cross-Skill Corroboration Signals |
| `references/gotcha_custodian_findings_schema.md` | Gotcha: Custodian Findings Schema |
| `references/gotcha_escalation_fingerprint.md` | Escalation Fingerprint Enrichment |
| `references/gotcha_evidence_field_schema.md` | Gotcha: Evidence Field Schema Variance in Events |
| `references/gotcha_oauth_corruption.md` | Gotcha: OAuth Token Corruption from Disk-Full (ENOSPC) |
| `references/gotcha_unknown_signal_type.md` | Gotcha: Unknown Signal Type Filter |
| `references/journal.md` | Journal |
| `references/journal_sources.md` | Praxis Journal Sources |
| `references/praxis-cron-journal-template.md` | Praxis Cron Journal Template |
| `references/praxis-ingest-directory-filter.md` | Praxis Ingest Script Directory Filter |
| `references/runtime_rules.md` | Praxis Runtime Rules |
| `references/scripts.md` | Praxis Scripts |
| `references/self-update.md` | Praxis Self-Update Procedure |
| `references/session-20260620-dispatch.md` | Session 2026-06-20 Dispatch |
| `references/session-20260621-cron-ingest-1912.md` | Session 2026-06-21 Cron Ingest @ 19:12Z |
| `references/session-20260621-dispatch-10.md` | Session 2026-06-21 — Dispatch #10 (14:35Z) |
| `references/session-20260621-dispatch-12.md` | Session 2026-06-21 — Dispatch (12:05Z) |
| `references/session-20260621-dispatch-13.md` | Session 2026-06-21 Dispatch (13:13Z) — Multi-Skill Dispatch, Template Fix |
| `references/session-20260621-dispatch-16.md` | Session 2026-06-21 (Dispatch 16) — Future-Dated Ingest State |
| `references/session-20260621-dispatch-18.md` | Session 2026-06-21 (Dispatch 18) — Dispatch Re-Detection + Production Script Additive Scan |
| `references/session-20260621-dispatch-2.md` | Session 2026-06-21 (Second) — Praxis Dispatch Ingest (Multi-Skill Dispatch) |
| `references/session-20260621-dispatch-20.md` | Session 2026-06-21 Dispatch #20 — Second-Wave Pattern Confirmed |
| `references/session-20260621-dispatch-3.md` | Session 2026-06-21 (Third) — Praxis Dispatch Ingest (Multi-Skill Dispatch) |
| `references/session-20260621-dispatch-4.md` | Session 2026-06-21 Dispatch Ingest (05:10Z dispatch trigger) |
| `references/session-20260621-dispatch-6.md` | Session 2026-06-21 Dispatch (05:55Z) — Multi-Skill Dispatch, All Pipelines Clean |
| `references/session-20260621-dispatch-7.md` | Praxis Dispatch Ingest — 2026-06-21 |
| `references/session-20260621-dispatch-8.md` | Session: 2026-06-21 Dispatch Ingest (Dispatch #8) |
| `references/session-20260621-dispatch.md` | Session 2026-06-21 — Praxis Dispatch Ingest (Multi-Skill Dispatch) |
| `references/session-20260621-dual-journal-fix.md` | Session 2026-06-21: Dual-Journal Directory Scan Fix |
| `references/session-20260622-cron-ingest-0322.md` | Session 2026-06-22: Cron Ingest @ 03:22Z |
| `references/session-20260622-cron-ingest-1108.md` | Praxis Cron Ingest — 2026-06-22 @ 11:08Z |
| `references/session-20260622-dispatch-2.md` | Praxis Dispatch Ingest — 2026-06-22 (Dispatch #18) |
| `references/session-20260622-dispatch-20.md` | Session 2026-06-22 — Praxis Dispatch Ingest (Dispatch #20) |
| `references/session-20260622-dispatch-21.md` | Session 2026-06-22 — Dispatch #21 (Second-Wave Handling) |
| `references/session-20260622-dispatch-22.md` | Session 2026-06-22 — Dispatch #22 (Forge + Mentor + Praxis) |
| `references/session-20260622-dispatch-23.md` | Praxis Dispatch Ingest — 2026-06-22 (Dispatch #23) |
| `references/session-20260622-dispatch-24.md` | Praxis Dispatch Ingest — 2026-06-22 (Dispatch #24) |
| `references/session-20260622-dispatch-25-praxis.md` | Session 2026-06-22 Dispatch #25 — Praxis Ingest |
| `references/session-20260622-dispatch-3.md` | Praxis Dispatch Ingest — 2026-06-22 (Third Dispatch) |
| `references/session-20260622-dispatch-praxis-22.md` | Session 2026-06-22 — Praxis Dispatch Ingest #22 (10:30Z) |
| `references/session-20260622-dispatch-praxis.md` | Session 2026-06-22 — Praxis Dispatch Ingest (Third-Wave Closure) |
| `references/session-20260622-dispatch.md` | Praxis Dispatch Ingest — 2026-06-22 |
| `references/session-20260622-praxis-dispatch.md` | Session 2026-06-22 Praxis Dispatch |
| `references/session-20260623-cron-ingest.md` | Cron Ingest — 2026-06-23T20:45Z |
| `references/session-20260623-dispatch-27-praxis.md` | Dispatch #27 — Praxis Component (2026-06-23) |
| `references/session-20260623-dispatch-28-praxis.md` | Dispatch #28 — Praxis Component (2026-06-23) |
| `references/session-20260623-dispatch-29-praxis.md` | Dispatch #29 — Praxis Component (2026-06-23) |
| `references/session-20260623-dispatch-30-praxis.md` | Dispatch #30 — Praxis Component (2026-06-23) |
| `references/session-20260623-dispatch-32-praxis.md` | Dispatch #32 — Praxis Component (2026-06-23) |
| `references/session-20260623-dispatch-praxis.md` | Dispatch #26 — Praxis Component (2026-06-23) |
| `references/session-20260624-debrief-notes.md` | Praxis Debrief — Session Notes (2026-06-24) |
| `references/session-20260624-dispatch-31-praxis.md` | Dispatch #31 — Praxis Component (2026-06-24) |
| `references/session-20260624-dispatch-33-praxis.md` | Dispatch #33 — Praxis Component (2026-06-24) |
| `references/session-20260624-dispatch-37-praxis.md` | Dispatch #37 — 2026-06-24T02:22Z (Multi-skill: Forge + Mentor + Praxis) |
| `references/session-20260624-dispatch-42.md` | Dispatch #42 — 2026-06-24T06:24Z (Praxis) |
| `references/session-20260624-dispatch-45-praxis.md` | Dispatch #45 — 2026-06-24T12:32Z (Praxis: second-wave skip + third-wave mitigation) |
| `references/session-20260624-dispatch-46-praxis.md` | Dispatch #46 — 2026-06-24T14:45Z (Praxis — Quick Path) |
| `references/session-20260624-dispatch-47-praxis.md` | Dispatch #47 — 2026-06-24T15:28Z (Praxis Ingest) |
| `references/session-20260624-dispatch-485-praxis.md` | Dispatch #485 — 2026-06-24T175558Z (Praxis Ingest) |
| `references/session-20260624-dispatch-49-praxis.md` | Dispatch #49 — 2026-06-24T19:28Z (Praxis in Multi-Skill Dispatch) |
| `references/session-20260624-dispatch-50-praxis.md` | Dispatch #50 — 2026-06-24T19:42Z (Praxis in Multi-Skill Dispatch) |
| `references/session-20260624-dispatch-51-praxis.md` | Dispatch #51 — 2026-06-24T19:58Z (Praxis in Multi-Skill Dispatch) |
| `references/session-20260625-cron-ingest-1535.md` | 2026-06-25 Cron Ingest (15:35Z) |
| `references/session-20260625-cron-ingest.md` | 2026-06-25 Cron Ingest |
| `references/session-20260625-dispatch-059-praxis.md` | Praxis — Dispatch #59 (2026-06-25T01:36Z) |
| `references/session-20260625-dispatch-060-praxis.md` | Praxis — Dispatch #60 (2026-06-25T02:08Z) |
| `references/session-20260625-dispatch-061-praxis.md` | Praxis — Dispatch #61 (2026-06-25T02:26Z) |
| `references/session-20260625-dispatch-063-praxis.md` | Dispatch #63 — 2026-06-25T02:49Z (Praxis) |
| `references/session-20260625-dispatch-067-praxis.md` | Dispatch #67 — Praxis Cross-Skill Mitigation (2026-06-25T03:50Z) |
| `references/session-20260625-dispatch-068-praxis.md` | Dispatch #68 — Praxis Journal Ingest (2026-06-25) |
| `references/session-20260625-dispatch-074-praxis.md` | Dispatch #74 — 2026-06-25T05:25Z |
| `references/session-20260625-dispatch-078-praxis.md` | Dispatch #78 — Praxis Journal Ingest (2026-06-25) |
| `references/session-20260625-dispatch-079-praxis.md` | Dispatch #79 — Praxis Journal Ingest (2026-06-25) |
| `references/session-20260625-dispatch-080-praxis.md` | Dispatch #80 — Praxis (2026-06-25T06:22Z) |
| `references/session-20260625-dispatch-085-praxis.md` | Dispatch #85 (2026-06-25):** Steady-state multi-skill dispatch, Praxis pipeline. |
| `references/session-20260625-dispatch-096-praxis.md` | Dispatch #96 — Praxis Journal Ingest (2026-06-25) |
| `references/session-20260625-dispatch-105-praxis.md` | Dispatch #105 — Praxis Journal Ingest (2026-06-25) |
| `references/session-20260625-dispatch-130-praxis.md` | Dispatch #130 (2026-06-25T21:38Z) — Praxis Journal Ingest |
| `references/session-20260625-dispatch-2157-praxis.md` | Dispatch ~#133 (2026-06-25T22:09Z) — Multi-Skill No-Op Ingest |
| `references/session-20260625-dispatch-57-praxis.md` | Praxis — Dispatch #57 (2026-06-25) |
| `references/session-20260625-dispatch-59-praxis.md` | Praxis — Dispatch #59 (2026-06-25T01:53Z) |
| `references/session-20260626-cron-ingest-1203.md` | Session 2026-06-26 Cron Ingest (12:03Z) |
| `references/session-20260626-cron-ingest-1538.md` | Cron Ingest Session — 2026-06-26 15:38Z |
| `references/session-20260626-cron-ingest-1722.md` | Cron Ingest Session — 2026-06-26T17:22Z |
| `references/session-20260626-cron-ingest.md` | Session 2026-06-26 Cron Ingest (03:11Z) |
| `references/session-20260626-debrief.md` | 2026-06-26 Praxis Debrief |
| `references/session-20260626-dispatch-141-praxis.md` | Session 2026-06-26 Dispatch #141 — Cron Journal Detected as New File |
| `references/session-20260626-dispatch-144-praxis.md` | Session 2026-06-26 Dispatch #144 — Dispatch-Output Eval Gap (Second-Wave) |
| `references/session-20260626-dispatch-147-praxis.md` | Session 2026-06-26 Dispatch #147 — Second-Wave, All Pipelines Clean |
| `references/session-20260626-dispatch-157-praxis.md` | Dispatch #157 (2026-06-26T09:35Z) — Genuine Dispatch with Eval Gap Backfill |
| `references/session-20260626-dispatch-160-praxis.md` | Dispatch #160 (2026-06-26T10:21Z) — Genuine Dispatch + Massive Legacy Backfill |
| `references/session-20260626-dispatch-gap-backfill.md` | Session 2026-06-26 Dispatch Gap Backfill (04:03Z) |
| `references/session-20260627-cron-ingest-1532.md` | Cron Ingest Session — 2026-06-27 15:32Z |
| `references/session-20260627-dispatch-1249-praxis.md` | Dispatch 2026-06-27T12:49Z — Eval Gap Ingest |
| `references/session-20260627-dispatch-1424Z-praxis.md` | Dispatch ~#1424 (2026-06-27T14:24Z): Praxis Eval Gap Registration — Genuine No-Op |
| `references/session-20260628-cron-ingest-1006.md` | Session: Cron Ingest 2026-06-28T10:06Z — Shift Consolidation Proactive Pass |
| `references/session-20260628-cron-ingest-1833.md` | Cron Ingest Session — 2026-06-28T18:33Z |
| `references/session-20260628-cron-ingest-1937.md` | Session 2026-06-28 — Cron Ingest 19:37Z (Bug 2 Cleanup Scope Expansion) |
| `references/session-20260628-dispatch-2230Z-praxis.md` | Dispatch 2026-06-28T22:30Z — Praxis Pipeline |
| `references/session-20260629-debrief-0603.md` | Session: Praxis Debrief — 2026-06-29 06:03 UTC |
| `references/session-20260630-dispatch-0642Z-praxis.md` | Dispatch 2026-06-30T06:42Z — Praxis Pipeline |
| `references/session-20260630-dispatch-0934Z-praxis.md` | Dispatch 2026-06-30T09:34Z (ocas-praxis) |
| `references/session-20260706-cron-dispatch-skill-updates.md` | Skill Library Updates — 2026-07-06 Cron Dispatch Session |
| `references/session-20260707-cron-ingest-0057Z.md` | Cron Ingest 2026-07-07T00:57Z — Routine Steady-State |
| `references/session-notes.md` | Praxis — Session Notes Reference |
| `references/session_20260530_ingest.md` | Praxis Ingest Run — 2026-05-30T19:50Z |
| `references/session_20260530_ingest2.md` | Session 2026-05-30 (Second Pass) — Journal Ingest Findings |
| `references/session_20260530_ingest3.md` | Praxis Ingest Run — 2026-05-30T22:23Z (Third Pass) |
| `references/session_20260530_ingest4.md` | Session 2026-05-30 Ingest #4 |
| `references/session_20260530_review.md` | Praxis Review Pass — 2026-05-30 |
| `references/session_20260531_ingest.md` | Session 2026-05-31 Ingest — Cron Journal Ingest |
| `references/session_20260531_ingest11.md` | Session: 2026-05-31 Ingest 11 (Journal Ingest) |
| `references/session_20260531_ingest12.md` | Session: 2026-05-31 Ingest Run (journal_ingest #12) |
| `references/session_20260531_ingest13.md` | Session: 2026-05-31 Ingest Run (journal_ingest #13) |
| `references/session_20260531_ingest14.md` | Session: 2026-05-31 Ingest Run (journal_ingest #14) |
| `references/session_20260531_ingest15.md` | Praxis Ingest — 2026-05-31 22:20 UTC (ingest15) |
| `references/session_20260531_ingest2.md` | Praxis Journal Ingest — 2026-05-31 01:24 UTC (Run 2) |
| `references/session_20260531_ingest3.md` | Praxis Journal Ingest — 2026-05-31 02:18 UTC (Run 3) |
| `references/session_20260531_ingest4.md` | Praxis Journal Ingest — 2026-05-31 07:30 PT |
| `references/session_20260531_ingest5.md` | Session: 2026-05-31 Praxis Journal Ingest (cron) |
| `references/session_20260531_ingest6.md` | Session: 2026-05-31 Praxis Journal Ingest (cron, 6th run) |
| `references/session_20260531_ingest7.md` | Session: 2026-05-31 Ingest Run (journal_ingest #7) |
| `references/session_20260531_ingest9.md` | Session: 2026-05-31 Ingest Run (journal_ingest #9) |
| `references/session_20260601_ingest1.md` | Session Note: 2026-06-01 Journal Ingest (ocas-praxis cron) |
| `references/session_20260601_ingest2.md` | Session Note: 2026-06-01 Journal Ingest #2 (ocas-praxis cron) |
| `references/session_20260604_ingest1.md` | Praxis Ingest Session — 2026-06-04 |
| `references/session_20260604_ingest2.md` | Session Note — 2026-06-04 Ingest Cycle 9 (Cron) |
| `references/session_20260604_ingest3.md` | Session Note — 2026-06-04 Ingest Cycle 10 (Cron) |
| `references/session_20260605_ingest1.md` | Session 2026-06-05 — Praxis Ingest Run 1 |
| `references/session_20260606_ingest1.md` | Session 2026-06-06 — Praxis Journal Ingest (cron) |
| `references/session_20260606_ingest2.md` | Session 2026-06-06 Ingest #2 — Cron Journal Ingest |
| `references/session_20260607_ingest1.md` | Session 2026-06-07 Praxis Ingest — Journal Scan Findings |
| `references/session_20260607_ingest2.md` | Session 2026-06-07 — Praxis Journal Ingest (Cron) |
| `references/session_20260607_ingest3.md` | Session 2026-06-07 Ingest Run 3 (Cron) |
| `references/session_20260612_ingest.md` | Session 2026-06-12 — Praxis Journal Ingest (Primary + Supplemental) |
| `references/session_20260612_ingest2.md` | Session 2026-06-12 — Praxis Journal Ingest (Second Run) |
| `references/session_20260612_ingest3.md` | Session 2026-06-12 — Praxis Journal Ingest (Third Run, Cron) |
| `references/session_20260612_ingest4.md` | Session 2026-06-12 — Praxis Journal Ingest (Fourth Run, Cron) |
| `references/session_20260612_ingest5.md` | Session: 2026-06-12 Praxis Ingest (cron) |
| `references/session_20260612_ingest_cron.md` | Session: 2026-06-12 Praxis Journal Ingest (Cron) |
| `references/session_20260613_ingest1.md` | Session 2026-06-13 — Praxis Journal Ingest 1 |
| `references/session_20260613_ingest_cron.md` | Session 2026-06-13 Praxis Ingest (Cron) |
| `references/session_20260613_ingest_cron10.md` | Session: 2026-06-13 Ingest Cron (10th run) |
| `references/session_20260613_ingest_cron11.md` | Session 2026-06-13 Ingest Cron #11 |
| `references/session_20260613_ingest_cron12.md` | Praxis Ingest — 2026-06-13 Cron Run (12th of day) |
| `references/session_20260613_ingest_cron2.md` | Praxis Ingest Session Notes — 2026-06-13 (Cron #2) |
| `references/session_20260613_ingest_cron3.md` | Praxis Ingest — 2026-06-13 Cron Run 3 (Steady-State) |
| `references/session_20260613_ingest_cron4.md` | Session: 2026-06-13 Ingest Cron (4th run) |
| `references/session_20260613_ingest_cron5.md` | Session: 2026-06-13 Praxis Ingest (cron) |
| `references/session_20260613_ingest_cron6.md` | Session: 2026-06-13 Ingest Cron (6th run) |
| `references/session_20260613_ingest_cron7.md` | Session: 2026-06-13 Ingest Cron (7th run) |
| `references/session_20260613_ingest_cron8.md` | Session: 2026-06-13 Ingest Cron (8th run) |
| `references/session_20260613_ingest_cron9.md` | Session: 2026-06-13 Ingest Cron (9th run) |
| `references/session_20260613_ingest_recovery.md` | Session 2026-06-13 — Ingest Cron Recovery |
| `references/session_20260614_debrief.md` | Praxis Session — 2026-06-14 Debrief Cron |
| `references/session_20260614_ingest_cron.md` | Session Note: 2026-06-14 Ingest Run |
| `references/session_20260614_ingest_cron23.md` | Session: 2026-06-14 23:36 UTC — Praxis Cron Ingest |
| `references/session_20260615_fullscan.md` | 2026-06-15 Full Journal Ingest |
| `references/session_20260615_ingest.md` | Session Note: 2026-06-15 Ingest Run |
| `references/session_20260615_ingest_cron.md` | 2026-06-15 Cron Ingest — Full Scan Validates Date-Window Fix |
| `references/session_20260616_gotchas.md` | Session 2026-06-16 Ingest — New Gotchas |
| `references/session_20260616_ingest.md` | 2026-06-16 Praxis Journal Ingest |
| `references/session_20260616_ingest_cron.md` | 2026-06-16 Praxis Journal Ingest (Cron Run) |
| `references/session_20260616_ingest_cron_afternoon.md` | 2026-06-16 Praxis Journal Ingest — Afternoon Cron Run |
| `references/session_20260616_ingest_cron_praxis.md` | 2026-06-16 Praxis Journal Ingest (Cron Run — praxis:journal_ingest) |
| `references/session_20260616_ingest_cron_praxis_v2.md` | 2026-06-16 Praxis Journal Ingest (Cron Run — praxis:journal_ingest v2) |
| `references/session_20260616_ingest_cron_praxis_v3.md` | 2026-06-16 Praxis Journal Ingest — 18:26 UTC Cron Run (v3) |
| `references/session_20260616_ingest_cron_praxis_v5.md` | Session 2026-06-16 Praxis Ingest Cron v5 |
| `references/session_20260616_ingest_v9_v10.md` | Session 2026-06-16 Praxis Ingest v9/v10 — Cap Enforcement Bug & Lesson Null-Phase Filter |
| `references/session_20260617_ingest.md` | Session 2026-06-17: Praxis Journal Ingest — Complete Loop Run |
| `references/session_20260617_ingest_cron_c.md` | Session: 2026-06-17 Cron Ingest C |
| `references/session_20260618_ingest_cron_c.md` | 2026-06-18 Praxis Journal Ingest (Cron Run C) |
| `references/session_20260618_ingest_cron_g.md` | Session 2026-06-18: Journal Ingest Cron |
| `references/session_20260618_ingest_cron_l.md` | 2026-06-18 Praxis Journal Ingest (Cron Run L) |
| `references/session_20260618_ingest_cron_m.md` | Session: 2026-06-18 Cron Ingest (Batch M) |
| `references/session_20260618_ingest_cron_o.md` | 2026-06-18 Praxis Journal Ingest (Cron Run O) |
| `references/session_20260618_ingest_cron_p.md` | Praxis — Session 2026-06-18 Ingest (Cron Run P) |
| `references/session_20260618_ingest_cron_v.md` | Session 2026-06-18 Cron Ingest V |
| `references/session_20260618_ingest_s.md` | Session 2026-06-18: Praxis Journal Ingest — Cron Run S |
| `references/session_20260618_ingest_u.md` | Session: 2026-06-18 Praxis Journal Ingest (Cron U) |
| `references/session_20260619_ingest.md` | Session 2026-06-19: Praxis Journal Ingest + Shift/Lesson Cleanup |
| `references/session_20260619_ingest_cron_b.md` | 2026-06-19 Cron Ingest (Second Run) |
| `references/session_20260620_ingest_b.md` | Session 2026-06-20 Ingest Cron B — Findings |
| `references/session_20260621_ingest.md` | Session 2026-06-21 — Praxis Journal Ingest |
| `references/session_20260621_ingest_cron.md` | Session 2026-06-21 Praxis Cron Ingest |
| `references/session_20260621_ingest_cron_0910.md` | Session 2026-06-21 — Praxis Cron Ingest (09:10 UTC) |
| `references/session_20260622_ingest.md` | Session 2026-06-22 — Praxis Journal Ingest |
| `references/session_20260622_ingest_1435.md` | Session: 2026-06-22 Cron Ingest 14:35Z |
| `references/session_20260622_ingest_cron_0805.md` | Session 2026-06-22 Cron Ingest @ 08:05Z |
| `references/session_20260622_ingest_cron_c.md` | Session 2026-06-22 Cron Ingest C — Findings |
| `references/session_20260625_ingest.md` | Praxis Ingest — 2026-06-25 Session Notes |
| `references/supplemental-ingest-after-dispatch.md` | Supplemental Ingest After Dispatch |
| `scripts/shift_cleanup_20260617.py` | Shift cleanup — expire malformed shifts, merge overlaps, enforce cap. Run after ingest to fix data quality ... |
