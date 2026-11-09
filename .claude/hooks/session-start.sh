#!/usr/bin/env bash
# SessionStart: stdout is added to Claude's context. Keep it short.
# The wake-up pack is the same one Hermes and MCP clients get (brain_wake_up).
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
export BRAIN_AGENT=claude-code
python3 scripts/brain.py wake-up 2>/dev/null || echo "Vault session start. Today is $(date +%Y-%m-%d). (wake-up pack unavailable: run python3 scripts/brain.py doctor)"
python3 scripts/brain.py health --brief 2>/dev/null
exit 0
