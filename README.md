# 🏛️ Praxis

> **Behavioral refinement loop — measures skill outcomes against baselines and promotes improvements.**

## Why Praxis?

Skills need feedback loops to improve. Praxis provides that by measuring actual outcomes (did the calendar event get created correctly? did the research brief answer the question?), comparing against baselines, and feeding results back into the self-improvement pipeline. It's how skills get better at what they do, not just faster.

Skill packages follow the [agentskills.io](https://agentskills.io/specification) open standard and are compatible with OpenClaw, Hermes Agent, Claude, and any agentskills.io-compliant client.

## Quick Start

```
# Check outcomes
"How did Sands perform this week?"

# Compare baselines
"Compare current Sands accuracy vs last month"
```

## What It Does

Praxis is a bounded behavioral refinement loop. It records execution outcomes, measures them against established baselines, and generates refinement signals when performance drifts or improved approaches are discovered. Results flow through journals to Corvus and Mentor for pattern analysis and improvement proposals.

## Dependencies

- All skills — reads journals for outcome data
- [Corvus](https://github.com/indigokarasu/corvus) — receives BehavioralSignal files
- [Mentor](https://github.com/indigokarasu/mentor) — receives performance data

---

*Praxis is part of the [OCAS Agent Suite](https://github.com/indigokarasu).*