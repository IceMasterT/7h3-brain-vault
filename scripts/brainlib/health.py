"""Vault health check. Read-only. Errors break the rules; warnings need a look."""
from __future__ import annotations

import datetime
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import policy
from .facts import malformed_fact_lines
from .index import open_index
from .vault import (
    ANCHORS, ARCHIVE, CONFIDENCE, INBOX, JOURNAL, META, META_TYPES, NEEDS_SUMMARY,
    NEEDS_VERIFIED, PROJECTS, REQUIRED_KEYS, ROOT, STATUSES, STEM_RE, TYPES,
    extract_links, load_all,
)

STALE_DAYS = 90
INBOX_MAX_AGE_DAYS = 7
NOW_MAX_LINES = 30
MAP_MAX_LINES = 200
SKIP_DIRS = {".git", ".brain", ".obsidian", ".trash", "node_modules", "__pycache__"}

CHECKS = {
    # key: (severity, title)
    "naming": ("error", "file naming"),
    "duplicate_names": ("error", "duplicate note names"),
    "missing_frontmatter": ("error", "missing or invalid frontmatter"),
    "broken_links": ("error", "broken links"),
    "secrets": ("error", "secret-looking content"),
    "superseded": ("error", "superseded notes without a valid successor"),
    "conflicts": ("warning", "possible fact conflicts (same subject and predicate, overlapping dates)"),
    "bad_facts": ("warning", "lines in a Facts section that do not parse"),
    "stale": ("warning", f"not verified in {STALE_DAYS} days"),
    "review_due": ("warning", "review_after date passed"),
    "missing_summary": ("warning", "missing summary"),
    "orphans": ("warning", "orphans (nothing links here)"),
    "not_in_index": ("warning", "not listed in _meta/index.md"),
    "style": ("warning", "house style"),
    "inbox_age": ("warning", f"inbox items older than {INBOX_MAX_AGE_DAYS} days"),
    "size": ("warning", "always-loaded files over budget"),
}


@dataclass
class Report:
    notes: int = 0
    inbox: int = 0
    map_lines: int = 0
    problems: dict = field(default_factory=lambda: {k: [] for k in CHECKS})

    def count(self, severity: str) -> int:
        return sum(len(v) for k, v in self.problems.items() if CHECKS[k][0] == severity)

    @property
    def errors(self) -> int:
        return self.count("error")

    @property
    def warnings(self) -> int:
        return self.count("warning")

    def brief(self) -> str:
        msg = (f"Vault health: {self.notes} notes, {self.errors} errors, "
               f"{self.warnings} warnings, {self.inbox} in inbox.")
        if self.problems["size"]:
            msg += " Always-loaded files over budget."
        return msg

    def markdown(self) -> str:
        d = datetime.date.today().isoformat()
        lines = ["---", "type: report", "status: active", f"created: {d}", f"updated: {d}", "---",
                 f"# Vault health ({d})", "",
                 f"- Notes: {self.notes}", f"- Inbox: {self.inbox}",
                 f"- AGENTS.md + CLAUDE.md lines: {self.map_lines} (budget {MAP_MAX_LINES})",
                 f"- Errors: {self.errors}", f"- Warnings: {self.warnings}", ""]
        for key, items in self.problems.items():
            sev, title = CHECKS[key]
            lines.append(f"## {title} ({len(items)}, {sev})")
            lines.extend(f"- {i}" for i in items) if items else lines.append("- none")
            lines.append("")
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {"notes": self.notes, "inbox": self.inbox, "errors": self.errors,
                "warnings": self.warnings, "map_lines": self.map_lines,
                "problems": {k: v for k, v in self.problems.items() if v}}


def _date(value) -> "datetime.date | None":
    try:
        return datetime.date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _attachment_names(root: Path) -> set[str]:
    names = set()
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        names.update(fns)
    return names


