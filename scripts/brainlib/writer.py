"""Validated writes. Every AI-facing write path ends here.

Each function enforces the vault rules in code (naming, templates, required
frontmatter, links, the content policy) so a model that never read AGENTS.md
still cannot damage the vault.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Optional

from . import audit, policy
from .vault import (
    ARCHIVE, CONFIDENCE, DECISIONS, INBOX, JOURNAL, META, ROOT, STATUSES, TYPES,
    extract_links, is_inside, iter_note_paths, load_note, render_template, resolve,
    set_frontmatter_fields, slugify, today,
)


class VaultError(Exception):
    """A write was refused. The message is safe to show to the model."""


INDEX_HEADINGS = {
    "note": "Notes", "source": "Sources", "person": "People",
    "project": "Projects", "draft": "Drafts",
}
SETTABLE_FIELDS = {
    "status", "summary", "tags", "aliases", "confidence", "superseded_by", "source",
    "review_after", "pinned",
}


# ---------------------------------------------------------------- helpers

def _guard(text: str, path: Path) -> None:
    if not is_inside(path):
        raise VaultError("refusing to write outside the vault.")
    reason = policy.check_write_path(path.as_posix()) or policy.check_content(text, path.name)
    if reason:
        raise VaultError(reason)


def _write(path: Path, text: str, action: str = "write") -> None:
    _guard(text, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)  # atomic on POSIX and Windows
    audit.record(action, path.relative_to(ROOT).as_posix(), audit.sha(text))


def _clean(text: Optional[str]) -> str:
    return (text or "").strip()


def _stem_taken(stem: str) -> Optional[str]:
    for p in iter_note_paths():
        if p.stem == stem:
            return p.relative_to(ROOT).as_posix()
    return None


def _link_list(refs) -> list[str]:
    out = []
    for r in refs or []:
        r = str(r).strip()
        if not r:
            continue
        m = re.fullmatch(r"\[\[([^\]\|#]+)(?:[#|][^\]]*)?\]\]", r)
        stem = m.group(1).strip() if m else r
        if "/" in stem or stem.endswith(".md"):
            stem = Path(stem).stem
        out.append(stem)
    return list(dict.fromkeys(out))


def section_bounds(text: str, heading: str) -> Optional[tuple[int, int]]:
    """(start of section content, end of section) for '## heading', or None."""
    m = re.search(r"^##[ \t]+" + re.escape(heading) + r"[ \t]*$", text, re.M | re.I)
    if not m:
        return None
    nxt = re.search(r"^##?[ \t]+", text[m.end():], re.M)
    end = m.end() + nxt.start() if nxt else len(text)
    return m.end(), end


def put_in_section(text: str, heading: str, content: str, replace: bool = False) -> str:
    """Append content to a section (or replace it). Creates it before Related."""
    content = content.strip("\n")
    b = section_bounds(text, heading)
    if b is None:
        rel = section_bounds(text, "Related")
        block = f"## {heading}\n{content}\n\n"
        if rel is not None:
            start = text.rfind("\n## ", 0, rel[0]) + 1
            return text[:start] + block + text[start:]
        return text.rstrip("\n") + "\n\n" + block.rstrip("\n") + "\n"
    start, end = b
    existing = text[start:end].strip("\n")
    has_content = existing and not re.fullmatch(r"(Where I paused:|\(fill in\)|\s)*", existing)
    if replace or not has_content:
        new = content
    else:
        new = existing + "\n" + content
    tail = "\n\n" if end < len(text) else "\n"
    return text[:start] + "\n" + new + tail + text[end:].lstrip("\n")


def add_related(text: str, stems: list[str]) -> str:
    present = {t.split("/")[-1] for t, _ in extract_links(text)}
    lines = "\n".join(f"- [[{s}]]" for s in stems if s not in present)
    return put_in_section(text, "Related", lines) if lines else text


def register_in_index(stem: str, summary: str, note_type: str) -> None:
    heading = INDEX_HEADINGS.get(note_type)
    if not heading:
        return
    path = ROOT / META / "index.md"
    text = path.read_text(encoding="utf-8")
    if f"[[{stem}]]" in text:
        return
    line = f"- [[{stem}]]" + (f": {summary}" if summary else "")
    text = put_in_section(text, heading, line)
    text = set_frontmatter_fields(text, {"updated": today()})
    _write(path, text)


# ---------------------------------------------------------------- captures

def capture(text: str, title: str = "", source: str = "", agent: str = "") -> dict:
    """Raw capture into the inbox. Triage turns it into real notes later."""
    text = _clean(text)
    if not text:
        raise VaultError("nothing to capture.")
    now = datetime.datetime.now()
    slug = slugify(title or " ".join(text.split()[:8]))
    path = ROOT / INBOX / f"{now:%Y-%m-%d-%H%M}-{slug}.md"
    n = 2
    while path.exists():
        path = ROOT / INBOX / f"{now:%Y-%m-%d-%H%M}-{slug}-{n}.md"
        n += 1
    fm = {"type": "capture", "created": now.date().isoformat()}
    if source:
        fm["source"] = source
    if agent:
        fm["captured_by"] = agent
    body = (f"# {title}\n\n" if title else "") + text + "\n"
    _write(path, set_frontmatter_fields(body, fm))
    return {"path": path.relative_to(ROOT).as_posix(), "status": "captured to inbox"}


def journal(entry: str, agent: str = "", date: str = "") -> dict:
    """Append a timestamped line to today's journal (episodic memory)."""
    entry = " ".join(_clean(entry).split())
    if not entry:
        raise VaultError("empty journal entry.")
    day = date or today()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise VaultError("date must be YYYY-MM-DD.")
    path = ROOT / JOURNAL / f"{day}.md"
    text = path.read_text(encoding="utf-8") if path.exists() else render_template("journal", day)
    stamp = datetime.datetime.now().strftime("%H:%M")
    who = f" ({agent})" if agent else ""
    text = put_in_section(text, "Log", f"- {stamp}{who}: {entry}")
    text = set_frontmatter_fields(text, {"updated": today()})
    _write(path, text)
    return {"path": path.relative_to(ROOT).as_posix(), "status": "journal updated"}


