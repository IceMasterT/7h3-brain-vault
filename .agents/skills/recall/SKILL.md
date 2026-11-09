---
name: recall
description: Use when a question touches me, my people, projects, past decisions or anything I may have saved before, so the answer comes from my second brain with citations.
---
# Answer from the vault
1. Recall: brain_recall with the question (or `python3 scripts/brain.py recall "question" --lenient`).
2. If the top hits are thin, search again with other words, synonyms or a person's name: brain_search, optionally filtered by type.
3. Read the two or three best notes in full (brain_read). Summaries are pointers, not evidence.
4. For anything that changes over time, check dated facts: brain_facts with subject (and as_of for a past date).
5. Answer. Cite every vault-backed claim as [[note-name]]. Label anything else "inferred". Mention superseded or low-confidence notes as such.
6. If nothing covers it, say "the vault has no note on this" and name the note you would create. Offer to capture what the user tells you.
