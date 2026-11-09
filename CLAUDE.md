# Second brain: Claude Code layer
<!-- The shared manual for every AI is AGENTS.md, imported below. Put only Claude-Code-specific notes here. Keep AGENTS.md + CLAUDE.md under 200 lines together. -->

@AGENTS.md

## Claude Code specifics
- Hooks inject the wake-up pack at session start and relevant notes on each prompt. Do not call brain_wake_up again unless the user asks.
- Path-scoped rules in .claude/rules/ load automatically when you touch a matching folder.
- Skills in .claude/skills/ are links to the shared .agents/skills/. Edit the shared copy.
- Auto memory (/memory) collects corrections. The promote-memory skill turns it into rules, skills and notes monthly. Prefer saving durable facts to the vault over auto memory: other AIs cannot read auto memory.
- CLAUDE.local.md (gitignored) holds private, per-machine notes. It loads after this file.

## Commands I use
- /memory: see and edit auto memory.
- /context: confirm AGENTS.md, CLAUDE.md and the rules loaded under Memory files.
- /mcp: confirm the brain server is connected.
- "run vault-audit", "run weekly-review", "run promote-memory", "triage the inbox", "log this decision".