# ---------------------------------------------------------------- notes

def create_note(note_type: str, title: str, summary: str, sections: Optional[dict] = None,
                related: Optional[list] = None, tags: Optional[list] = None,
                source: str = "", confidence: str = "", aliases: Optional[list] = None) -> dict:
    if note_type not in TYPES or note_type == "journal":
        raise VaultError(f"type must be one of: {', '.join(t for t in TYPES if t != 'journal')}.")
    title, summary = _clean(title), " ".join(_clean(summary).split())
    if not title:
        raise VaultError("a title is required.")
    if not summary and note_type != "draft":
        raise VaultError("a one-sentence summary is required. It is what search and recall show.")
    if confidence and confidence not in CONFIDENCE:
        raise VaultError("confidence must be high, medium or low.")
    folder, template = TYPES[note_type]
    stem = slugify(title)
    if note_type == "decision":
        stem = f"{today()}-{stem}"
    taken = _stem_taken(stem)
    if taken:
        raise VaultError(f"a note named {stem} already exists at {taken}. Update it instead of duplicating.")
    path = ROOT / folder / f"{stem}.md"

    text = render_template(template, title)
    fields: dict = {}
    if summary:
        fields["summary"] = summary
    if tags:
        fields["tags"] = [slugify(t) for t in tags if str(t).strip()]
    if aliases:
        fields["aliases"] = [str(a).strip() for a in aliases if str(a).strip()]
    if source:
        fields["source"] = source
    if confidence:
        fields["confidence"] = confidence
    text = set_frontmatter_fields(text, fields)
    if summary:
        text = text.replace("One-sentence summary.", summary, 1)
    for heading, content in (sections or {}).items():
        if _clean(content):
            text = put_in_section(text, str(heading).strip(), _clean(content), replace=True)

    links = _link_list(related)
    missing = [s for s in links if not resolve(s)]
    if missing:
        raise VaultError(f"related notes not found: {', '.join(missing)}. Search first, or leave them out.")
    text = add_related(text, links)
    _write(path, text)
    register_in_index(stem, summary, note_type)
    if note_type == "decision":
        _log_decision_line(stem, summary)
    return {"note": stem, "path": path.relative_to(ROOT).as_posix(), "status": "created"}


