---
name: triage-inbox
description: Use when I ask to triage, sort or process the inbox, or when 00-inbox has waiting items.
---
# Triage the inbox
1. Run `python3 scripts/brain.py triage-suggest`. It lists every capture with a rule-based suggestion (decision, person, project, source, preference, note), a confidence, and existing notes that look similar. Treat it as a hint, not a verdict.
2. For each item decide: new note, update to an existing note, person card, project update, decision, preference (goes to _meta/identity.md, which the user edits), or discard.
3. Search before creating (brain_search or `brain.py search`). Prefer updating over creating.
4. Show the user a table: file, proposed action, target file. Wait for approval before moving anything.
5. After approval, create or update targets from _templates/ (or with brain_create_note / brain_update_note, which enforce the rules), add [[wikilinks]] and a one-sentence summary, and move each processed capture to 90-archive/inbox-processed/ (never delete). Use brain_archive or `git mv`.
6. New notes are listed in _meta/index.md under the right heading (the brain tools do this).
7. Report what changed in three lines or fewer, and add one journal line.
