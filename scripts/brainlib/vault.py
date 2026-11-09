"""Vault layout, note parsing and frontmatter handling."""
from __future__ import annotations

import datetime
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional


def find_root() -> Path:
    """The vault root: $BRAIN_VAULT when set, else two levels above this file."""
    env = os.environ.get("BRAIN_VAULT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


ROOT = find_root()

INBOX = "00-inbox"
NOTES = "10-notes"
PEOPLE = "20-people"
PROJECTS = "30-projects"
DRAFTS = "40-drafts"
DECISIONS = "50-decisions"
JOURNAL = "60-journal"
ARCHIVE = "90-archive"
META = "_meta"
TEMPLATES = "_templates"

# Folders that hold live memory. Order matters for display only.
LIVE_FOLDERS = (INBOX, NOTES, PEOPLE, PROJECTS, DRAFTS, DECISIONS, JOURNAL)

# Note type -> home folder and template name.
TYPES = {
    "note": (NOTES, "note"),
    "source": (NOTES, "source"),
    "person": (PEOPLE, "person"),
    "project": (PROJECTS, "project"),
    "draft": (DRAFTS, "draft"),
    "decision": (DECISIONS, "decision"),
    "journal": (JOURNAL, "journal"),
}
META_TYPES = {"index", "log", "report"}

REQUIRED_KEYS = ("type", "status", "created", "updated")
NEEDS_VERIFIED = {"note", "person", "source"}
NEEDS_SUMMARY = {"note", "person", "project", "decision", "source"}
STATUSES = {
    "active", "idea", "drafting", "review", "done", "paused",
    "blocked", "superseded", "archived",
}
CONFIDENCE = {"high", "medium", "low"}

# Notes that are always present and are allowed to have no inbound links.
ANCHORS = {"index", "now", "decisions"}

STEM_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")
FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
H1_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.M)
LINK_RE = re.compile(r"(!?)\[\[([^\]\|#\^]+)(?:[#\^][^\]\|]*)?(?:\|[^\]]*)?\]\]")
FENCE_RE = re.compile(r"(```|~~~).*?\1", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def today() -> str:
    return datetime.date.today().isoformat()


def slugify(text: str) -> str:
    """Turn a title into a lowercase-with-hyphens file stem."""
    s = text.strip().lower()
    s = re.sub(r"['’]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:80].rstrip("-") or "untitled"


# ---------------------------------------------------------------- frontmatter
# A deliberately small YAML subset: scalars, inline lists and block lists.
# It covers everything the templates produce and fails soft on anything else.

def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def _parse_inline_list(v: str) -> list:
    inner = v.strip()[1:-1].strip()
    if not inner:
        return []
    return [_unquote(x) for x in re.split(r",(?=(?:[^\"']|\"[^\"]*\"|'[^']*')*$)", inner) if x.strip()]


def parse_frontmatter(text: str) -> tuple[dict, str, bool]:
    """Return (frontmatter, body, had_frontmatter)."""
    m = FM_RE.match(text)
    if not m:
        return {}, text, False
    fm: dict = {}
    key: Optional[str] = None
    for raw in m.group(1).splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s*-\s+(.*)$", line)
        if item and key is not None and isinstance(fm.get(key), list):
            fm[key].append(_unquote(item.group(1)))
            continue
        kv = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if not kv:
            continue
        key, val = kv.group(1), kv.group(2).strip()
        if val == "":
            fm[key] = []  # either an empty value or the start of a block list
        elif val.startswith("[") and val.endswith("]"):
            fm[key] = _parse_inline_list(val)
        else:
            fm[key] = _unquote(val)
    # An empty block list that never got items is an empty scalar.
    for k, v in list(fm.items()):
        if v == [] and k not in ("tags", "aliases"):
            fm[k] = ""
    return fm, text[m.end():], True


def _format_value(value) -> str:
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_format_scalar(v) for v in value) + "]"
    return _format_scalar(value)


def _format_scalar(value) -> str:
    s = "" if value is None else str(value)
    if s == "" or re.search(r"[:#\[\]{},&*!|>'\"%@`]|^\s|\s$|^-", s):
        if s == "":
            return ""
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def set_frontmatter_fields(text: str, updates: dict) -> str:
    """Set keys in a note's frontmatter, keeping every other line untouched."""
    m = FM_RE.match(text)
    if not m:
        lines = [f"{k}: {_format_value(v)}".rstrip() for k, v in updates.items()]
        return "---\n" + "\n".join(lines) + "\n---\n" + text
    block = m.group(1).splitlines()
    pending = dict(updates)
    out: list[str] = []
    i = 0
    while i < len(block):
        line = block[i]
        kv = re.match(r"^([A-Za-z0-9_\-]+)\s*:", line)
        if kv and kv.group(1) in pending:
            k = kv.group(1)
            out.append(f"{k}: {_format_value(pending.pop(k))}".rstrip())
            i += 1
            while i < len(block) and re.match(r"^\s*-\s+", block[i]):
                i += 1  # drop the old block-list items
            continue
        out.append(line)
        i += 1
    out.extend(f"{k}: {_format_value(v)}".rstrip() for k, v in pending.items())
    return "---\n" + "\n".join(out) + "\n---\n" + text[m.end():]


# ---------------------------------------------------------------- notes

def strip_code(text: str) -> str:
    text = COMMENT_RE.sub("", text)
    text = FENCE_RE.sub("", text)
    return INLINE_CODE_RE.sub("", text)


def extract_links(text: str) -> list[tuple[str, bool]]:
    """[(target, is_embed)] for every wikilink outside code and comments."""
    return [(m.group(2).strip(), m.group(1) == "!") for m in LINK_RE.finditer(strip_code(text))]


def as_list(value) -> list:
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


@dataclass
class Note:
    path: Path
    rel: str
    stem: str
    folder: str
    fm: dict
    body: str
    has_frontmatter: bool
    mtime: float
    text: str = field(repr=False, default="")

    @property
    def type(self) -> str:
        return str(self.fm.get("type", "")).strip()

    @property
    def status(self) -> str:
        return str(self.fm.get("status", "")).strip()

    @property
    def title(self) -> str:
        m = H1_RE.search(self.body)
        return m.group(1).strip() if m else self.stem.replace("-", " ")

    @property
    def tags(self) -> list:
        return as_list(self.fm.get("tags"))

    @property
    def aliases(self) -> list:
        return as_list(self.fm.get("aliases"))

    @property
    def summary(self) -> str:
        """frontmatter summary, else the first prose paragraph after the title."""
        s = str(self.fm.get("summary", "") or "").strip()
        if s:
            return s
        body = H1_RE.sub("", strip_code(self.body), count=1)
        for para in re.split(r"\n\s*\n", body):
            p = para.strip()
            if p and not p.startswith(("#", "-", "|", ">", "*", "1.")) and "(fill in)" not in p:
                return re.sub(r"\s+", " ", p)[:300]
        return ""

    @property
    def links(self) -> list[str]:
        return [t.split("/")[-1] for t, embed in extract_links(self.body) if not embed]

    @property
    def pinned(self) -> bool:
        """Pinned notes load in every wake-up pack and never show as fading."""
        return str(self.fm.get("pinned", "")).strip().lower() in ("true", "yes", "1")

    @property
    def archived(self) -> bool:
        return self.folder == ARCHIVE or self.status in ("archived", "superseded")


def folder_of(rel: str) -> str:
    return rel.split("/", 1)[0] if "/" in rel else ""


def load_note(path: Path, root: Path = ROOT) -> Note:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body, had = parse_frontmatter(text)
    rel = path.relative_to(root).as_posix()
    return Note(path=path, rel=rel, stem=path.stem, folder=folder_of(rel), fm=fm,
                body=body, has_frontmatter=had, mtime=path.stat().st_mtime, text=text)


def iter_note_paths(root: Path = ROOT, include_archive: bool = True,
                    include_meta: bool = True) -> Iterator[Path]:
    folders = list(LIVE_FOLDERS)
    if include_archive:
        folders.append(ARCHIVE)
    if include_meta:
        folders.append(META)
    for folder in folders:
        base = root / folder
        if not base.is_dir():
            continue
        for dp, dns, fns in os.walk(base):
            dns[:] = sorted(d for d in dns if not d.startswith("."))
            for fn in sorted(fns):
                if fn.endswith(".md") and not fn.startswith("."):
                    yield Path(dp) / fn


def load_all(root: Path = ROOT, include_archive: bool = True,
             include_meta: bool = True) -> list[Note]:
    return [load_note(p, root) for p in iter_note_paths(root, include_archive, include_meta)]


def resolve(ref: str, root: Path = ROOT) -> Optional[Path]:
    """Find a note by stem, wikilink text, or vault-relative path."""
    ref = ref.strip()
    m = re.fullmatch(r"\[\[([^\]\|#]+)(?:[#|][^\]]*)?\]\]", ref)
    if m:
        ref = m.group(1).strip()
    if ref.endswith(".md") or "/" in ref:
        cand = (root / ref).resolve()
        if not ref.endswith(".md"):
            cand = cand.with_suffix(".md")
        if is_inside(cand, root) and cand.is_file():
            return cand
        ref = Path(ref).stem
    stem = ref.lower() if STEM_RE.match(ref.lower()) else slugify(ref)
    live = [p for p in iter_note_paths(root, include_archive=False) if p.stem == stem]
    if live:
        return live[0]
    archived = [p for p in iter_note_paths(root) if p.stem == stem]
    return archived[0] if archived else None


def is_inside(path: Path, root: Path = ROOT) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def render_template(name: str, title: str, root: Path = ROOT) -> str:
    """Fill an Obsidian core template ({{date}}, {{title}}, {{time}})."""
    tpl = (root / TEMPLATES / f"{name}.md").read_text(encoding="utf-8")
    now = datetime.datetime.now()
    return (tpl.replace("{{date}}", now.date().isoformat())
               .replace("{{time}}", now.strftime("%H:%M"))
               .replace("{{title}}", title))
