"""doctor (check and repair the install) and connect (config for each AI tool)."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from .vault import LIVE_FOLDERS, ARCHIVE, META, ROOT

PY = "python3" if os.name != "nt" else "python"


def _q(p: Path) -> str:
    return shlex.quote(str(p))


def _paths(root: Path) -> dict:
    return {
        "server": root / "scripts" / "mcp_server.py",
        "brain": root / "scripts" / "brain.py",
        "guard": root / ".claude" / "hooks" / "guard.py",
        "recall": root / ".claude" / "hooks" / "recall.py",
        "skills": root / ".agents" / "skills",
    }


# ---------------------------------------------------------------- connect

def connect(target: str, root: Path = ROOT) -> str:
    p = _paths(root)
    server_args = [str(p["server"]), "--agent", target]
    if target == "hermes":
        return f"""# Merge into ~/.hermes/config.yaml (add under the existing top-level keys
# if they are already there; do not create duplicates). Then restart Hermes.

mcp_servers:
  brain:
    command: "{PY}"
    args: {json.dumps(server_args)}
    timeout: 60

skills:
  # Vault skills in every Hermes session, wherever you start it:
  external_dirs:
    - "{p['skills']}"
  # Or, only when Hermes runs inside the vault (it is a git repo):
  trusted_project_dirs:
    - "{root}"

hooks:
  # Same safety guard as Claude Code. Only acts on paths inside the vault.
  pre_tool_call:
    - matcher: "terminal|write_file|patch"
      command: "{PY} {_q(p['guard'])}"
      timeout: 10
      fail_closed: true
  # Per-turn recall: injects matching vault notes into the user turn.
  pre_llm_call:
    - command: "{PY} {_q(p['recall'])}"
      timeout: 10