def log_decision(title: str, decision: str, why: str, rejected: str = "",
                 change_mind: str = "", related: Optional[list] = None) -> dict:
    return create_note(
        "decision", title, summary=decision,
        sections={"Decision": decision, "Why": why, "Options rejected": rejected,
                  "What would change my mind": change_mind},
        related=related)


def _log_decision_line(stem: str, summary: str) -> None:
    path = ROOT / DECISIONS / "decisions.md"
    text = path.read_text(encoding="utf-8")
    if f"[[{stem}]]" in text:
        return
    line = f"- {today()} [[{stem}]]: {summary}"
    m = re.search(r"^- \d{4}-\d{2}-\d{2} ", text, re.M)  # newest first
    if m:
        text = text[:m.start()] + line + "\n" + text[m.start():]
    else:
        text = put_in_section(text, "Log", line) if section_bounds(text, "Log") else \
            text.replace("\n## Related", f"\n{line}\n\n## Related", 1)
    _write(path, set_frontmatter_fields(text, {"updated": today()}))


def update_note(ref: str, append: Optional[dict] = None, set_fields: Optional[dict] = None,
                verified: bool = False, related: Optional[list] = None) -> dict:
    path = resolve(ref)
    if not path:
        raise VaultError(f"no note matches {ref!r}. Search first.")
    rel = path.relative_to(ROOT).as_posix()
    if rel.startswith(INBOX + "/"):
        raise VaultError("inbox captures are raw. Triage them instead of editing.")
    if rel.startswith(ARCHIVE + "/"):
        raise VaultError("archived notes are frozen. Create a new note and link it.")
    note = load_note(path)
    text = note.text
    fields = {}
    for k, v in (set_fields or {}).items():
        if k not in SETTABLE_FIELDS:
            raise VaultError(f"field {k!r} cannot be set. Allowed: {', '.join(sorted(SETTABLE_FIELDS))}.")
        if k == "status" and v not in STATUSES:
            raise VaultError(f"status must be one of: {', '.join(sorted(STATUSES))}.")
        if k == "confidence" and v not in CONFIDENCE:
            raise VaultError("confidence must be high, medium or low.")
        if k == "superseded_by":
            target = _link_list([v])[0] if _link_list([v]) else ""
            if not resolve(target):
                raise VaultError(f"superseded_by target {v!r} not found.")
            fields["status"] = "superseded"
            v = f"[[{target}]]"
        fields[k] = v
    for heading, content in (append or {}).items():
        if _clean(content):
            text = put_in_section(text, str(heading).strip(), _clean(content))
    links = _link_list(related)
    missing = [s for s in links if not resolve(s)]
    if missing:
        raise VaultError(f"related notes not found: {', '.join(missing)}.")
    text = add_related(text, links)
    fields["updated"] = today()
    if verified:
        fields["last_verified"] = today()
        if note.type == "person":
            text = put_in_section(text, "Last contact", today(), replace=True)
    text = set_frontmatter_fields(text, fields)
    if text == note.text:
        return {"note": note.stem, "path": rel, "status": "unchanged"}
    _write(path, text)
    return {"note": note.stem, "path": rel, "status": "updated"}


def archive(ref: str, reason: str = "") -> dict:
    """Retire a note. Never deletes: moves it to 90-archive/<folder>/."""
    path = resolve(ref)
    if not path:
        raise VaultError(f"no note matches {ref!r}.")
    rel = path.relative_to(ROOT).as_posix()
    if rel.startswith(ARCHIVE + "/") or rel.startswith(META + "/"):
        raise VaultError("that note cannot be archived.")
    if path.stem in ("now", "decisions"):
        raise VaultError("anchor notes cannot be archived.")
    dest = ROOT / ARCHIVE / rel
    if dest.exists():
        raise VaultError(f"{dest.relative_to(ROOT).as_posix()} already exists.")
    text = load_note(path).text
    if not rel.startswith(INBOX + "/"):
        text = set_frontmatter_fields(text, {"status": "archived", "updated": today()})
        if reason:
            text = put_in_section(text, "Archived", f"{today()}: {reason}")
    _guard(text, dest)
    _write(path, text)
    dest.parent.mkdir(parents=True, exist_ok=True)
    path.replace(dest)
    audit.record("archive", rel, audit.sha(text), detail=f"moved to {dest.relative_to(ROOT).as_posix()}")
    return {"from": rel, "to": dest.relative_to(ROOT).as_posix(), "status": "archived"}
