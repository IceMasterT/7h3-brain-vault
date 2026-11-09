#!/usr/bin/env python3
"""Claude Code Stop hook: every SAVE_EVERY user messages, ask Claude once to save
what it learned before it stops. Never loops: it stands down when
stop_hook_active is set, and nudges at most once per SAVE_EVERY messages.
Fails open: any problem means Claude simply stops as usual.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VAULT = os.path.dirname(os.path.dirname(HERE))
SAVE_EVERY = 15
REASON = ("Before stopping: if this session produced facts, decisions or preferences worth keeping, "
          "save them to the second brain (inbox capture, capture-decision skill, or a journal line via "
          "`python3 scripts/brain.py journal ...`). If nothing is worth saving, just stop.")


def user_messages(transcript_path: str) -> int:
    n = 0
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") != "user":
                continue
            content = (e.get("message") or {}).get("content")
            if isinstance(content, str) and content.strip():
                n += 1
            elif isinstance(content, list) and any(
                    isinstance(p, dict) and p.get("type") == "text" for p in content):
                n += 1
    return n


def main() -> int:
    data = json.load(sys.stdin)
    if data.get("stop_hook_active"):
        return 0
    path = data.get("transcript_path") or ""
    if not path or not os.path.isfile(path):
        return 0
    count = user_messages(path)
    if count < SAVE_EVERY:
        return 0
    session = re.sub(r"[^A-Za-z0-9_\-]", "", str(data.get("session_id") or "default"))[:64]
    state = os.path.join(VAULT, ".brain", f"nudge-{session}")
    os.makedirs(os.path.dirname(state), exist_ok=True)
    try:
        with open(state, encoding="utf-8") as f:
            last = int(f.read().strip() or 0)
    except (OSError, ValueError):
        last = 0
    if count // SAVE_EVERY <= last // SAVE_EVERY:
        return 0
    with open(state, "w", encoding="utf-8") as f:
        f.write(str(count))
    print(json.dumps({"decision": "block", "reason": REASON}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
