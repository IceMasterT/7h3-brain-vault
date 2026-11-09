"""Append-only, hash-chained log of every AI write to the vault.

Each line of _meta/audit-log.jsonl records who wrote what and the SHA-256 of
the new content, plus the hash of the previous line. Editing or deleting any
past line breaks the chain, which `brain.py audit --verify` reports. Git history
shows what changed; this log shows which agent changed it.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

from .vault import META, ROOT

GENESIS = "0" * 64


def log_path(root: Path = ROOT) -> Path:
    return root / META / "audit-log.jsonl"


@contextmanager
def _locked(f):
    try:
        import fcntl
    except ImportError:  # Windows: single-writer assumption, chain still verifiable
        yield
        return
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _line_hash(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record(action: str, rel: str, content_sha: str = "", detail: str = "", root: Path = ROOT) -> None:
    path = log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as f:
        with _locked(f):
            f.seek(0)
            last = ""
            for line in f:
                if line.strip():
                    last = line.rstrip("\n")
            entry = {
                "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "agent": os.environ.get("BRAIN_AGENT", "") or "unknown",
                "action": action,
                "path": rel,
                "sha256": content_sha,
                "prev": _line_hash(last) if last else GENESIS,
            }
            if detail:
                entry["detail"] = detail
            f.seek(0, os.SEEK_END)
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()


def verify(root: Path = ROOT) -> tuple[bool, str, int]:
    """(ok, message, entries)."""
    path = log_path(root)
    if not path.exists():
        return True, "no audit log yet", 0
    prev = GENESIS
    n = 0
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                return False, f"line {i} is not valid JSON", n
            if entry.get("prev") != prev:
                return False, f"chain broken at line {i}: an earlier entry was changed or removed", n
            prev = _line_hash(line)
            n += 1
    return True, f"chain intact ({n} entries)", n


def tail(limit: int = 20, root: Path = ROOT) -> list[dict]:
    path = log_path(root)
    if not path.exists():
        return []
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [json.loads(l) for l in lines[-limit:]]
