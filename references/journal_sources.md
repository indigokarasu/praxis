# Praxis Journal Sources

Skills known to produce journals that Praxis reads:

- ocas-corvus — pattern analysis and signal discovery
- ocas-spot — booking attempts, failures, bot detection outcomes
- ocas-rally — trade execution, research outcomes, healthcheck results
- ocas-taste — preference signals and recommendations
- ocas-elephas — knowledge graph ingestion events
- ocas-finch — self-improvement mining results
- ocas-fellow — experimentation outcomes
- ocas-scout — research results and OSINT findings
- ocas-bones — prediction market monitoring
- ocas-bower — Drive organization results
- ocas-vibes — writing output signals
- ocas-voyage — travel planning outcomes
- ocas-imagine — image generation results
- ocas-weave — contact graph changes
- ocas-vesper — daily briefing signals
- ocas-dispatch — communication outcomes
- ocas-mentor — skill evaluation results
- ocas-lucid — journal curation outcomes
- ocas-sands — calendar management outcomes
- ocas-sift — research synthesis results
- ocas-reach — world-data query outcomes
- ocas-inception — environment simulation results
- ocas-look — image-to-action outcomes
- ocas-multipass — delegated task outcomes
- ocas-forge — skill authoring outcomes
- ocas-haiku — Bluesky posting outcomes
- ocas-custodian — monitoring and alert outcomes

Praxis scans all skill journals at `{agent_root}/commons/journals/*/YYYY-MM-DD/` on each cron run. Praxis extracts behavioral signals (failures, corrections, successes, patterns) from journal entries and decides whether to record each as an event and extract a lesson. Praxis is not obligated to act on every journal entry. Consumed `journal_id` values are tracked in `journals_evaluated.jsonl`. Skills do not write to Praxis's directories.

See `journal_ingestion.md` for the journal schema and ingestion rules.
