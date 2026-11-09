---
type: decision
status: active
created: 2026-11-09
updated: 2026-11-09
summary: The vault is upgraded into shared memory for every AI, with one standard-library core behind an MCP server, hooks for Claude Code and Hermes, and a CLI.
tags: [architecture]
---
# Shared memory for every AI

## Decision
The vault becomes shared long-term memory for any AI. AGENTS.md is the canonical manual. One Python standard-library core (scripts/brainlib) powers an MCP server, Claude Code and Hermes Agent hooks, the brain CLI and a chat loop for local Hermes models.

## Why
- The first version only worked inside Claude Code. Memory that one agent cannot share is not a second brain.
- Standard library only: nothing to install, nothing to break, works offline.
- Rules enforced in one place behave the same for every agent.

## Options rejected
- Vector database and embeddings: extra dependencies, opaque ranking, not needed at personal scale.
- A copy of the rules per tool: drifts out of sync.

## Assumptions
- SQLite with FTS5 is available in the system Python (doctor checks it).

## What would change my mind
- Search quality stops being good enough as the vault grows past a few thousand notes.

## Related
- [[decisions]]
- [[how-this-vault-works]]
