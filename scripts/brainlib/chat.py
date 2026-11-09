"""A small terminal chat loop that gives any OpenAI-compatible model the vault.

Built for local Hermes models (Ollama, LM Studio, llama.cpp server, vLLM) but
works with any server that speaks /v1/chat/completions. Talks only to the
--base-url you give it. Write tools ask for confirmation unless --yes.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

from . import hermes
from .tools import by_name, openai_schema

MAX_TOOL_ROUNDS = 8
THINK_RE = re.compile(r"<think>.*?</think>", re.S)


class ChatError(Exception):
    pass


def _post(base_url: str, payload: dict, api_key: str, timeout: int) -> dict:
    url = base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        raise ChatError(f"HTTP {e.code} from {url}: {body}") from None
    except urllib.error.URLError as e:
        raise ChatError(f"cannot reach {url}: {e.reason}") from None


class Session:
    def __init__(self, base_url: str, model: str, api_key: str = "", mode: str = "auto",
                 read_only: bool = False, assume_yes: bool = False, temperature: float = 0.3,
                 timeout: int = 300):
        self.base_url, self.model, self.api_key = base_url, model, api_key
        self.mode = mode  # auto | native | text
        self.read_only, self.assume_yes = read_only, assume_yes
        self.temperature, self.timeout = temperature, timeout
        self.tools = by_name(read_only)
        self.messages: list[dict] = []
        self._reset_system()

    def _reset_system(self) -> None:
        text_mode = self.mode == "text"
        self.messages = [{"role": "system", "content": hermes.system_prompt(text_mode, self.read_only)}]

    def _confirm(self, name: str, args: dict) -> bool:
        tool = self.tools[name]
        if not tool.writes or self.assume_yes:
            return True
        print(f"\n[{name}] wants to write:\n{json.dumps(args, indent=2, ensure_ascii=False)}")
        try:
            return input("Allow? [y/N] ").strip().lower() in ("y", "yes")
        except EOFError:
            return False

    def _run_tool(self, name: str, args: dict) -> str:
        if name not in self.tools:
            return f"Unknown tool {name!r}. Available: {', '.join(self.tools)}."
        if not self._confirm(name, args):
            return "The user declined this write. Do not retry it; ask what they want instead."
        print(f"  -> {name}", file=sys.stderr)
        return self.tools[name].call(args)

    def _complete(self) -> dict:
        payload = {"model": self.model, "messages": self.messages, "temperature": self.temperature}
        if self.mode in ("auto", "native"):
            payload["tools"] = openai_schema(self.read_only)
        try:
            data = _post(self.base_url, payload, self.api_key, self.timeout)
        except ChatError as e:
            if self.mode == "auto" and "HTTP 4" in str(e):
                # Server rejected the tools field: fall back to the Hermes text protocol.
                print("(server has no native tool calling; using the Hermes <tool_call> format)", file=sys.stderr)
                self.mode = "text"
                history = self.messages[1:]
                self._reset_system()
                self.messages.extend(history)
                return self._complete()
            raise
        try:
            return data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise ChatError(f"unexpected response: {json.dumps(data)[:300]}") from None

    def ask(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        for _ in range(MAX_TOOL_ROUNDS):
            msg = self._complete()
            content = msg.get("content") or ""
            native_calls = msg.get("tool_calls") or []
            if native_calls:
                self.messages.append({"role": "assistant", "content": content, "tool_calls": native_calls})
                for call in native_calls:
                    fn = call.get("function", {})
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = self._run_tool(fn.get("name", ""), args if isinstance(args, dict) else {})
                    self.messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                          "name": fn.get("name", ""), "content": result})
                continue
            text_calls = hermes.parse_tool_calls(content)
            if text_calls:
                self.messages.append({"role": "assistant", "content": content})
                responses = [hermes.tool_response(c["name"], self._run_tool(c["name"], c["arguments"]))
                             for c in text_calls]
                # Plain user turn: works on every server, unlike role "tool" without an id.
                self.messages.append({"role": "user", "content": "\n".join(responses)})
                continue
            self.messages.append({"role": "assistant", "content": content})
            return THINK_RE.sub("", hermes.strip_tool_calls(content)).strip()
        return "(stopped after too many tool calls in one turn)"


def repl(session: Session) -> int:
    print(f"Second brain chat with {session.model} at {session.base_url}. "
          "Commands: /reset, /quit. Writes ask before saving.")
    while True:
        try:
            line = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("/quit", "/exit"):
            return 0
        if line == "/reset":
            session._reset_system()
            print("(context cleared, wake-up pack reloaded)")
            continue
        try:
            print("\nbrain> " + session.ask(line))
        except ChatError as e:
            print(f"error: {e}", file=sys.stderr)


def api_key_from_env(var: str) -> str:
    return os.environ.get(var, "") if var else ""
