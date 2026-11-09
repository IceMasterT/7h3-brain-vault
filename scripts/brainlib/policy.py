"""Safety policy shared by every writer: hooks, MCP tools, the CLI and chat.

check_* functions return None when the action is allowed, or a short reason
string when it must be blocked. They never raise on odd input.
"""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Iterable, Iterator, Optional

from .vault import ARCHIVE, ROOT, is_inside

SECRET_PATTERNS = [
    (r"sk-ant-[A-Za-z0-9_\-]{20,}", "Anthropic API key"),
    (r"\bsk-(?:proj-|live-|test-)?[A-Za-z0-9_\-]{20,}", "API key (sk-...)"),
    (r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}", "Stripe live key"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key"),
    (r"\bASIA[0-9A-Z]{16}\b", "AWS temporary access key"),
    (r"\bgh[pousr]_[A-Za-z0-9]{30,}", "GitHub token"),
    (r"\bgithub_pat_[A-Za-z0-9_]{40,}", "GitHub fine-grained token"),
    (r"\bglpat-[A-Za-z0-9_\-]{20,}", "GitLab token"),
    (r"\bxox[abprs]-[A-Za-z0-9\-]{10,}", "Slack token"),
    (r"\bAIza[0-9A-Za-z_\-]{35}\b", "Google API key"),
    (r"\bhf_[A-Za-z0-9]{30,}", "Hugging Face token"),
    (r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}", "JWT"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "SSN-shaped number"),
    (r"(?i)\b(?:password|passwd|pwd|passphrase)\s*[:=]\s*\S{4,}", "password assignment"),
    # Real keys contain digits; identifiers like api_key_from_env do not.
    (r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"]?"
     r"(?=[A-Za-z_\-]*\d)[A-Za-z0-9_\-]{16,}", "credential assignment"),
]
_SECRET_RES = [(re.compile(p), label) for p, label in SECRET_PATTERNS]
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")

EM_DASH = "—"

# The guard's own rules are protected too, or an AI could edit its way past them.
PROTECTED = (".claude/hooks/", ".claude/settings.json", ".githooks/", "scripts/brainlib/policy.py")
PRIVATE = ("CLAUDE.local.md", ".env")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alt = not alt
    return total % 10 == 0


def _a(label: str) -> str:
    return ("an " if label[0].lower() in "aeiou" else "a ") + label


def find_secret(text: str) -> Optional[str]:
    """Label of the first secret-looking thing in text, or None."""
    if not text:
        return None
    for rx, label in _SECRET_RES:
        if rx.search(text):
            return label
    for m in _CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and len(set(digits)) > 1 and _luhn_ok(digits):
            return "payment card number"
    return None


def check_content(text: str, path: str = "") -> Optional[str]:
    """Rules for any text written into the vault."""
    label = find_secret(text)
    if label:
        return f"content looks like {_a(label)}. Secrets never go in the vault."
    if EM_DASH in text and (not path or path.endswith(".md")):
        return "em dash found. House style forbids em dashes. Rewrite with commas, periods or colons."
    return None


def check_write_path(path: str, root: Path = ROOT) -> Optional[str]:
    """Rules for which vault files an AI may write."""
    norm = path.replace("\\", "/")
    if any(p in norm for p in PROTECTED):
        return "hooks, settings, git hooks and the guard policy are protected. Ask the user to edit them."
    base = norm.rsplit("/", 1)[-1]
    if base in PRIVATE or base.startswith(".env"):
        return "private files are off limits."
    return None


# ---------------------------------------------------------------- shell

_SEGMENT_SPLIT = re.compile(r"\|\||&&|;|\||\n|&(?!>)")
_REDIRECT_TO = re.compile(r">>?\s*(\S+)")

DELETERS = {"rm", "unlink", "shred", "srm", "wipe"}
NETWORK = {"curl", "wget", "scp", "sftp", "rsync", "nc", "ncat", "netcat", "ftp", "telnet", "ssh", "aria2c"}
PRIVILEGE = {"sudo", "doas", "su", "pkexec", "runas"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
WRITERS = {"tee", "truncate", "chmod", "chown", "ln", "cp", "mv", "install", "dd", "touch"}
# Wrappers that run the command after them. Value: options that take an argument.
WRAPPERS = {
    "env": set(), "nohup": set(), "time": set(), "nice": {"-n"}, "ionice": {"-c", "-n"},
    "command": set(), "builtin": set(), "exec": set(), "stdbuf": set(), "timeout": {"-s", "-k"},
    "xargs": {"-I", "-n", "-P", "-L", "-d", "-s", "-a", "-E"},
}
GIT_GLOBAL_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def _argv(segment: str) -> list[str]:
    try:
        return shlex.split(segment, comments=False)
    except ValueError:  # unbalanced quotes: judge the raw words
        return segment.split()


def _programs(argv: list[str], depth: int = 0) -> Iterator[list[str]]:
    """Every command an argv will run, unwrapping env/xargs/find -exec/sh -c."""
    while argv and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]):
        argv = argv[1:]  # leading VAR=value assignments
    if not argv or depth > 4:
        return
    prog = os.path.basename(argv[0])
    if prog in PRIVILEGE:
        yield argv
        yield from _programs(argv[1:], depth + 1)
        return
    if prog in WRAPPERS:
        i, takes_arg = 1, WRAPPERS[prog]
        while i < len(argv) and argv[i].startswith("-"):
            i += 2 if argv[i] in takes_arg else 1
        if prog == "timeout" and i < len(argv):
            i += 1  # the duration
        if prog == "env":
            while i < len(argv) and "=" in argv[i]:
                i += 1
        yield from _programs(argv[i:], depth + 1)
        return
    if prog in SHELLS and "-c" in argv[1:]:
        k = argv.index("-c")
        if k + 1 < len(argv):
            for seg in _SEGMENT_SPLIT.split(argv[k + 1]):
                yield from _programs(_argv(seg.strip()), depth + 1)
        return
    if prog == "find":
        for i, tok in enumerate(argv):
            if tok in ("-exec", "-execdir", "-ok", "-okdir"):
                sub = []
                for t in argv[i + 1:]:
                    if t in (";", "+"):  # shlex has already unescaped \;
                        break
                    sub.append(t)
                yield from _programs(sub, depth + 1)
    yield argv