def run(root: Path = ROOT) -> Report:
    rep = Report()
    p = rep.problems
    today = datetime.date.today()
    notes = load_all(root)
    stems = defaultdict(list)
    for n in notes:
        stems[n.stem].append(n.rel)
    attachments = None
    inbound: dict = defaultdict(set)

    index_text = ""
    idx = root / META / "index.md"
    if idx.exists():
        index_text = idx.read_text(encoding="utf-8")

    for n in notes:
        in_archive = n.folder == ARCHIVE
        in_meta = n.folder == META
        if not in_archive and not in_meta:
            rep.notes += 1
        if n.folder == INBOX:
            rep.inbox += 1
            created = _date(n.fm.get("created", "")) or datetime.date.fromtimestamp(n.mtime)
            if (today - created).days > INBOX_MAX_AGE_DAYS:
                p["inbox_age"].append(f"{n.rel} ({(today - created).days} days)")

        if not STEM_RE.match(n.stem) and not in_archive:
            p["naming"].append(f"{n.rel} (use lowercase-with-hyphens.md)")

        label = policy.find_secret(n.text)
        if label:
            p["secrets"].append(f"{n.rel} (looks like {policy._a(label)})")

        for target, embed in extract_links(n.body):
            stem = target.split("/")[-1]
            if embed or re.search(r"\.(?!md$)[A-Za-z0-9]{1,5}$", stem):
                if attachments is None:
                    attachments = _attachment_names(root)
                if stem not in attachments and f"{stem}.md" not in attachments:
                    p["broken_links"].append(f"{n.rel} -> ![[{stem}]] (attachment not found)")
                continue
            stem = stem[:-3] if stem.endswith(".md") else stem
            if stem in stems:
                inbound[stem].add(n.stem)
            elif not in_archive:
                p["broken_links"].append(f"{n.rel} -> [[{stem}]]")

        if n.folder in (INBOX, ARCHIVE):
            continue

        # Frontmatter
        if not n.has_frontmatter:
            p["missing_frontmatter"].append(f"{n.rel} (no frontmatter)")
            continue
        missing = [k for k in REQUIRED_KEYS if not str(n.fm.get(k, "")).strip()]
        if n.type in NEEDS_VERIFIED and not n.fm.get("last_verified"):
            missing.append("last_verified")
        if missing:
            p["missing_frontmatter"].append(f"{n.rel} (missing {', '.join(missing)})")
        if n.type and n.type not in TYPES and n.type not in META_TYPES:
            p["missing_frontmatter"].append(f"{n.rel} (unknown type {n.type!r})")
        if n.status and n.status not in STATUSES:
            p["missing_frontmatter"].append(f"{n.rel} (unknown status {n.status!r})")
        conf = str(n.fm.get("confidence", "")).strip()
        if conf and conf not in CONFIDENCE:
            p["missing_frontmatter"].append(f"{n.rel} (confidence must be high, medium or low)")
        for key in ("created", "updated", "last_verified", "review_after"):
            if n.fm.get(key) and not _date(n.fm[key]):
                p["missing_frontmatter"].append(f"{n.rel} (bad {key} date {n.fm[key]!r})")

        lv = _date(n.fm.get("last_verified", ""))
        if lv and (today - lv).days > STALE_DAYS and n.status not in ("superseded", "archived"):
            p["stale"].append(f"{n.rel} (verified {lv})")
        ra = _date(n.fm.get("review_after", ""))
        if ra and ra < today:
            p["review_due"].append(f"{n.rel} (review after {ra})")

        if n.type in NEEDS_SUMMARY and not str(n.fm.get("summary", "")).strip() and n.stem not in ANCHORS:
            p["missing_summary"].append(n.rel)

        succ = str(n.fm.get("superseded_by", "")).strip()
        if n.status == "superseded" or succ:
            target = re.sub(r"^\[\[|\]\]$", "", succ).split("|")[0].strip()
            if not target or target not in stems:
                p["superseded"].append(f"{n.rel} (superseded_by {succ or 'missing'})")
            elif n.status != "superseded":
                p["superseded"].append(f"{n.rel} (has superseded_by but status is {n.status!r})")

        for line in malformed_fact_lines(n.body):
            p["bad_facts"].append(f"{n.rel}: {line} (use subject | predicate | object | from | to)")

        if policy.EM_DASH in n.text:
            p["style"].append(f"{n.rel} (em dash)")

        if (not in_meta and n.folder != JOURNAL and n.type in ("note", "source", "person", "project", "draft")
                and n.stem not in ANCHORS and f"[[{n.stem}]]" not in index_text):
            p["not_in_index"].append(n.rel)

    for stem, rels in stems.items():
        live = [r for r in rels if not r.startswith(ARCHIVE + "/")]
        if len(live) > 1:
            p["duplicate_names"].append(f"{stem}: {', '.join(live)} (wikilinks become ambiguous)")

    for n in notes:
        if n.folder in (INBOX, ARCHIVE, META, JOURNAL) or n.stem in ANCHORS:
            continue
        if not (inbound.get(n.stem, set()) - {n.stem}):
            p["orphans"].append(n.rel)

    idx = open_index(root)
    try:
        for a, b in idx.conflicts():
            p["conflicts"].append(f"{a.text()} vs {b.text()}")
    finally:
        idx.close()

    for name in ("AGENTS.md", "CLAUDE.md"):
        f = root / name
        if f.exists():
            rep.map_lines += len(f.read_text(encoding="utf-8").splitlines())
    if rep.map_lines > MAP_MAX_LINES:
        p["size"].append(f"AGENTS.md + CLAUDE.md are {rep.map_lines} lines (budget {MAP_MAX_LINES})")
    now = root / PROJECTS / "now.md"
    if now.exists():
        n_lines = len(now.read_text(encoding="utf-8").splitlines())
        if n_lines > NOW_MAX_LINES + 10:  # frontmatter allowance
            p["size"].append(f"30-projects/now.md is {n_lines} lines (keep the list under {NOW_MAX_LINES})")

    for k in p:
        p[k].sort()
    return rep
