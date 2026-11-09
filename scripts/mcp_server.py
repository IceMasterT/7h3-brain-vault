#!/usr/bin/env python3
"""Second brain MCP server (stdio). Standard library only.

Gives any MCP client (Claude Code, Claude Desktop, Hermes Agent, Cursor,
Codex, Gemini CLI, LM Studio, ...) the same vault tools.

Usage: mcp_server.py [--agent NAME] [--read-only] [--vault PATH]
  --agent      name recorded in the audit log and journal lines (default: mcp)
  --read-only  expose only search and read tools
  --vault      vault root (default: $BRAIN_VAULT, else this script's vault)
"""
import argparse
import json
import os
import sys
import traceback

SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", default=os.environ.get("BRAIN_AGENT") or "mcp")
    ap.add_argument("--read-only", action="store_true")
    ap.add_argument("--vault")
    args = ap.parse_args()
    # Both must be set before brainlib is imported: it resolves them at import time.
    os.environ["BRAIN_AGENT"] = args.agent
    if args.vault:
        os.environ["BRAIN_VAULT"] = args.vault
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from brainlib import __version__
    from brainlib.context import PROTOCOL
    from brainlib.tools import by_name, get_tools
    from brainlib.vault import ROOT

    tools = by_name(args.read_only)
    out = sys.stdout

    def send(msg: dict) -> None:
        out.write(json.dumps(msg, ensure_ascii=False) + "\n")
        out.flush()

    def reply(mid, result=None, error=None) -> None:
        msg = {"jsonrpc": "2.0", "id": mid}
        if error is not None:
            msg["error"] = error
        else:
            msg["result"] = result
        send(msg)

    log = lambda *a: print("[brain-mcp]", *a, file=sys.stderr, flush=True)
    log(f"vault={ROOT} agent={args.agent} read_only={args.read_only} tools={len(tools)}")

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            reply(None, error={"code": -32700, "message": "Parse error"})
            continue
        if isinstance(msg, list):  # batches were removed from MCP; refuse cleanly
            reply(None, error={"code": -32600, "message": "Batch requests are not supported"})
            continue
        method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if mid is None:  # notification: never answered
            continue
        try:
            if method == "initialize":
                asked = params.get("protocolVersion", "")
                version = asked if asked in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
                reply(mid, {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "second-brain", "version": __version__},
                    "instructions": (
                        "This server is the user's second brain: a Markdown vault of notes, people, "
                        "projects, decisions and a journal. Call brain_wake_up once at the start of "
                        "a session.\n\n" + PROTOCOL),
                })
            elif method == "ping":
                reply(mid, {})
            elif method == "tools/list":
                reply(mid, {"tools": [{"name": t.name, "description": t.description,
                                       "inputSchema": t.schema,
                                       "annotations": {"readOnlyHint": not t.writes,
                                                       "destructiveHint": False,
                                                       "openWorldHint": False}}
                                      for t in get_tools(args.read_only)]})
            elif method == "tools/call":
                tool = tools.get(params.get("name", ""))
                if tool is None:
                    reply(mid, error={"code": -32602, "message": f"Unknown tool: {params.get('name')}"})
                    continue
                text = tool.call(params.get("arguments") or {})
                is_error = text.startswith(("Refused:", "Bad arguments"))
                reply(mid, {"content": [{"type": "text", "text": text}], "isError": is_error})
            elif method in ("resources/list", "prompts/list"):
                reply(mid, {method.split("/")[0]: []})
            else:
                reply(mid, error={"code": -32601, "message": f"Method not found: {method}"})
        except Exception as e:  # never let one bad call kill the server
            log(traceback.format_exc())
            reply(mid, error={"code": -32603, "message": f"Internal error: {e}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
