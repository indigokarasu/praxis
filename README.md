# 🔄 Praxis

Bounded behavioral refinement loop with lessons, shifts, and debriefs.

**Skill name:** `ocas-praxis`
**Version:** 2.2.0
**Type:** system
**Layer:** Execution
**Author:** Indigo Karasu

---

## Files

| File | Purpose |
|---|---|
| `skill.json` | Package metadata and routing description |
| `SKILL.md` | Operational instructions for the agent |
| `references/` | Support files referenced by SKILL.md |

---

## Changelog

### 2.2.0 (2026-03-22)

- Added short-name routing aliases to skill.json description and SKILL.md frontmatter for natural invocation ('Scout', 'Sift', etc.)
- Added trigger phrases to descriptions for improved routing accuracy
- Cross-skill references in descriptions now use 'use X' format for routing clarity

### 2.1.0 (2026-03-22)

- Added Run completion section with explicit intake poll, state persistence, and journal write
- Added Initialization section with heartbeat registration
- Added Background tasks section: praxis:intake (heartbeat)
- Removed non-conformant OCAS_ROOT environment variable reference

### 2.0.0 (2026-03-18)

- Initial build of all OCAS skills as a unified suite
