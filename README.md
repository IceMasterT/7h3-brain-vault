# 7h3 Brain Vault

Your long-term memory, shared by every AI you use.

7h3 Brain Vault is one folder of plain Markdown. Obsidian is the window you read and link in. Claude Code, Hermes Agent, local Hermes models, Claude Desktop, Cursor, Codex, Gemini CLI and LM Studio all read and write the same notes through one engine. They follow the same rules, and every write leaves an audit trail.

- No dependencies. Python 3.9+ standard library and SQLite FTS5.
- Works offline.
- Markdown is the only database. The search index is a cache you can delete.

## Quick start
```bash
./install.sh ~/7h3-brain-vault            # new vault
./install.sh --upgrade ~/my-vault         # upgrade in place (notes untouched, engine backed up to .backups/)
```
Then:
1. In Obsidian, choose Open folder as vault.
2. Fill in `_meta/identity.md`: who you are and how you like answers. Every AI reads it at session start.
3. Run `python3 scripts/brain.py doctor` until every line is ok.
4. Connect your AIs (next section).

## Connect your AIs
| AI | How |
|---|---|
| Claude Code | `cd` into the vault and run `claude`. AGENTS.md, rules, skills, hooks and the MCP server load on their own. Check with `/context` and `/mcp`. From other projects, run `brain.py connect claude-code`. |
| Hermes Agent | `python3 scripts/brain.py connect hermes` prints the block for `~/.hermes/config.yaml` (MCP server, vault skills, safety guard, per-turn recall). Approve the hooks once, then check with `hermes mcp test brain` and `hermes hooks doctor`. |
| Local Hermes models (Ollama, LM Studio, llama.cpp, vLLM) | `python3 scripts/brain.py chat --model hermes3`. Defaults to Ollama at localhost:11434; use `--base-url` for others. Uses native tool calls, or the Hermes `<tool_call>` format when the server has none. Writes ask before saving. |
| Any model without tools | `python3 scripts/brain.py prompt --hermes` prints a system prompt with the wake-up pack. `brain.py tools --format openai` prints the tool schemas. |
| Claude Desktop, LM Studio, Cursor, Codex, Gemini CLI | `python3 scripts/brain.py connect <claude-desktop, lm-studio, cursor, codex or gemini>` prints the config to paste. Cursor also reads `.cursor/mcp.json` inside the vault. |

## How memory works
| Layer | Where | Reaches the AI |
|---|---|---|
| L0 identity | `_meta/identity.md` | every session (wake-up pack) |
| L1 essentials | memory protocol, `now.md`, pinned notes, recent decisions, today's journal | every session (wake-up pack) |
| L2 recall | notes matching the current prompt | every prompt |
| L3 search | everything | on demand: `brain_search`, `brain_read`, `brain_facts` |
| Manual | `AGENTS.md` (shared). `CLAUDE.md` and `GEMINI.md` import it. | every session |
| Folder rules | `.claude/rules/*.md` | Claude by path; others read them before writing in a folder |
| Procedures | `.agents/skills/*` (Agent Skills format, linked into `.claude/skills/`) | when invoked |
| Enforcement | `scripts/brainlib/policy.py` via hooks, the MCP server, the CLI and a git pre-commit check | always |

### Folders
| Folder | Holds | Memory kind |
|---|---|---|
| `00-inbox` | raw captures | intake |
| `10-notes` | one topic per file | semantic |
| `20-people` | one person or company per file | semantic |
| `30-projects` | projects, plus the live `now.md` | working |
| `40-drafts` | writing in progress | working |
| `50-decisions` | one file per decision, plus the log | semantic |
| `60-journal` | one file per day | episodic |
| `90-archive` | retired notes | cold |

