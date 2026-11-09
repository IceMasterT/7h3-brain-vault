#!/usr/bin/env python3
"""PreToolUse guard for Claude Code and pre_tool_call guard for Hermes Agent.

Hard enforcement, unlike AGENTS.md / CLAUDE.md which are only context.
Exit 2 blocks the tool call and shows stderr to the model (both tools honour it).
The rules themselves live in scripts/brainlib/policy.py, shared with the MCP
server and the CLI, so every AI meets the same limits.

Hermes hooks are global, so the guard only acts when a tool call targets the
vault (its working dir or a path inside it). If the policy cannot be loaded
the guard fails closed.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VAULT = os.path.dirname(os.path.dirname(HERE))


def block(msg: str) -> None:
    print(f"BLOCKED by vault guard: {msg}", file=sys.stderr)
    sys.exit(2)


try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

os.environ.setdefault("BRAIN_VAULT", VAULT)
try:
    sys.path.insert(0, os.path.join(VAULT, "scripts"))
    from brainlib import policy
    from brainlib.vault import ROOT
except Exception as e:  # a guard that cannot load must not wave writes through
    block(f"guard policy failed to load ({e.__class__.__name__}: {e}). Fix scripts/brainlib.")

tool = data.get("tool_name") or ""
inp = data.get("tool_input") or {}
cwd = data.get("cwd") or os.getcwd()

if tool in ("Bash", "terminal"):
    cmd = inp.get("command", "") or ""
    workdir = inp.get("workdir") or cwd
    if not policy.touches_vault([workdir], workdir, ROOT) and str(ROOT) not in cmd:
        sys.exit(0)  # a command elsewhere on the machine: not this guard's business
    reason = policy.check_command(cmd, workdir, ROOT)
    if reason:
        block(reason)
    sys.exit(0)

if tool in ("Write", "Edit", "MultiEdit", "write_file", "patch"):
    path = inp.get("file_path") or inp.get("path") or ""
    if not policy.touches_vault([path], None if os.path.isabs(path) else cwd, ROOT):
        sys.exit(0)
    reason = policy.check_write_path(path, ROOT)
    if reason:
        block(reason)
    if tool == "MultiEdit":
        text = "\n".join(e.get("new_string", "") for e in inp.get("edits", []) or [])
    else:
        text = inp.get("content") or inp.get("new_string") or inp.get("patch") or ""
    reason = policy.check_content(text, path)
    if reason:
        block(reason)

sys.exit(0)