# Hermes asks once per hook to approve it. Check with: hermes hooks list
"""
    if target in ("claude-desktop", "lm-studio", "generic-json"):
        cfg = {"mcpServers": {"brain": {"command": PY, "args": server_args}}}
        where = {
            "claude-desktop": "Claude Desktop: Settings > Developer > Edit Config (claude_desktop_config.json)",
            "lm-studio": "LM Studio: Program tab > Install > Edit mcp.json",
            "generic-json": "Any client that uses the mcpServers JSON shape",
        }[target]
        return f"// {where}. Merge into the existing mcpServers object.\n" + json.dumps(cfg, indent=2)
    if target == "cursor":
        return ("// .cursor/mcp.json ships in the vault and uses ${workspaceFolder}.\n"
                "// For use from other projects, add to ~/.cursor/mcp.json:\n"
                + json.dumps({"mcpServers": {"brain": {"command": PY, "args": server_args}}}, indent=2))
    if target == "codex":
        return ("# ~/.codex/config.toml\n[mcp_servers.brain]\n"
                f'command = "{PY}"\nargs = {json.dumps(server_args)}\n')
    if target == "gemini":
        return ("// ~/.gemini/settings.json (or .gemini/settings.json in a project)\n"
                + json.dumps({"mcpServers": {"brain": {"command": PY, "args": server_args}}}, indent=2))
    if target == "claude-code":
        return ("# Inside the vault nothing is needed: .mcp.json, hooks and skills load automatically.\n"
                "# To use the brain from any other project:\n"
                f"claude mcp add --scope user brain -- {PY} {_q(p['server'])} --agent claude-code\n")
    raise ValueError("target must be one of: hermes, claude-code, claude-desktop, cursor, codex, gemini, lm-studio, generic-json")


CONNECT_TARGETS = ["hermes", "claude-code", "claude-desktop", "cursor", "codex", "gemini", "lm-studio", "generic-json"]


# ---------------------------------------------------------------- doctor

def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def doctor(root: Path = ROOT, fix: bool = False) -> tuple[list[tuple[str, str, str]], int]:
    """[(status, check, detail)], number of failures. status: ok | fixed | warn | fail."""
    rows: list[tuple[str, str, str]] = []
    fails = 0

    def add(status: str, check: str, detail: str = "") -> None:
        nonlocal fails
        rows.append((status, check, detail))
        fails += status == "fail"

    add("ok" if sys.version_info >= (3, 9) else "fail", "Python 3.9+", sys.version.split()[0])
    try:
        sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        add("ok", "SQLite FTS5", sqlite3.sqlite_version)
    except sqlite3.OperationalError:
        add("fail", "SQLite FTS5", "this Python's SQLite lacks FTS5; install a current Python")

    missing = [f for f in (*LIVE_FOLDERS, ARCHIVE, f"{ARCHIVE}/inbox-processed", f"{ARCHIVE}/attachments")
               if not (root / f).is_dir()]
    if missing and fix:
        for f in missing:
            (root / f).mkdir(parents=True, exist_ok=True)
        add("fixed", "Vault folders", "created " + ", ".join(missing))
    else:
        add("ok" if not missing else "fail", "Vault folders", "missing: " + ", ".join(missing) if missing else "")

    # Claude Code reads .claude/skills/<name>; the shared copy lives in .agents/skills/<name>.
    src = root / ".agents" / "skills"
    dst = root / ".claude" / "skills"
    bad = []
    for skill in sorted(d for d in src.iterdir() if (d / "SKILL.md").exists()) if src.is_dir() else []:
        link = dst / skill.name
        target = Path("..") / ".." / ".agents" / "skills" / skill.name
        if link.is_symlink() and link.resolve() == skill.resolve():
            continue
        if fix:
            dst.mkdir(parents=True, exist_ok=True)
            if link.is_symlink() or link.is_file():
                link.unlink()
            elif link.is_dir():
                shutil.rmtree(link)  # a stale copy of a shared skill, regenerated below
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError:
                shutil.copytree(skill, link)  # no symlink support (Windows without dev mode)
        bad.append(skill.name)
    if bad:
        add("fixed" if fix else "fail", "Claude Code skill links",
            ("linked " if fix else "not linked: ") + ", ".join(bad) + ("" if fix else " (run doctor --fix)"))
    else:
        add("ok", "Claude Code skill links", "all skills shared from .agents/skills")

    if shutil.which("git"):
        if _git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
            if fix:
                _git(root, "init", "-q")
                add("fixed", "Git repository", "initialised")
            else:
                add("warn", "Git repository", "not a git repo: no history, Hermes project skills need one")
        if _git(root, "rev-parse", "--is-inside-work-tree").returncode == 0:
            hp = _git(root, "config", "core.hooksPath").stdout.strip()
            if hp != ".githooks":
                if fix:
                    _git(root, "config", "core.hooksPath", ".githooks")
                    add("fixed", "Git pre-commit check", "core.hooksPath set to .githooks")
                else:
                    add("warn", "Git pre-commit check", "run doctor --fix to block secrets at commit time")
            else:
                add("ok", "Git pre-commit check", ".githooks active")
    else:
        add("warn", "Git", "git not installed: no history or pre-commit check")

    for hook in sorted((root / ".claude" / "hooks").glob("*")) + sorted((root / ".githooks").glob("*")):
        if hook.is_file() and not os.access(hook, os.X_OK):
            if fix:
                hook.chmod(hook.stat().st_mode | 0o111)
                add("fixed", f"Executable {hook.relative_to(root)}")
            else:
                add("warn", f"Executable {hook.relative_to(root)}", "not executable")

    from .index import open_index
    idx = open_index(root)
    try:
        n = idx.db.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        add("ok", "Search index", f"{n} files indexed in .brain/index.sqlite")
    finally:
        idx.close()

    ident = root / META / "identity.md"
    if ident.exists() and "(fill in)" in ident.read_text(encoding="utf-8"):
        add("warn", "Identity", "fill in _meta/identity.md so every AI knows who you are")

    hermes_cfg = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "config.yaml"
    if hermes_cfg.exists():
        text = hermes_cfg.read_text(encoding="utf-8", errors="replace")
        if str(root / "scripts" / "mcp_server.py") in text:
            add("ok", "Hermes Agent", "brain MCP server is configured")
        else:
            add("warn", "Hermes Agent", "installed but not connected: run brain.py connect hermes")
    return rows, fails
