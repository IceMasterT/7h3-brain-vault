---
type: note
status: active
created: 2026-10-31
updated: 2026-11-09
last_verified: 2026-11-09
summary: One Markdown folder is the shared long-term memory for every AI the user works with, with search, recall, safety rules and an audit trail built in.
tags: [meta]
aliases: [vault design, second brain design]
source: setup
confidence: high
pinned: true
---
# How this vault works

One Markdown folder is the shared long-term memory for every AI the user works with, with search, recall, safety rules and an audit trail built in.

## Details
- One folder, many readers. Obsidian is the human UI. Claude Code, Hermes Agent, Codex, Cursor, Gemini CLI, Claude Desktop and local models reach it through AGENTS.md, an MCP server, hooks and the brain CLI.
- Memory kinds: identity (_meta/identity.md), working (now.md, projects), semantic (notes, people, decisions), episodic (60-journal), procedural (.agents/skills).
- Context loads in layers. L0 identity and L1 essentials (protocol, priorities, pinned notes, decisions) arrive at session start as the wake-up pack. L2 recall injects matching notes on each prompt. L3 is full search on demand.
- Search is SQLite FTS5 with BM25, boosted by links, recency, pins and use. The index in .brain/ is a cache that rebuilds from the files.
- Dated facts in "## Facts" sections let the vault answer what was true on a date and flag contradictions.
- Hard rules live in code (scripts/brainlib/policy.py) and are enforced by the Claude Code and Hermes hooks, the MCP server and a git pre-commit check. AGENTS.md is context, not enforcement.
- Every AI write is recorded in _meta/audit-log.jsonl, hash-chained so tampering shows.
- Daily: capture to 00-inbox, triage, work, journal. Weekly: weekly-review. Monthly: promote-memory. Any time: vault-audit.

## Facts
- vault | design version | 2 | 2026-11-09 |
- vault | design version | 1 | 2026-10-31 | 2026-11-09

## Sources
- Setup session, 2026-10-31. Upgrade session, 2026-11-09.

## Related
- [[index]]
- [[decisions]]
- [[2026-11-09-shared-memory-for-every-ai]]
