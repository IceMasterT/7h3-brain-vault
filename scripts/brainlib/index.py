"""Full-text search index over the vault (SQLite FTS5, BM25 ranking).

The index lives in .brain/index.sqlite. It is a cache: delete it any time and
it rebuilds from the Markdown files. Refresh is incremental by mtime and size,
so calling it before every search costs a directory walk, not a reindex.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .facts import Fact, overlaps, parse_facts
from .vault import ROOT, Note, iter_note_paths, load_note

SCHEMA_VERSION = 2

STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having
he her here hers herself him himself his how i if in into is it its itself just me more most my myself no
nor not now of off on once only or other our ours ourselves out over own same she should so some such than
that the their theirs them themselves then there these they this those through to too under until up very
was we were what when where which while who whom why will with would you your yours yourself yourselves
let lets please tell show give make get got want need know think like use using used one two may might
must shall yes ok okay hey hi hello thanks thank
""".split())

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-']*[a-z0-9]|[a-z0-9]")


def db_path(root: Path = ROOT) -> Path:
    return root / ".brain" / "index.sqlite"


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def query_terms(text: str, limit: int = 12) -> list[str]:
    """Distinct content words of a query, in order, stopwords dropped."""
    seen: list[str] = []
    for t in tokens(text):
        t = t.strip("-'")
        if len(t) < 2 or t in STOPWORDS or t in seen:
            continue
        seen.append(t)
    return seen[:limit]


@dataclass
class Hit:
    rel: str
    stem: str
    title: str
    type: str
    status: str
    summary: str
    tags: list
    updated: str
    score: float
    coverage: float
    matched: list
    snippet: str = ""

    def as_dict(self) -> dict:
        return {
            "note": self.stem, "path": self.rel, "title": self.title, "type": self.type,
            "status": self.status, "summary": self.summary, "tags": self.tags,
            "updated": self.updated, "score": round(self.score, 3),
            "coverage": round(self.coverage, 2), "matched": self.matched, "snippet": self.snippet,
        }


