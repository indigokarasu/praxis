# 🔄 Praxis

Praxis is the system's behavioral self-improvement loop -- it records real task outcomes, waits for patterns to emerge across multiple events, and then consolidates validated lessons into a small capped set of active behavior shifts that influence every future run. The cap of 12 active shifts is a hard constraint that prevents unbounded rule accumulation, and every shift must trace back to recorded events so nothing changes without an auditable reason.


Skill packages follow the [agentskills.io](https://agentskills.io/specification) open standard and are compatible with OpenClaw, Hermes Agent, and any agentskills.io-compliant client.

---

## Overview

Praxis answers the question of how a system gets better at its own behavior without rewriting its own identity. It records real task outcomes, waits for patterns to emerge across multiple events, and consolidates validated lessons into a small capped set of active behavior shifts that influence every future run. The cap of 12 is a hard constraint -- when full, new shifts must displace weaker ones or be rejected, preventing the kind of unbounded rule accumulation that degrades system coherence over time. Praxis also receives BehavioralSignal files from Corvus and decides independently whether to act on each one.

## Commands

| Command | Description |
|---|---|
| `praxis.event.record` | Record a completed event or outcome with evidence |
| `praxis.lesson.extract` | Derive micro-lessons from recorded events |
| `praxis.shift.propose` | Propose a new behavior shift from lessons |
| `praxis.shift.list` | List all shifts with status |
| `praxis.shift.activate` | Activate a proposed shift (enforces cap) |
| `praxis.shift.expire` | Expire or reject a shift with reason |
| `praxis.runtime.brief` | Generate runtime brief with active shifts only |
| `praxis.debrief.generate` | Produce a plain-language debrief |
| `praxis.status` | Event count, active shifts, cap usage, last debrief |
| `praxis.journal` | Write journal for the current run |
| `praxis.update` | Pull latest from GitHub source (preserves journals and data) |

## Setup

`praxis.init` runs automatically on first invocation and creates all required directories, config.json, and JSONL files. It also registers the `praxis:journal-scan` heartbeat entry to process incoming BehavioralSignal files from Corvus and `praxis:update` (midnight daily, self-update). No manual setup is required.

## Dependencies

**OCAS Skills**
- [Corvus](https://github.com/indigokarasu/corvus) -- sends BehavioralSignal files via Praxis journal payload
- [Dispatch](https://github.com/indigokarasu/dispatch) -- receives action decisions for communication execution

**External**
- None

## Scheduled Tasks

| Job | Mechanism | Schedule | Command |
|---|---|---|---|
| `praxis:journal-scan` | heartbeat | Every heartbeat pass | Scan Corvus journals for BehavioralSignal payloads (via journal payload) |
| `praxis:update` | cron | `0 0 * * *` (midnight daily) | Self-update from GitHub source |

## Changelog


### v2.6.5 — April 26, 2026
- Version alignment per spec-ocas-skill-publishing.md (no functional change)
### v2.5.0 -- April 2, 2026
- Structured entity observations in journal payloads (`entities_observed`, `relationships_observed`, `preferences_observed`)
- `user_relevance` tagging on journal observations (default `agent_only` for behavioral patterns, `user` for user-preference lessons)
- Elephas journal cooperation in skill cooperation section

### v2.3.0 -- March 27, 2026
- Added `praxis.update` command and midnight cron for automatic version-checked self-updates

### v2.2.0 -- March 22, 2026
- Routing improvements

### v2.1.0 -- March 22, 2026
- Run completion protocols and journal operations
- Heartbeat registration for Corvus journal signal payloads

### v2.0.0 -- March 18, 2026
- Initial release as part of the unified OCAS skill suite
---

*Praxis is part of the [OCAS Agent Suite](https://github.com/indigokarasu) -- a collection of interconnected skills for personal intelligence, autonomous research, and continuous self-improvement. Each skill owns a narrow responsibility and communicates with others through structured signal files, shared journals, and Chronicle, a long-term knowledge graph that accumulates verified facts over time.*
