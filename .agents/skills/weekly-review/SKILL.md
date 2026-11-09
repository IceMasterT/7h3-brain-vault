---
name: weekly-review
description: Use when I ask for a weekly review of my second brain.
---
# Weekly review
1. Run `python3 scripts/brain.py health --write` and read _meta/vault-health.md. Fix errors first.
2. Read every file in 30-projects/. List what moved this week, what is stuck, and the next step for each.
3. Check 20-people/ for anyone with Last contact older than 30 days. List them.
4. Stale facts: notes with last_verified older than 90 days, and review_after dates that passed. Ask which to verify, update or archive.
5. Conflicts: `python3 scripts/brain.py facts --conflicts`. Present each pair; never resolve one silently.
6. Fading notes: `python3 scripts/brain.py fading`. Propose archive candidates. Never archive without approval.
7. Read this week's 60-journal/ files. Promote durable "Learned" lines into notes (with approval).
8. Digest proposal (optional): if five or more small notes share a tag, propose one digest note that links them. Originals stay; archive only with approval.
9. Make sure this week's decisions are in 50-decisions/decisions.md.
10. Refresh 30-projects/now.md with the top three priorities. Show the diff before saving.
11. Write the review to 10-notes/weekly-review-YYYY-MM-DD.md using _templates/note.md, linking each project and person mentioned.
