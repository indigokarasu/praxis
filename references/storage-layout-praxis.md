# Praxis — Storage Layout

```
{agent_root}/commons/data/ocas-praxis/
  config.json              # ConfigBase + Praxis defaults
  events.jsonl             # Recorded behavioral events
  lessons.jsonl            # Extracted micro-lessons
  shifts.jsonl             # Active/proposed/expired behavior shifts
  debriefs.jsonl           # Generated plain-language debriefs
  decisions.jsonl          # Material decisions
  journals_evaluated.jsonl # Consumed journal tracking
  intents.jsonl            # User intents
  evidence.jsonl           # Recovery contract evidence
  evaluations/             # Evaluation data
  reports/                 # Generated reports

{agent_root}/commons/journals/ocas-praxis/
  YYYY-MM-DD/
    {run_id}.json          # One journal per run
```
