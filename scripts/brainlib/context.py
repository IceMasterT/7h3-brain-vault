"""Context building: the layered wake-up pack and per-question recall.

Layers (after mempalace's L0 to L3):
  L0 identity      _meta/identity.md, written by the user. Always loaded.
  L1 essentials    protocol, priorities, pinned notes, recent decisions. Always loaded.
  L2 recall        notes matching the current question. Injected per prompt.
  L3 search        full search and reads, on demand through tools.
Everything is short, sourced (each line names its note) and safe to inject.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .index import Index, open_index, query_terms
from .vault import (
    DECISIONS, INBOX, JOURNAL, META, PROJECTS, ROOT, iter_note_paths, load_note, strip_code, today,
)

WAKE_UP_BUDGET = 3200  # characters, about 800 tokens
RECALL_HEADER = "Second brain recall (vault notes that may be relevant; verify before relying on them):"

PROTOCOL = """Memory protocol:
1. Before any claim about the user, people, projects or past decisions, search the vault. Wrong is worse than slow.
2. Cite notes as [[wikilinks]]. Mark anything the vault does not say as "inferred".
3. New information goes to the inbox (brain_capture) unless the user asked for a structured note.
4. When a fact changes, close it (Facts "to" date or superseded_by). Never delete, archive instead.
5. Before the session ends, add one journal line (brain_journal): what was done or learned."""


def _list_items(text: str, limit: int) -> list[str]:
    items = re.findall(r"^\s*(?:\d+\.|-)\s+(.+)$", text, re.M)
    return [i.strip() for i in items if "(fill in)" not in i and not i.strip().startswith("[[")][:limit]


def _identity(root: Path) -> str:
    path = root / META / "identity.md"
    if not path.exists():
        return ""
    body = load_note(path, root).body
    body = re.sub(r"^#.*$", "", strip_code(body), flags=re.M)
    lines = [l.rstrip() for l in body.splitlines() if l.strip() and "(fill in)" not in l]
    return "\n".join(lines)[:600]


def wake_up(root: Path = ROOT, idx: Optional[Index] = None, budget: int = WAKE_UP_BUDGET) -> str:
    """Session-start orientation, highest value first, cut at the budget."""
    own = idx is None
    idx = idx or open_index(root)
    try:
        parts: list[str] = [f"Second brain wake-up ({today()}). Vault: {root}"]
        ident = _identity(root)
        if ident:
            parts.append("About the user [[identity]]:\n" + ident)
        parts.append(PROTOCOL)

        now = root / PROJECTS / "now.md"
        if now.exists():
            items = _list_items(load_note(now, root).body, 7)
            parts.append("Priorities [[now]]: " + ("; ".join(items) if items else "not set yet."))

        pinned = idx.db.execute(
            "SELECT stem, type, summary FROM docs WHERE pinned = 1 AND folder != '90-archive' "
            "AND status NOT IN ('archived','superseded') ORDER BY updated DESC LIMIT 15").fetchall()
        if pinned:
            parts.append("Pinned:\n" + "\n".join(
                f"- [[{r['stem']}]] ({r['type']}): {r['summary'][:160]}" for r in pinned))

        dec = root / DECISIONS / "decisions.md"
        if dec.exists():
            lines = re.findall(r"^- (\d{4}-\d{2}-\d{2}) \[\[([^\]]+)\]\]:?\s*(.*)$",
                               dec.read_text(encoding="utf-8"), re.M)
            if lines:
                parts.append("Recent decisions:\n" + "\n".join(
                    f"- {d} [[{s}]]: {t[:140]}" for d, s, t in lines[:5]))

        jpath = root / JOURNAL / f"{today()}.md"
        if jpath.exists():
            entries = re.findall(r"^- \d{2}:\d{2}.*$", jpath.read_text(encoding="utf-8"), re.M)
            if entries:
                parts.append("Today's journal (latest):\n" + "\n".join(entries[-3:]))

        recent = [r for r in idx.recent(8) if r["stem"] not in ("now", "decisions")][:5]
        if recent:
            parts.append("Recently changed:\n" + "\n".join(
                f"- [[{r['stem']}]] ({r['type'] or 'capture'}): {r['summary'][:120]}" for r in recent))

        inbox = sum(1 for p in iter_note_paths(root, include_archive=False, include_meta=False)
                    if p.relative_to(root).as_posix().startswith(INBOX + "/"))
        if inbox:
            parts.append(f"Inbox: {inbox} capture(s) waiting for triage.")

        out = ""
        for part in parts:
            if len(out) + len(part) + 2 > budget:
                out += "\n\n(more in the vault: use search)"
                break
            out += ("\n\n" if out else "") + part
        return out
    finally:
        if own:
            idx.close()


def recall(query: str, limit: int = 4, root: Path = ROOT, idx: Optional[Index] = None,
           strict: bool = True) -> str:
    """Relevant notes for a question, or '' when nothing clears the bar.

    strict mode (used by the per-prompt hooks) only returns notes that match at
    least two content words of the prompt (one for a one-word prompt) and, for
    longer prompts, at least a third of them. Unrelated turns stay free of noise.
    """
    terms = query_terms(query)
    if not terms:
        return ""
    own = idx is None
    idx = idx or open_index(root)
    try:
        hits = idx.search(query, limit=limit * 3)
        picked = []
        for h in hits:
            if strict:
                needed = 1 if len(terms) == 1 else 2
                if len(h.matched) < needed:
                    continue
                if len(terms) >= 4 and h.coverage < 0.34:
                    continue
            picked.append(h)
            if len(picked) >= limit:
                break
        if not picked:
            return ""
        idx.record_access([h.stem for h in picked])
        lines = [RECALL_HEADER]
        for h in picked:
            summary = h.summary or h.snippet
            status = f", {h.status}" if h.status and h.status != "active" else ""
            lines.append(f"- [[{h.stem}]] ({h.type or 'capture'}{status}; {h.rel}): {summary[:220]}")
        lines.append("Read a note in full before quoting it. Cite notes as [[wikilinks]].")
        return "\n".join(lines)
    finally:
        if own:
            idx.close()
