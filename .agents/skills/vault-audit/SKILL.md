---
name: vault-audit
description: Use when I ask for a vault audit, health check, or whether the AI can actually see my files.
---
# Vault audit
1. Run `python3 scripts/brain.py doctor` and report any FAIL or warn line. Offer `doctor --fix` for fixable ones.
2. Run `python3 scripts/brain.py health --write` and summarize _meta/vault-health.md in five lines.
3. Run `python3 scripts/brain.py audit --verify`. A broken chain means someone edited the AI write log: tell the user.
4. Check AGENTS.md + CLAUDE.md length. If over 200 lines together, propose what to move into rules or skills.
5. Ask the user to confirm the agent sees its memory: Claude Code `/context` (AGENTS.md, CLAUDE.md, rules under Memory files) and `/mcp` (brain connected); Hermes `hermes mcp list` and `hermes hooks list`.
6. Look for contradictions between AGENTS.md, CLAUDE.md, .claude/rules/ and notes. List any pair that disagrees.
7. Confirm hooks are registered: read .claude/settings.json and list each hook and what it enforces.
8. Score out of 6: memory loaded, MCP connected, under 200 lines, agent memory reviewed this month, hard rules in code, no contradictions.
