"""Rule-based triage hints for inbox captures. No model, no network.

Each capture is scored against marker phrases per destination. The highest
score wins; confidence = min(1, score / 5) and anything under 0.3 falls back
to "note". These are suggestions for the triage-inbox skill, never actions.
(Scoring adapted from mempalace's general_extractor.)
"""
from __future__ import annotations

import re
from pathlib import Path

from .index import open_index
from .vault import INBOX, ROOT, iter_note_paths, load_note

MARKERS = {
    "decision": [r"\bdecided\b", r"\bdecision\b", r"\bwe(?:'ll| will) go with\b", r"\bchose\b",
                 r"\bgoing with\b", r"\blet'?s use\b", r"\bagreed\b", r"\binstead of\b", r"\bsettled on\b"],
    "person": [r"\b(?i:met)(?: (?i:with))? [A-Z][a-z]+", r"(?i)\bcall with\b", r"(?i)\bemail(?:ed)? (?:from|to)\b",
               r"(?i)\bphone\b", r"(?i)\bintroduced\b", r"(?i)\b(?:she|he|his|her)\b", r"(?i)\bworks at\b",
               r"(?i)\bbirthday\b"],
    "project": [r"\bdeadline\b", r"\bmilestone\b", r"\bship(?:ped|ping)?\b", r"\blaunch\b",
                r"\bnext step\b", r"\btodo\b|\bto-do\b", r"\bblocked\b", r"\bsprint\b", r"\brelease\b"],
    "source": [r"https?://", r"\barxiv\b", r"\bpaper\b", r"\bbook\b", r"\barticle\b", r"\bpodcast\b",
               r"\bvideo\b", r"\bquote\b", r"\baccording to\b"],
    "preference": [r"\bI prefer\b", r"\bI (?:really )?(?:like|love|hate|dislike)\b", r"\balways\b",
                   r"\bnever\b", r"\bmy favou?rite\b", r"\bdon'?t (?:ever )?use\b"],
}
COMPILED = {k: [re.compile(p, re.I if k != "person" else 0) for p in v] for k, v in MARKERS.items()}
DESTINATION = {
    "decision": "decision via capture-decision",
    "person": "person card in 20-people/",
    "project": "update a project in 30-projects/",
    "source": "source note in 10-notes/",
    "preference": "preference: identity.md or a note in 10-notes/",
    "note": "note in 10-notes/",
}


def classify(text: str) -> tuple[str, float]:
    scores = {k: sum(1 for rx in rxs if rx.search(text)) for k, rxs in COMPILED.items()}
    kind = max(scores, key=scores.get)
    score = scores[kind]
    if score:
        score += 2 if len(text) > 500 else 1 if len(text) > 200 else 0
    confidence = min(1.0, score / 5)
    if confidence < 0.3:
        return "note", round(confidence, 2)
    return kind, round(confidence, 2)


def suggest(root: Path = ROOT) -> list[dict]:
    out = []
    idx = open_index(root)
    try:
        for path in iter_note_paths(root, include_archive=False, include_meta=False):
            rel = path.relative_to(root).as_posix()
            if not rel.startswith(INBOX + "/"):
                continue
            n = load_note(path, root)
            kind, conf = classify(n.body)
            similar = [h.stem for h in idx.search(n.body[:400], limit=4)
                       if not h.rel.startswith(INBOX + "/")][:3]
            out.append({"file": rel, "suggested": DESTINATION[kind], "kind": kind,
                        "confidence": conf, "possible_existing_notes": similar})
    finally:
        idx.close()
    return out
