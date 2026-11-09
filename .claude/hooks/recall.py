#!/usr/bin/env python3
"""Per-turn recall. Injects vault notes that match what the user just asked.

Claude Code  UserPromptSubmit: reads {"prompt"}, plain stdout becomes context.
Hermes Agent pre_llm_call:     reads extra.user_message, replies {"context": ...}.
             On the first turn it also injects the wake-up pack (Hermes does
             not load CLAUDE.md imports), and every SAVE_EVERY user turns it
             reminds the agent to save what it learned.

Fails open and silent: a recall problem must never block a conversation.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VAULT = os.path.dirname(os.path.dirname(HERE))
SAVE_EVERY = 15
SAVE_NUDGE = ("Second brain: it has been a while since anything was saved. If this conversation "
              "produced facts, decisions or preferences worth keeping, save them now (brain_capture, "
              "brain_log_decision, brain_journal), then continue.")


def text_of(message) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):  # multimodal parts
        return " ".join(p.get("text", "") for p in message if isinstance(p, dict))
    return ""


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    os.environ.setdefault("BRAIN_VAULT", VAULT)
    sys.path.insert(0, os.path.join(VAULT, "scripts"))
    from brainlib import context
    from brainlib.index import open_index

    hermes = data.get("hook_event_name") == "pre_llm_call"
    extra = data.get("extra") or {}
    prompt = text_of(extra.get("user_message")) if hermes else text_of(data.get("prompt"))

    parts = []
    idx = open_index()
    try:
        if hermes and extra.get("is_first_turn"):
            parts.append(context.wake_up(idx=idx))
        found = context.recall(prompt, idx=idx) if prompt.strip() else ""
        if found:
            parts.append(found)
    finally:
        idx.close()
    if hermes:
        history = extra.get("conversation_history") or []
        user_turns = sum(1 for m in history if isinstance(m, dict) and m.get("role") == "user") + 1
        if user_turns % SAVE_EVERY == 0:
            parts.append(SAVE_NUDGE)

    if not parts:
        return 0
    out = "\n\n".join(parts)
    print(json.dumps({"context": out}) if hermes else out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
