"""Dated facts: small, checkable claims with a validity window.

A note may hold a "## Facts" section with one fact per line:

    - Alice | works at | Acme | 2024-03 | 2026-01
    - Alice | works at | Globex | 2026-01

Fields are subject | predicate | object | valid from | valid to. Dates are
YYYY, YYYY-MM or YYYY-MM-DD and both are optional; an empty "to" means still
true. When a fact stops being true, fill in its "to" date instead of deleting
the line, so the vault can answer "what was true on <date>?". Two facts with the
same subject and predicate, different objects and overlapping dates are
reported as a possible conflict by the health check.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DATE_RE = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")
FACTS_SECTION_RE = re.compile(r"^##[ \t]+Facts[ \t]*$(.*?)(?=^#{1,2}[ \t]|\Z)", re.M | re.S | re.I)


def _lo(d: str) -> str:
    """Earliest full date a partial date can mean."""
    if not d:
        return "0000-01-01"
    return d + {4: "-01-01", 7: "-01"}.get(len(d), "")


def _hi(d: str) -> str:
    """Latest full date a partial date can mean (day 31 is fine for comparison)."""
    if not d:
        return "9999-12-31"
    return d + {4: "-12-31", 7: "-31"}.get(len(d), "")


@dataclass
class Fact:
    subject: str
    predicate: str
    object: str
    valid_from: str = ""
    valid_to: str = ""
    line: str = ""
    note: str = ""

    def true_on(self, date: str) -> bool:
        started = _lo(self.valid_from) <= _hi(date)
        not_ended = not self.valid_to or _lo(date) < _lo(self.valid_to)  # "to" is exclusive
        return started and not_ended

    def as_dict(self) -> dict:
        return {"subject": self.subject, "predicate": self.predicate, "object": self.object,
                "from": self.valid_from or None, "to": self.valid_to or None, "note": self.note}

    def text(self) -> str:
        span = ""
        if self.valid_from or self.valid_to:
            span = f" ({self.valid_from or '?'} to {self.valid_to or 'now'})"
        return f"{self.subject} {self.predicate} {self.object}{span} [[{self.note}]]"


def overlaps(a: Fact, b: Fact) -> bool:
    """True when the two validity windows share any time.

    An end date is exclusive: a fact that ends in 2026-01 and one that starts in
    2026-01 describe a handover, not a contradiction.
    """
    a_end = _lo(a.valid_to) if a.valid_to else "9999-12-31"
    b_end = _lo(b.valid_to) if b.valid_to else "9999-12-31"
    return _lo(a.valid_from) < b_end and _lo(b.valid_from) < a_end


def parse_facts(body: str) -> list[Fact]:
    out: list[Fact] = []
    for section in FACTS_SECTION_RE.findall(body):
        for raw in section.splitlines():
            m = re.match(r"^\s*[-*]\s+(.+)$", raw)
            if not m or "|" not in m.group(1):
                continue
            parts = [p.strip() for p in m.group(1).split("|")]
            if len(parts) < 3 or not all(parts[:3]):
                continue
            frm = parts[3] if len(parts) > 3 else ""
            to = parts[4] if len(parts) > 4 else ""
            if (frm and not DATE_RE.match(frm)) or (to and not DATE_RE.match(to)):
                continue
            out.append(Fact(parts[0], parts[1], parts[2], frm, to, m.group(1).strip()))
    return out


def malformed_fact_lines(body: str) -> list[str]:
    """Lines in a Facts section that look like facts but do not parse."""
    bad = []
    for section in FACTS_SECTION_RE.findall(body):
        for raw in section.splitlines():
            m = re.match(r"^\s*[-*]\s+(.+)$", raw)
            if not m:
                continue
            if not parse_facts("## Facts\n" + raw + "\n"):
                bad.append(m.group(1).strip())
    return bad