def _git_sub(argv: list[str]) -> list[str]:
    i = 1
    while i < len(argv) and argv[i].startswith("-"):
        i += 2 if argv[i] in GIT_GLOBAL_WITH_ARG else 1
    return argv[i:]


def _outside(paths: list[str], cwd: Path, root: Path) -> bool:
    for p in paths:
        target = Path(os.path.expanduser(p))
        if not target.is_absolute():
            target = cwd / target
        if not is_inside(target, root):
            return True
    return False


def _check_program(argv: list[str], cwd: Path, root: Path) -> Optional[str]:
    prog = os.path.basename(argv[0])
    args = argv[1:]
    if prog in DELETERS:
        return f"{prog} is blocked. Move files to {ARCHIVE}/ instead."
    if prog == "rmdir":
        return f"rmdir is blocked. Move folders to {ARCHIVE}/ instead."
    if prog in PRIVILEGE:
        return f"{prog} is blocked."
    if prog in NETWORK:
        return "network transfer commands are blocked in this vault."
    if prog == "find" and "-delete" in args:
        return f"find -delete is blocked. Move files to {ARCHIVE}/."
    if prog == "mv" and _outside([a for a in args if not a.startswith("-")], cwd, root):
        return "moving files outside the vault is blocked."
    if prog == "git":
        sub = _git_sub(argv)
        verb, rest = (sub[0], sub[1:]) if sub else ("", [])
        if verb == "rm":
            return f"git rm is blocked. Move files to {ARCHIVE}/ instead."
        if verb == "clean":
            return "git clean deletes files and is blocked."
        if verb == "push" and any(r in ("-f", "--force", "--force-with-lease") or r.startswith("--force")
                                  or (r.startswith("+") and len(r) > 1) for r in rest):
            return "force push is blocked."
        if verb == "reset" and "--hard" in rest:
            return "hard reset is blocked."
        if verb in ("checkout", "restore") and "." in rest:
            return "discarding all changes is blocked."
        if verb == "mv" and _outside([a for a in rest if not a.startswith("-")], cwd, root):
            return "moving files outside the vault is blocked."
    return None


def _writes_protected(segment: str, argv: list[str]) -> bool:
    if not any(p in segment for p in PROTECTED):
        return False
    if any(any(p in t for p in PROTECTED) for t in _REDIRECT_TO.findall(segment)):
        return True
    progs = [os.path.basename(a[0]) for a in _programs(argv) if a]
    if any(p in WRITERS for p in progs):
        return True
    return any(p in ("sed", "perl") and any(t.startswith("-i") for t in argv) for p in progs)


def check_command(cmd: str, cwd: Optional[str] = None, root: Path = ROOT) -> Optional[str]:
    """Rules for shell commands that run in or touch the vault.

    Judges the programs a command runs (including through env, xargs, find -exec
    and sh -c), not words that merely appear in it, so `grep -r rmdir .` is fine.
    """
    if not cmd:
        return None
    here = Path(cwd).resolve() if cwd else root
    for seg in _segments(cmd):
        argv = _argv(seg)
        for prog_argv in _programs(argv):
            reason = _check_program(prog_argv, here, root)
            if reason:
                return reason
        if _writes_protected(seg, argv):
            return "do not modify hook, settings, git hook or guard policy files."
    if re.search(r">|\btee\b", cmd):
        label = find_secret(cmd)
        if label:
            return f"command writes something that looks like {_a(label)}. Secrets never go in the vault."
        if EM_DASH in cmd and ".md" in cmd:
            return "em dash found. House style forbids em dashes."
    return None


def _segments(cmd: str) -> list[str]:
    return [s.strip() for s in _SEGMENT_SPLIT.split(cmd) if s.strip()]


def touches_vault(paths: Iterable[str], cwd: Optional[str], root: Path = ROOT) -> bool:
    """True when the working dir or any referenced path is inside the vault."""
    if cwd and is_inside(Path(cwd), root):
        return True
    base = Path(cwd) if cwd else Path.cwd()
    for p in paths:
        if not p:
            continue
        cand = Path(os.path.expanduser(p))
        if not cand.is_absolute():
            cand = base / cand
        if is_inside(cand, root):
            return True
    return False


def archive_hint() -> str:
    return f"Move it to {ARCHIVE}/ instead."
