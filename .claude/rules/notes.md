---
paths:
  - "10-notes/**"
---
# Evergreen notes
- One topic per file. If a note covers two topics, split it and link the halves.
- Start from _templates/note.md (or _templates/source.md for something you read, watched or heard). Frontmatter is required.
- Fill summary: one sentence. Search and recall show it, so make it stand alone.
- Structure: summary line, Details, Facts, Sources, Related.
- Related holds [[wikilinks]] to at least two other notes when they exist. List the note in _meta/index.md.
- Facts that can go stale (prices, roles, laws, versions) get "as of YYYY-MM-DD", or a dated line in Facts.
- When you verify a fact is still true, update last_verified. Do not bump it just for editing.
- Never merge two notes that disagree. Add a "Conflict" section naming both and ask the user.
- When a newer note replaces this one, set superseded_by: [[newer-note]] and status: superseded. Keep the old note.
- confidence: high only for things the user stated or a cited primary source says.
