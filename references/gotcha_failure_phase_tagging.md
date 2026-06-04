# Gotcha: Failure Phase Tagging

When recording corrections and failures, always tag by the task phase where the failure occurred.

## Phase Taxonomy

- **Planning** — Wrong approach, incorrect assumptions, missing prerequisites
- **Execution** — Tool call/API failure, wrong parameters, timeout
- **Response** — Correct result but wrong format, verbosity, tone

## Routing

- Planning corrections → skill preconditions/setup sections
- Execution corrections → tool-usage/gotchas sections
- Response corrections → output-formatting sections
