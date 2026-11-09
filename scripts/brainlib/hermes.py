"""Prompts for models that are not wired to MCP, in particular Nous Hermes models.

Hermes 2 Pro, 3 and 4 were trained on a function-calling format: tool
signatures inside <tools></tools> in the system prompt, calls emitted as
<tool_call>{"name": ..., "arguments": {...}}</tool_call>, results returned
inside <tool_response></tool_response>. Servers such as Ollama, vLLM and
llama.cpp parse that format into OpenAI tool_calls when given `tools`; when a
server does not, the chat loop parses the tags itself.
"""
from __future__ import annotations

import json
import re

from .context import wake_up
from .tools import hermes_tools_block

HERMES_TOOL_INSTRUCTIONS = """You are a function calling AI model. You are provided with function signatures within <tools></tools> XML tags. You may call one or more functions to assist with the user query. Don't make assumptions about what values to plug into functions. Here are the available tools:
{tools}
Use the following pydantic model json schema for each tool call you will make: {{"properties": {{"name": {{"title": "Name", "type": "string"}}, "arguments": {{"title": "Arguments", "type": "object"}}}}, "required": ["name", "arguments"], "title": "FunctionCall", "type": "object"}}
For each function call return a json object with function name and arguments within <tool_call></tool_call> XML tags as follows:
<tool_call>
{{"name": <function-name>, "arguments": <args-dict>}}
</tool_call>"""

ROLE = """You are the user's memory-backed assistant. Your long-term memory is the user's second brain: a Markdown vault you reach only through the brain_* tools. Treat the vault as the source of truth about the user, their people, projects and decisions. Use plain, short sentences."""

TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


def system_prompt(with_tool_block: bool, read_only: bool = False, include_wake_up: bool = True) -> str:
    """Full system prompt. with_tool_block=True embeds the Hermes <tools> format."""
    parts = []
    if with_tool_block:
        parts.append(HERMES_TOOL_INSTRUCTIONS.format(tools=hermes_tools_block(read_only)))
    parts.append(ROLE)
    if include_wake_up:
        parts.append(wake_up())
    return "\n\n".join(parts)


def parse_tool_calls(content: str) -> list[dict]:
    """[{name, arguments}] from Hermes-format text. Malformed calls are skipped."""
    calls = []
    for m in TOOL_CALL_RE.finditer(content or ""):
        try:
            obj = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("name"), str):
            args = obj.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append({"name": obj["name"], "arguments": args if isinstance(args, dict) else {}})
    return calls


def tool_response(name: str, content: str) -> str:
    return "<tool_response>\n" + json.dumps({"name": name, "content": content}, ensure_ascii=False) + "\n</tool_response>"


def strip_tool_calls(content: str) -> str:
    return TOOL_CALL_RE.sub("", content or "").strip()
