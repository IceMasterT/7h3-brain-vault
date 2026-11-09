# Second brain: shared long-term memory for every AI

One folder of plain Markdown. Obsidian is the window you read and link in. Every AI you use (Claude Code, Hermes Agent, local Hermes models, Claude Desktop, Cursor, Codex, Gemini CLI, LM Studio) reads and writes the same memory through one engine, under the same rules, with an audit trail.

No dependencies: Python 3.9+ standard library and SQLite FTS5. Works offline.

## Install
```bash
./install.sh ~/second-brain            # new vault
./install.sh --upgrade ~/my-vault      # upgrade an existing vault in place (notes untouched, engine backed up to .backups/)
```
Then:
1. Obsidian: Open folder as vault.
2. Fill in `_meta/identity.md`: who you are and how you like answers. Every AI reads it at session start.
3. `python3 scripts/brain.py doctor` until every line is ok.
4. Connect your AIs (below).

## Connect your AIs
| AI | How |
|---|---|
| Claude Code | `cd` into the vault and run `claude`. AGENTS.md, rules, skills, hooks and the MCP server load automatically. Check with `/context` and `/mcp`. From other projects: `brain.py connect claude-code`. |
| Hermes Agent | `python3 scripts/brain.py connect hermes` prints the block for `~/.hermes/config.yaml`: the MCP server, the vault skills, the safety guard and per-turn recall. Approve the hooks once, then check with `hermes mcp test brain` and `hermes hooks doctor`. |
| Local Hermes models (Ollama, LM Studio, llama.cpp, vLLM) | `python3 scripts/brain.py chat --model hermes3` (Ollama at localhost:11434 by default; `--base-url` for others). Uses native tool calls, or the Hermes `<tool_call>` format when the server has none. Writes ask before saving. |
| Any model without tools | `python3 scripts/brain.py prompt --hermes` prints a system prompt with the wake-up pack and the Hermes tool block. `brain.py tools --format openai` prints the tool schemas. |
| Claude Desktop, LM Studio, Cursor, Codex, Gemini CLI | `python3 scripts/brain.py connect <claude-desktop, lm-studio, cursor, codex or gemini>` prints the config to paste. Cursor also picks up `.cursor/mcp.json` inside the vault. |

## How memory works
| Layer | Where | Reaches the AI |
|---|---|---|
| L0 identity | `_meta/identity.md` | every session (wake-up pack) |
| L1 essentials | memory protocol, `now.md`, pinned notes, recent decisions, today's journal | every session (wake-up pack) |
| L2 recall | notes matching the current prompt | every prompt (Claude `UserPromptSubmit`, Hermes `pre_llm_call`) |
| L3 search | everything | on demand: `brain_search`, `brain_read`, `brain_facts` |
| Manual | `AGENTS.md` (shared), `CLAUDE.md` and `GEMINI.md` import it | every session |
| Folder rules | `.claude/rules/*.md` | Claude by path; others read them before writing in a folder |
| Procedures | `.agents/skills/*` (Agent Skills format; linked into `.claude/skills/`) | when invoked |
| Enforcement | `scripts/brainlib/policy.py` via hooks, the MCP server, the CLI and a git pre-commit check | always |

Memory kinds map to folders: `00-inbox` intake, `10-notes` semantic, `20-people` people, `30-projects` working, `40-drafts` drafts, `50-decisions` decisions, `60-journal` episodic, `90-archive` cold.

What makes it more than a folder of notes:
- **Ranked search.** SQLite FTS5 with BM25, blended with question coverage, title hits, recency, link centrality, pins and how often a note proved useful. The index in `.brain/` is a cache that rebuilds itself.
- **Quiet recall.** Per-prompt recall only injects notes that match at least two words of the prompt, so unrelated turns stay clean.
- **Dated facts.** `- subject | predicate | object | from | to` lines in a `## Facts` section. Ask what was true on a date (`brain_facts as_of`). Overlapping contradictions are flagged.
- **Never delete.** Notes are superseded (`superseded_by`) or archived, never removed.
- **Validated writes.** Templates, naming, summaries, links and the index are enforced in code, so even a model that never read the rules writes clean notes.
- **Audit trail.** Every AI write goes to `_meta/audit-log.jsonl`, hash-chained. `brain.py audit --verify` detects tampering.
- **Fading notes.** `brain.py fading` lists notes nobody used or edited in 90 days, as archive proposals. Nothing is archived without you.
- **Save nudges.** Every 15 user messages, Claude Code (Stop hook) and Hermes (recall hook) are reminded to save what they learned.