### What sets it apart
- **Ranked search.** BM25 blended with question coverage, title hits, recency, link centrality, pins and past usefulness.
- **Quiet recall.** A prompt only pulls in notes that match at least two of its words, so unrelated turns stay clean.
- **Dated facts.** `- subject | predicate | object | from | to` lines in a `## Facts` section. Ask what was true on a date with `brain_facts as_of`. Overlapping contradictions are flagged.
- **Never delete.** Notes are superseded (`superseded_by`) or archived.
- **Validated writes.** Templates, naming, summaries, links and the index are enforced in code, even for a model that never read the rules.
- **Audit trail.** Every AI write goes to `_meta/audit-log.jsonl`, hash-chained. `brain.py audit --verify` detects tampering.
- **Fading notes.** `brain.py fading` lists notes unused for 90 days as archive proposals. Nothing moves without you.
- **Save nudges.** Every 15 user messages, Claude Code and Hermes are reminded to save what they learned.

## CLI
```bash
python3 scripts/brain.py search "motor controller" --type project
python3 scripts/brain.py recall "who reviews my designs?"
python3 scripts/brain.py facts --subject "Dana Reyes" --as-of 2025-06
python3 scripts/brain.py capture "Dana prefers email over calls" --source "chat 2026-11-09"
python3 scripts/brain.py journal "Picked the MCU for the rover"
python3 scripts/brain.py health            # --strict fails on errors (used by pre-commit)
python3 scripts/brain.py triage-suggest
python3 scripts/brain.py audit --verify
python3 scripts/brain.py doctor --fix
```
`python3 scripts/brain.py --help` lists everything.

## MCP tools
- **Read:** `brain_wake_up`, `brain_recall`, `brain_search`, `brain_read`, `brain_facts`, `brain_recent`, `brain_health`.
- **Write (validated, audited):** `brain_capture`, `brain_journal`, `brain_create_note`, `brain_update_note`, `brain_log_decision`, `brain_archive`.

`scripts/mcp_server.py --read-only` exposes only the read tools, for AIs you do not want writing.

## Safety
Blocked for every AI:
- deleting files (`rm`, `rmdir`, `unlink`, `git rm`, `git clean`, `find -delete`, also through `xargs`, `find -exec`, `env` and `sh -c`)
- force push, hard reset, `sudo`, network transfer tools
- moving files out of the vault
- edits to hooks, settings, git hooks and the policy itself
- secrets and card numbers in content
- em dashes in notes

Who enforces it:
- **Claude Code:** `guard.py` (PreToolUse) plus the `settings.json` deny list.
- **Hermes Agent:** the same `guard.py` as a fail-closed `pre_tool_call` hook, limited to paths inside the vault.
- **MCP server and CLI:** the same policy inside every write.
- **Git:** the pre-commit check refuses commits that add secrets or break vault health.

To allow something that is blocked, edit `scripts/brainlib/policy.py` yourself. No AI can.

## Routines
- **Daily:** capture to `00-inbox`, then say "triage the inbox". Add journal lines as you work.
- **On a decision:** say "log this decision".
- **End of a session:** say "wrap up".
- **Weekly:** say "run weekly-review".
- **Monthly:** say "run promote-memory", then "run vault-audit".

## Verify your setup
1. `python3 -m unittest discover -s scripts/tests` runs the engine tests on a temporary copy.
2. Ask "Where do notes live and how are they named?" The answer should match AGENTS.md.
3. Ask "Save my password hunter2 in a note." It must be refused.
4. Ask "Delete 10-notes/how-this-vault-works.md." It must be refused, with an offer to archive.
5. Ask about something you saved. The answer should cite the note as a [[wikilink]].

## Layout
```
AGENTS.md            shared manual for every AI       CLAUDE.md, GEMINI.md   import it
.mcp.json            Claude Code MCP config           .cursor/mcp.json       Cursor MCP config
.agents/skills/      shared procedures                .claude/skills/        links to them
.claude/hooks/       guard, recall, save nudge, session start
.claude/rules/       folder rules                     .githooks/pre-commit   commit-time checks
scripts/brain.py     CLI                              scripts/mcp_server.py  MCP server
scripts/brainlib/    engine (policy, index, writer, context, facts, audit, tools, hermes, chat)
scripts/tests/       test suite                       _templates/            note blueprints
_meta/               identity, index, audit log, promotion log, health report
.brain/              search index cache (gitignored)  .backups/              upgrade backups (gitignored)
```
