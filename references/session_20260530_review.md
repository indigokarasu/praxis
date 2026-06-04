# Praxis Review Pass — 2026-05-30

## Session Summary

Praxis v3.0 review pass was invoked to run `praxis_review.py --since-hours 24`. The script didn't exist. The entire pipeline was reconstructed inline and is now captured in `scripts/praxis_review.py`.

## Key Findings

### 1. `scripts/praxis_review.py` was missing
The skill manifest declared the script but it was never created. Created it from the battle-tested inline pipeline. **Lesson**: When creating skills, ensure all manifest-declared scripts are actually written.

### 2. Journal schema variance
- `summary` field can be a dict OR a string — must `isinstance`-guard
- `blockers_active` may be `None` — must type-guard before numeric comparison
- Some summary dicts use different keys (`new_tasks_added`/`tasks_resolved` vs `checked`/`successful`/`blocked`)

### 3. F-string escaping in Python scripts
Python f-strings with `\"` inside fail when passed through `terminal(command="python3 -c '...'")`. Use `.format()` instead. Write complex scripts to file first, then run.

### 4. Three proposed shifts need activation
- HTTP 429 exponential backoff for cron API calls (priority: 2)
- Orphaned cron cleanup after skill changes (priority: 3)
- MCP singleton check before starting workspace servers (priority: 6)

All have sufficient evidence (2+ events, clear causal grounding). Should be activated next session if no objections.

### 5. Shift decay status
No shifts at decay threshold. Closest: "Don't fabricate content" (12 days), "User correction tracking" (11 days), "Surface blockers" (11 days). All will hit 14-day window within 3 days without reinforcement.

## Scripts Created

- `scripts/praxis_review.py` — full standalone review pass (journal scan → signal extraction → event recording → debrief generation → evidence logging)

## Gotchas Updated

1. `summary` field can be dict OR string (new)
2. `blockers_active` needs type guard (new)
3. F-string backslash escaping in write_file (new)
4. Review script path mismatch → now says script exists (updated)
5. Proposed shift activation delay — activate promptly with evidence (new)
