# Praxis — Self-Update Procedure

`praxis.update` pulls the latest skill package from GitHub source. Preserves journals and data.

1. Read `source:` from frontmatter → extract `{owner}/{repo}` from URL
2. Read local version from SKILL.md frontmatter `metadata.version`
3. Fetch remote version: `gh api "repos/{owner}/{repo}/contents/SKILL.md" --jq '.content' | base64 -d | grep 'version:' | head -1 | sed 's/.*"\(.*\)".*/\1/'`
4. If remote version equals local version → stop silently
5. `cd {agent_root}/skills/ocas-praxis && git stash && git pull origin main && git stash pop`
6. On failure → retry once. If second attempt fails, report error and stop.
7. Output exactly: `I updated Praxis from version {old} to {new}`