class Index:
    def __init__(self, root: Path = ROOT):
        self.root = root
        path = db_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()

    # ------------------------------------------------------------ schema
    def _ensure_schema(self) -> None:
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        with self.db:
            self.db.executescript("""
                DROP TABLE IF EXISTS docs;
                DROP TABLE IF EXISTS fts;
                DROP TABLE IF EXISTS links;
                DROP TABLE IF EXISTS facts;
                CREATE TABLE docs (
                    rel TEXT PRIMARY KEY, stem TEXT, folder TEXT, title TEXT, type TEXT,
                    status TEXT, summary TEXT, tags TEXT, aliases TEXT, updated TEXT,
                    last_verified TEXT, confidence TEXT, pinned INTEGER, mtime REAL,
                    size INTEGER, words TEXT
                );
                CREATE INDEX docs_stem ON docs(stem);
                CREATE VIRTUAL TABLE fts USING fts5(
                    rel UNINDEXED, title, aliases, summary, tags, body,
                    tokenize = 'porter unicode61'
                );
                CREATE TABLE links (src TEXT, dst TEXT);
                CREATE INDEX links_dst ON links(dst);
                CREATE INDEX links_src ON links(src);
                CREATE TABLE facts (
                    rel TEXT, stem TEXT, subject TEXT, predicate TEXT, object TEXT,
                    valid_from TEXT, valid_to TEXT, line TEXT
                );
                CREATE INDEX facts_sp ON facts(subject, predicate);
                CREATE INDEX facts_rel ON facts(rel);
                -- Usage survives reindexing: it is about the note, not the file version.
                CREATE TABLE IF NOT EXISTS access (
                    stem TEXT PRIMARY KEY, uses INTEGER NOT NULL DEFAULT 0, last_access REAL
                );
            """)
            self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    # ------------------------------------------------------------ refresh
    def refresh(self) -> dict:
        """Bring the index in line with the files. Returns change counts."""
        known = {r["rel"]: (r["mtime"], r["size"]) for r in
                 self.db.execute("SELECT rel, mtime, size FROM docs")}
        seen = set()
        added = changed = 0
        with self.db:
            for path in iter_note_paths(self.root):
                rel = path.relative_to(self.root).as_posix()
                seen.add(rel)
                st = path.stat()
                if known.get(rel) == (st.st_mtime, st.st_size):
                    continue
                note = load_note(path, self.root)
                self._delete(rel)
                self._insert(note, st.st_size)
                if rel in known:
                    changed += 1
                else:
                    added += 1
            removed = [rel for rel in known if rel not in seen]
            for rel in removed:
                self._delete(rel)
        return {"added": added, "changed": changed, "removed": len(removed)}

    def rebuild(self) -> dict:
        with self.db:
            self.db.execute("DELETE FROM docs")
            self.db.execute("DELETE FROM fts")
            self.db.execute("DELETE FROM links")
            self.db.execute("DELETE FROM facts")
        return self.refresh()

    def _delete(self, rel: str) -> None:
        self.db.execute("DELETE FROM docs WHERE rel=?", (rel,))
        self.db.execute("DELETE FROM fts WHERE rel=?", (rel,))
        self.db.execute("DELETE FROM links WHERE src=?", (rel,))
        self.db.execute("DELETE FROM facts WHERE rel=?", (rel,))

    def _insert(self, note: Note, size: int) -> None:
        fm = note.fm
        body = note.body
        words = " ".join(sorted(set(tokens(" ".join(
            [note.title, " ".join(note.aliases), note.summary, " ".join(note.tags), body])))))
        self.db.execute(
            "INSERT INTO docs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (note.rel, note.stem, note.folder, note.title, note.type, note.status, note.summary,
             json.dumps(note.tags), json.dumps(note.aliases), str(fm.get("updated", "")),
             str(fm.get("last_verified", "")), str(fm.get("confidence", "")), int(note.pinned),
             note.mtime, size, words))
        self.db.execute(
            "INSERT INTO fts (rel, title, aliases, summary, tags, body) VALUES (?,?,?,?,?,?)",
            (note.rel, note.title + " " + note.stem.replace("-", " "), " ".join(note.aliases),
             note.summary, " ".join(note.tags), body))
        self.db.executemany("INSERT INTO links VALUES (?,?)",
                            [(note.rel, dst) for dst in set(note.links)])
        self.db.executemany("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?)",
                            [(note.rel, note.stem, f.subject, f.predicate, f.object,
                              f.valid_from, f.valid_to, f.line) for f in parse_facts(note.body)])

    # ------------------------------------------------------------ queries
    def backlinks(self, stem: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT d.rel, d.stem, d.title, d.summary FROM links l JOIN docs d ON d.rel=l.src "
            "WHERE l.dst=? ORDER BY d.updated DESC", (stem,))
        return [dict(r) for r in rows]

    def outlinks(self, rel: str) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT dst FROM links WHERE src=?", (rel,))]

    def inbound_count(self, stem: str) -> int:
        return self.db.execute("SELECT COUNT(DISTINCT src) FROM links WHERE dst=?", (stem,)).fetchone()[0]

    def recent(self, limit: int = 10, include_archive: bool = False) -> list[dict]:
        where = "" if include_archive else "WHERE folder != '90-archive' AND folder != '_meta'"
        rows = self.db.execute(
            f"SELECT rel, stem, title, type, status, summary, updated FROM docs {where} "
            "ORDER BY mtime DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 8, types: Optional[list] = None,
               folders: Optional[list] = None, include_archive: bool = False,
               min_coverage: float = 0.0) -> list[Hit]:
        terms = query_terms(query)
        if not terms:
            return []
        match = " OR ".join('"' + t.replace('"', "") + '"' + ("*" if len(t) >= 4 else "") for t in terms)
        filters, params = [], [match]
        if not include_archive:
            filters.append("d.folder NOT IN ('90-archive') AND d.status NOT IN ('archived')")
        # Housekeeping pages (index, logs, reports) are not memories; identity is.
        filters.append("(d.folder != '_meta' OR d.stem = 'identity')")
        if types:
            filters.append("d.type IN (%s)" % ",".join("?" * len(types)))
            params.extend(types)
        if folders:
            filters.append("d.folder IN (%s)" % ",".join("?" * len(folders)))
            params.extend(folders)
        where = (" AND " + " AND ".join(filters)) if filters else ""
        sql = (
            "SELECT d.*, bm25(fts, 0.0, 10.0, 8.0, 5.0, 4.0, 1.0) AS rank, "
            "snippet(fts, 5, '**', '**', ' ... ', 12) AS snip "
            "FROM fts JOIN docs d ON d.rel = fts.rel "
            f"WHERE fts MATCH ?{where} ORDER BY rank LIMIT ?"
        )
        params.append(max(limit * 4, 20))
        try:
            rows = self.db.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []
        hits = []
        now = time.time()
        self._uses = {row[0]: row[1] for row in self.db.execute("SELECT stem, uses FROM access")}
        best = max((-r["rank"] for r in rows), default=0.0) or 1.0
        for r in rows:
            words = set(r["words"].split())
            matched = [t for t in terms if t in words or any(w.startswith(t) for w in words if len(t) >= 4)]
            coverage = len(matched) / len(terms)
            if coverage < min_coverage:
                continue
            title_words = set(tokens(r["title"] + " " + r["stem"].replace("-", " ") + " " + r["aliases"]))
            in_title = sum(1 for t in matched if t in title_words) / len(terms)
            age_days = max(0.0, (now - r["mtime"]) / 86400)
            # Blend: text relevance, how much of the question it covers, title hits,
            # freshness and link centrality. Then policy multipliers.
            score = (0.45 * max(0.0, -r["rank"]) / best
                     + 0.30 * coverage
                     + 0.10 * in_title
                     + 0.10 * math.exp(-age_days / 30)
                     + 0.05 * min(1.0, math.log1p(self.inbound_count(r["stem"])) / 3))
            if r["pinned"]:
                score *= 1.2
            if r["confidence"] == "low":
                score *= 0.85
            score *= 1.0 + 0.05 * math.log1p(self._uses.get(r["stem"], 0))  # notes that keep proving useful
            if r["status"] == "superseded":
                score *= 0.3
            if r["folder"] == "00-inbox":
                score *= 0.8
            hits.append(Hit(
                rel=r["rel"], stem=r["stem"], title=r["title"], type=r["type"], status=r["status"],
                summary=r["summary"], tags=json.loads(r["tags"] or "[]"), updated=r["updated"],
                score=score, coverage=coverage, matched=matched,
                snippet=re.sub(r"\s+", " ", r["snip"] or "").strip()))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    # ------------------------------------------------------------ usage
    def record_access(self, stems: list) -> None:
        """Count a note as used. Feeds ranking and the weekly fading-notes list."""
        now = time.time()
        with self.db:
            self.db.executemany(
                "INSERT INTO access (stem, uses, last_access) VALUES (?, 1, ?) "
                "ON CONFLICT(stem) DO UPDATE SET uses = uses + 1, last_access = excluded.last_access",
                [(s, now) for s in dict.fromkeys(stems)])

    def fading(self, days: int = 90, limit: int = 20) -> list[dict]:
        """Live notes nobody has used or edited for `days`: archive candidates, never auto-moved."""
        cutoff = time.time() - days * 86400
        rows = self.db.execute(
            "SELECT d.rel, d.stem, d.type, d.summary, a.uses, a.last_access FROM docs d "
            "LEFT JOIN access a ON a.stem = d.stem "
            "WHERE d.folder IN ('10-notes','20-people','30-projects','40-drafts') AND d.pinned = 0 "
            "AND d.stem NOT IN ('now') AND d.status NOT IN ('archived','superseded') "
            "AND d.mtime < ? AND (a.last_access IS NULL OR a.last_access < ?) "
            "ORDER BY COALESCE(a.last_access, d.mtime) LIMIT ?", (cutoff, cutoff, limit))
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ facts
    def facts(self, subject: str = "", predicate: str = "", as_of: str = "",
              include_superseded: bool = False) -> list[Fact]:
        sql = ("SELECT f.* FROM facts f JOIN docs d ON d.rel = f.rel WHERE d.folder != '90-archive'")
        params: list = []
        if not include_superseded:
            sql += " AND d.status NOT IN ('superseded', 'archived')"
        if subject:
            sql += " AND f.subject = ? COLLATE NOCASE"
            params.append(subject.strip())
        if predicate:
            sql += " AND f.predicate = ? COLLATE NOCASE"
            params.append(predicate.strip())
        out = [Fact(r["subject"], r["predicate"], r["object"], r["valid_from"], r["valid_to"],
                    r["line"], r["stem"]) for r in self.db.execute(sql + " ORDER BY f.valid_from", params)]
        if as_of:
            out = [f for f in out if f.true_on(as_of)]
        return out

    def conflicts(self) -> list[tuple[Fact, Fact]]:
        """Same subject and predicate, different object, overlapping dates."""
        groups: dict = {}
        for f in self.facts():
            groups.setdefault((f.subject.lower(), f.predicate.lower()), []).append(f)
        found = []
        for fs in groups.values():
            for i, a in enumerate(fs):
                for b in fs[i + 1:]:
                    if a.object.lower() != b.object.lower() and overlaps(a, b):
                        found.append((a, b))
        return found

    def close(self) -> None:
        self.db.close()


def open_index(root: Path = ROOT, refresh: bool = True) -> Index:
    idx = Index(root)
    if refresh:
        idx.refresh()
    return idx
