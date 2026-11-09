---
name: capture-decision
description: Use when I make or confirm a decision, or say "log this decision".
---
# Capture a decision
1. Collect from the user, in their words: the decision, why, options rejected, assumptions, and what would change their mind.
2. Preferred: call brain_log_decision. It creates 50-decisions/YYYY-MM-DD-short-title.md from the template and adds the line to 50-decisions/decisions.md, newest first.
3. Without the tool: create the file from _templates/decision.md, fill summary, and add "- YYYY-MM-DD [[file-stem]]: one-sentence summary" at the top of the list in decisions.md.
4. Link related notes and projects. If the decision replaces an older one, set superseded_by on the old decision.
5. Record only what the user stated. Do not invent reasons.
