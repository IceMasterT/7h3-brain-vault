---
name: promote-memory
description: Use monthly, or when I ask to clean up, review or promote agent memory (Claude auto memory, Hermes MEMORY.md and USER.md).
---
# Promote agent memory into the vault
Agent memories collect corrections nobody reviews, and only one agent can read each. This skill turns them into a curated brain every AI can use.
1. Gather the entries. Claude Code: ask the user to open /memory, or read the files they point to. Hermes Agent: ~/.hermes/memories/MEMORY.md and USER.md (read only; ask first).
2. Classify every entry:
   - About the user (preferences, style, background): propose a line for _meta/identity.md.
   - Needed by every agent every session: propose a line for AGENTS.md (check the 200 line budget).
   - Only for one folder or file type: propose a rule in .claude/rules/ with paths.
   - A procedure: propose a skill in .agents/skills/.
   - A hard "never": propose a rule for scripts/brainlib/policy.py and tell the user to add it themselves.
   - World or work knowledge: propose a vault note.
   - Stale, duplicate, contradicting or one-off: propose deletion from the agent memory.
3. Show a table of entry, verdict, destination. Make no changes until the user approves each group.
4. Log the session in _meta/promotion-log.md: date, entries reviewed, promoted, deleted.
5. Flag any two entries that contradict each other. Never resolve a contradiction silently.
