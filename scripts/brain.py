#!/usr/bin/env python3
"""brain: command line for the second brain. Standard library only.

Read
  search QUERY            ranked search (--type, --limit, --archive, --json)
  recall QUERY            the context block a hook would inject for QUERY
  wake-up                 session-start pack (identity, protocol, priorities, ...)
  read NOTE               print a note with its backlinks
  facts                   dated facts (--subject, --predicate, --as-of)
  fading                  live notes unused and unedited for --days (archive candidates)
  triage-suggest          rule-based hints for each inbox capture
Write (validated, audited)
  capture TEXT            raw capture to the inbox (--title, --source)
  journal TEXT            one line in today's journal
Maintain
  health                  vault health (--brief, --write, --json, --strict)
  index                   refresh the search index (--rebuild)
  audit                   AI write log (--verify, --tail N)
  doctor                  check the install (--fix repairs it)
Connect
  connect TARGET          config for hermes, claude-code, claude-desktop, cursor, codex, gemini, lm-studio
  tools                   tool schemas (--format openai|hermes|mcp, --read-only)
  prompt                  system prompt for a model without MCP (--hermes adds the <tools> block)
  chat                    chat with any OpenAI-compatible model (Hermes via Ollama, LM Studio, ...)
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="brain", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", help="vault root (default: $BRAIN_VAULT or this script's vault)")
    ap.add_argument("--agent", help="name recorded in the audit log (default: $BRAIN_AGENT or cli)")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    s = sub.add_parser("search"); s.add_argument("query", nargs="+")
    s.add_argument("--type", action="append"); s.add_argument("--limit", type=int, default=8)
    s.add_argument("--archive", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("recall"); s.add_argument("query", nargs="+"); s.add_argument("--lenient", action="store_true")
    sub.add_parser("wake-up")
    s = sub.add_parser("read"); s.add_argument("note")
    s = sub.add_parser("facts"); s.add_argument("--subject", default=""); s.add_argument("--predicate", default="")
    s.add_argument("--as-of", default=""); s.add_argument("--conflicts", action="store_true")
    s = sub.add_parser("fading"); s.add_argument("--days", type=int, default=90)
    sub.add_parser("triage-suggest")
    s = sub.add_parser("capture"); s.add_argument("text", nargs="+")
    s.add_argument("--title", default=""); s.add_argument("--source", default="")
    s = sub.add_parser("journal"); s.add_argument("text", nargs="+")
    s = sub.add_parser("health")
    for flag in ("--brief", "--write", "--json", "--strict"):
        s.add_argument(flag, action="store_true")
    s = sub.add_parser("index"); s.add_argument("--rebuild", action="store_true")
    s = sub.add_parser("audit"); s.add_argument("--verify", action="store_true"); s.add_argument("--tail", type=int, default=20)
    s = sub.add_parser("doctor"); s.add_argument("--fix", action="store_true")
    s = sub.add_parser("connect"); s.add_argument("target")
    s = sub.add_parser("tools"); s.add_argument("--format", choices=["openai", "hermes", "mcp"], default="openai")
    s.add_argument("--read-only", action="store_true")
    s = sub.add_parser("prompt"); s.add_argument("--hermes", action="store_true")
    s.add_argument("--read-only", action="store_true"); s.add_argument("--no-wake-up", action="store_true")
    s = sub.add_parser("chat")
    s.add_argument("--base-url", default="http://localhost:11434/v1", help="OpenAI-compatible endpoint")
    s.add_argument("--model", required=True, help="e.g. hermes3, nous-hermes-4-14b")
    s.add_argument("--api-key-env", default="", help="NAME of an env var holding the API key")
    s.add_argument("--mode", choices=["auto", "native", "text"], default="auto",
                   help="native tool calls, Hermes <tool_call> text, or auto-detect")
    s.add_argument("--read-only", action="store_true"); s.add_argument("--yes", action="store_true",
                                                                        help="allow writes without asking")
    s.add_argument("--temperature", type=float, default=0.3)

    a = ap.parse_args(argv)
    if a.vault:
        os.environ["BRAIN_VAULT"] = a.vault
    os.environ["BRAIN_AGENT"] = a.agent or os.environ.get("BRAIN_AGENT") or (
        f"chat:{a.model}" if a.cmd == "chat" else "cli")

    # Imported after the environment is set: brainlib resolves the vault at import.
    from brainlib import audit, context, health, setup, triage, writer
    from brainlib.index import open_index
    from brainlib.tools import by_name, get_tools, hermes_tools_block, openai_schema

    if a.cmd == "search":
        idx = open_index()
        try:
            hits = idx.search(" ".join(a.query), limit=a.limit, types=a.type, include_archive=a.archive)
        finally:
            idx.close()
        if a.json:
            _print_json([h.as_dict() for h in hits])
        elif not hits:
            print("No matches.")
        for h in [] if a.json else hits:
            print(f"[[{h.stem}]]  {h.type or 'capture'}  {h.rel}  score {h.score:.2f}  matched {', '.join(h.matched)}")
            if h.summary or h.snippet:
                print(f"    {(h.summary or h.snippet)[:200]}")
        return 0
    if a.cmd == "recall":
        out = context.recall(" ".join(a.query), strict=not a.lenient)
        print(out or "(nothing clears the recall bar)")
        return 0
    if a.cmd == "wake-up":
        print(context.wake_up())
        return 0
    if a.cmd == "read":
        print(by_name()["brain_read"].call({"note": a.note}))
        return 0
    if a.cmd == "facts":
        idx = open_index()
        try:
            if a.conflicts:
                pairs = idx.conflicts()
                for x, y in pairs:
                    print(f"- {x.text()}\n  vs {y.text()}")
                print(f"{len(pairs)} possible conflict(s).")
                return 0
            for f in idx.facts(a.subject, a.predicate, a.as_of):
                print("- " + f.text())
        finally:
            idx.close()
        return 0
    if a.cmd == "fading":
        idx = open_index()
        try:
            rows = idx.fading(a.days)
        finally:
            idx.close()
        for r in rows:
            print(f"- [[{r['stem']}]] ({r['type']}): uses {r['uses'] or 0}. {r['summary'][:100]}")
        print(f"{len(rows)} note(s) unused and unedited for {a.days}+ days. Propose; never auto-archive.")
        return 0
    if a.cmd == "triage-suggest":
        rows = triage.suggest()
        if not rows:
            print("Inbox is empty.")
        for r in rows:
            similar = ", ".join(f"[[{s}]]" for s in r["possible_existing_notes"]) or "none"
            print(f"- {r['file']}: {r['suggested']} (confidence {r['confidence']}). Similar: {similar}")
        return 0
    if a.cmd in ("capture", "journal"):
        try:
            if a.cmd == "capture":
                res = writer.capture(" ".join(a.text), title=a.title, source=a.source,
                                     agent=os.environ["BRAIN_AGENT"])
            else:
                res = writer.journal(" ".join(a.text), agent=os.environ["BRAIN_AGENT"])
        except writer.VaultError as e:
            print(f"Refused: {e}", file=sys.stderr)
            return 1
        print(f"{res['status']}: {res['path']}")
        return 0
    if a.cmd == "health":
        rep = health.run()
        if a.brief:
            print(rep.brief())
        elif a.json:
            _print_json(rep.as_dict())
        else:
            print(rep.markdown())
        if a.write:
            from brainlib.vault import META, ROOT
            (ROOT / META / "vault-health.md").write_text(rep.markdown() + "\n", encoding="utf-8")
        return 1 if (a.strict and rep.errors) else 0
    if a.cmd == "index":
        idx = open_index(refresh=False)
        try:
            print(idx.rebuild() if a.rebuild else idx.refresh())
        finally:
            idx.close()
        return 0
    if a.cmd == "audit":
        if a.verify:
            ok, msg, _ = audit.verify()
            print(msg)
            return 0 if ok else 1
        for e in audit.tail(a.tail):
            print(f"{e['ts']}  {e['agent']:<18} {e['action']:<8} {e['path']}" + (f"  ({e['detail']})" if e.get("detail") else ""))
        return 0
    if a.cmd == "doctor":
        rows, fails = setup.doctor(fix=a.fix)
        marks = {"ok": "ok   ", "fixed": "FIXED", "warn": "warn ", "fail": "FAIL "}
        for status, check, detail in rows:
            print(f"{marks[status]} {check}" + (f": {detail}" if detail else ""))
        return 1 if fails else 0
    if a.cmd == "connect":
        try:
            print(setup.connect(a.target))
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        return 0
    if a.cmd == "tools":
        if a.format == "hermes":
            print(hermes_tools_block(a.read_only))
        elif a.format == "mcp":
            _print_json([{"name": t.name, "description": t.description, "inputSchema": t.schema}
                         for t in get_tools(a.read_only)])
        else:
            _print_json(openai_schema(a.read_only))
        return 0
    if a.cmd == "prompt":
        from brainlib.hermes import system_prompt
        print(system_prompt(a.hermes, a.read_only, include_wake_up=not a.no_wake_up))
        return 0
    if a.cmd == "chat":
        from brainlib.chat import Session, api_key_from_env, repl
        return repl(Session(a.base_url, a.model, api_key=api_key_from_env(a.api_key_env), mode=a.mode,
                            read_only=a.read_only, assume_yes=a.yes, temperature=a.temperature))
    return 2


if __name__ == "__main__":
    sys.exit(main())