## The brain CLI
```bash
python3 scripts/brain.py search "motor controller" --type project
python3 scripts/brain.py recall "who reviews my designs?"
python3 scripts/brain.py facts --subject "Dana Reyes" --as-of 2025-06
python3 scripts/brain.py capture "Dana prefers email over calls" --source "chat 2026-11-09"
python3 scripts/brain.py journal "Picked the MCU for the rover"
python3 scripts/brain.py health        # --strict fails on errors (used by the pre-commit check)
python3 scripts/brain.py triage-suggest
python3 scripts/brain.py audit --verify
python3 scripts/brain.py doctor --fix
```
`python3 scripts/brain.py --help` lists everything.

## MCP tools
Read: `brain_wake_up`, `brain_recall`, `brain_search`, `brain_read`, `brain_facts`, `brain_recent`, `brain_health`.
Write (validated, audited): `brain_capture`, `brain_journal`, `brain_create_note`, `brain_update_note`, `brain_log_decision`, `brain_archive`.
`scripts/mcp_server.py --read-only` exposes only the read tools, for AIs you do not want writing.

## What enforces what
- Blocked for every AI: deleting files (`rm`, `rmdir`, `unlink`, `git rm`, `git clean`, `find -delete`, also through `xargs`, `find -exec`, `env`, `sh -c`), force push, hard reset, `sudo`, network transfer tools, moving files out of the vault, edits to hooks, settings, git hooks and the policy itself, secrets and card numbers in content, em dashes in notes.
- Claude Code: `guard.py` (PreToolUse) plus the `settings.json` deny list.
- Hermes Agent: the same `guard.py` as a `pre_tool_call` shell hook with `fail_closed`. It acts only on paths inside the vault.
- MCP server and CLI: the same policy inside every write.
- Obsidian: the git pre-commit check refuses commits that add secrets or break vault health.
- To allow something blocked, edit `scripts/brainlib/policy.py` yourself. No AI can.

## Routines
- Daily: capture to `00-inbox` (Obsidian or `brain_capture`), then "triage the inbox". Journal lines as you work.
- On a decision: "log this decision".
- End of a session: "wrap up" (session-close skill).
- Weekly: "run weekly-review" (stale facts, conflicts, fading notes, priorities).
- Monthly: "run promote-memory" (Claude auto memory and Hermes MEMORY.md into the vault), then "run vault-audit".

## Checks after setup
1. `python3 -m unittest discover -s scripts/tests`: the engine's own tests, run on a temporary copy.
2. Ask "Where do notes live and how are they named?" The answer should match AGENTS.md.
3. Ask "Save my password hunter2 in a note." It must be refused.
4. Ask "Delete 10-notes/how-this-vault-works.md." It must be refused, with an offer to archive.
5. Ask about something you saved. The answer should cite the note as a [[wikilink]].

## Layout
```
AGENTS.md            shared manual for every AI       CLAUDE.md / GEMINI.md  import it
.mcp.json            Claude Code MCP config            .cursor/mcp.json       Cursor MCP config
.agents/skills/      procedures, shared                .claude/skills/        links to them
.claude/hooks/       guard, recall, save nudge, session start (Claude Code and Hermes)
.claude/rules/       folder rules                      .githooks/pre-commit   commit-time checks
scripts/brain.py     CLI                               scripts/mcp_server.py  MCP server
scripts/brainlib/    the engine (policy, index, writer, context, facts, audit, tools, hermes, chat)
scripts/tests/       test suite                        _templates/            note blueprints
_meta/               identity, index, audit log, promotion log, health report
.brain/              search index cache (gitignored)   .backups/              upgrade backups (gitignored)
```
