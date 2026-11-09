"""The tool surface every AI gets: one definition, many transports.

The MCP server, the Hermes/OpenAI tool-schema export and the local chat loop
all read TOOLS, so a tool behaves identically whichever model calls it.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable

from . import context, health, writer
from .index import open_index
from .vault import ROOT, TYPES, load_note, resolve

AGENT = os.environ.get("BRAIN_AGENT", "")
NOTE_TYPES = [t for t in TYPES if t != "journal"]


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    handler: Callable[..., object]
    writes: bool = False

    def call(self, args: dict) -> str:
        """Run the tool and return text for the model. Refusals are text too."""
        try:
            result = self.handler(**(args or {}))
        except writer.VaultError as e:
            return f"Refused: {e}"
        except TypeError as e:
            return f"Bad arguments for {self.name}: {e}"
        if isinstance(result, str):
            return result
        return json.dumps(result, indent=2, ensure_ascii=False)


def _obj(props: dict, required: list | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [],
            "additionalProperties": False}


STR = {"type": "string"}
STR_LIST = {"type": "array", "items": {"type": "string"}}


# ---------------------------------------------------------------- handlers

def _search(query: str, limit: int = 8, types: list | None = None, include_archive: bool = False):
    idx = open_index()
    try:
        hits = idx.search(query, limit=max(1, min(int(limit), 25)), types=types or None,
                          include_archive=bool(include_archive))
        if not hits:
            return {"results": [], "hint": "Nothing matched. Try other words, or say the vault has no note on it."}
        return {"results": [h.as_dict() for h in hits]}
    finally:
        idx.close()


def _read(note: str):
    path = resolve(note)
    if not path:
        return f"No note matches {note!r}. Use brain_search first."
    n = load_note(path)
    idx = open_index()
    try:
        back = [b["stem"] for b in idx.backlinks(n.stem) if b["stem"] != n.stem]
        idx.record_access([n.stem])
    finally:
        idx.close()
    meta = f"[path: {n.rel}] [backlinks: {', '.join('[[%s]]' % b for b in back) or 'none'}]"
    return meta + "\n\n" + n.text


def _recall(query: str, limit: int = 5):
    text = context.recall(query, limit=max(1, min(int(limit), 10)), strict=False)
    return text or "The vault has no note that matches. Say so rather than guessing."


def _wake_up():
    return context.wake_up()


def _facts(subject: str = "", predicate: str = "", as_of: str = ""):
    idx = open_index()
    try:
        facts = idx.facts(subject=subject, predicate=predicate, as_of=as_of)
        if not facts:
            return "No dated facts match. Facts live in '## Facts' sections of notes."
        return {"as_of": as_of or "any time", "facts": [f.as_dict() for f in facts]}
    finally:
        idx.close()


def _recent(limit: int = 10):
    idx = open_index()
    try:
        return {"recent": idx.recent(max(1, min(int(limit), 50)))}
    finally:
        idx.close()


def _capture(text: str, title: str = "", source: str = ""):
    return writer.capture(text, title=title, source=source, agent=AGENT)


def _journal(entry: str):
    return writer.journal(entry, agent=AGENT)


def _create(type: str, title: str, summary: str, sections: dict | None = None,
            related: list | None = None, tags: list | None = None, source: str = "",
            confidence: str = "", aliases: list | None = None):
    return writer.create_note(type, title, summary, sections=sections, related=related,
                              tags=tags, source=source, confidence=confidence, aliases=aliases)


def _update(note: str, append: dict | None = None, set: dict | None = None,
            verified: bool = False, related: list | None = None):
    return writer.update_note(note, append=append, set_fields=set, verified=bool(verified), related=related)


def _decision(title: str, decision: str, why: str, rejected: str = "", change_mind: str = "",
              related: list | None = None):
    return writer.log_decision(title, decision, why, rejected=rejected, change_mind=change_mind, related=related)


def _archive(note: str, reason: str):
    return writer.archive(note, reason=reason)


def _health():
    rep = health.run()
    return rep.as_dict()


# ---------------------------------------------------------------- registry

TOOLS: list[Tool] = [
    Tool("brain_wake_up",
         "Orientation pack for the start of a session: current priorities, recent decisions, "
         "recently changed notes, today's journal and inbox count. Call once at the start.",
         _obj({}), _wake_up),
    Tool("brain_recall",
         "Answer-ready recall for a question: the most relevant notes with their summaries. "
         "Call before answering anything about the user, their work, people or past decisions.",
         _obj({"query": {**STR, "description": "The question or topic in plain words."},
               "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}}, ["query"]),
         _recall),
    Tool("brain_search",
         "Ranked full-text search (BM25) over the vault with filters. Returns note names, "
         "summaries, matched words and snippets.",
         _obj({"query": STR,
               "limit": {"type": "integer", "minimum": 1, "maximum": 25, "default": 8},
               "types": {"type": "array", "items": {"type": "string", "enum": list(TYPES) + ["capture"]}},
               "include_archive": {"type": "boolean", "default": False}}, ["query"]),
         _search),
    Tool("brain_read",
         "Read one note in full, with its path and the notes that link to it. Accepts a note "
         "name, a [[wikilink]] or a vault-relative path.",
         _obj({"note": STR}, ["note"]), _read),
    Tool("brain_facts",
         "Dated facts (subject | predicate | object | from | to) from notes' Facts sections. "
         "Use as_of (YYYY-MM-DD) to ask what was true on a date.",
         _obj({"subject": STR, "predicate": STR,
               "as_of": {**STR, "description": "YYYY, YYYY-MM or YYYY-MM-DD"}}), _facts),
    Tool("brain_recent", "Most recently changed notes.",
         _obj({"limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}), _recent),
    Tool("brain_capture",
         "Save something worth remembering to the inbox, raw, for the user to triage. The safe "
         "default for new information: use it when unsure where something belongs.",
         _obj({"text": {**STR, "description": "What to remember, in the user's words where possible."},
               "title": STR, "source": {**STR, "description": "Where it came from (URL, chat, file)."}},
              ["text"]), _capture, writes=True),
    Tool("brain_journal",
         "Append one line to today's journal: what was done or learned this session.",
         _obj({"entry": STR}, ["entry"]), _journal, writes=True),
    Tool("brain_create_note",
         "Create a structured note from the vault template. Search first: duplicates are refused. "
         "Requires a one-sentence summary. related must name notes that exist.",
         _obj({"type": {"type": "string", "enum": NOTE_TYPES},
               "title": STR,
               "summary": {**STR, "description": "One sentence. Shown by search and recall."},
               "sections": {"type": "object", "additionalProperties": {"type": "string"},
                            "description": "Heading -> markdown, e.g. {\"Details\": \"...\", \"Sources\": \"...\"}."},
               "related": {**STR_LIST, "description": "Existing note names to link."},
               "tags": STR_LIST, "aliases": STR_LIST,
               "source": STR,
               "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
              ["type", "title", "summary"]), _create, writes=True),
    Tool("brain_update_note",
         "Update an existing note: append text under headings, set frontmatter fields "
         "(status, summary, tags, aliases, confidence, superseded_by, source, review_after), "
         "mark facts verified today, or add related links.",
         _obj({"note": STR,
               "append": {"type": "object", "additionalProperties": {"type": "string"}},
               "set": {"type": "object"},
               "verified": {"type": "boolean", "default": False},
               "related": STR_LIST}, ["note"]), _update, writes=True),
    Tool("brain_log_decision",
         "Record a decision the user made or confirmed: creates the decision note and adds it to "
         "the decision log. Record only what the user stated.",
         _obj({"title": STR, "decision": STR, "why": STR, "rejected": STR,
               "change_mind": {**STR, "description": "What would change the user's mind."},
               "related": STR_LIST}, ["title", "decision", "why"]), _decision, writes=True),
    Tool("brain_archive",
         "Retire a note by moving it to 90-archive/. Nothing is ever deleted. Only when the user asks.",
         _obj({"note": STR, "reason": STR}, ["note", "reason"]), _archive, writes=True),
    Tool("brain_health",
         "Vault health report: broken links, missing frontmatter, stale facts, orphans, secrets.",
         _obj({}), _health),
]


def get_tools(read_only: bool = False) -> list[Tool]:
    return [t for t in TOOLS if not (read_only and t.writes)]


def by_name(read_only: bool = False) -> dict[str, Tool]:
    return {t.name: t for t in get_tools(read_only)}


def openai_schema(read_only: bool = False) -> list[dict]:
    """OpenAI-style function list. Hermes models, Ollama, LM Studio, vLLM and llama.cpp accept it."""
    return [{"type": "function", "function": {"name": t.name, "description": t.description,
                                              "parameters": t.schema}} for t in get_tools(read_only)]


def hermes_tools_block(read_only: bool = False) -> str:
    """The <tools> block of the Hermes function-calling system prompt."""
    lines = [json.dumps(s, ensure_ascii=False) for s in openai_schema(read_only)]
    return "<tools>\n" + "\n".join(lines) + "\n</tools>"


VAULT_ROOT = ROOT
