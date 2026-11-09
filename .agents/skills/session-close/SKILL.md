---
name: session-close
description: Use at the end of a working session, when I say "wrap up", "save this", "remember this", or when a hook reminds you to save.
---
# Close the session into memory
1. One journal line: brain_journal (or `python3 scripts/brain.py journal "..."`) saying what was done or decided, in one sentence.
2. New facts, preferences or ideas the user stated: brain_capture each, in the user's words, with a source ("chat YYYY-MM-DD").
3. A decision was made: run the capture-decision skill.
4. A project moved: append to its Log section and update its Status and Next step (brain_update_note).
5. A note was confirmed still true: brain_update_note with verified true.
6. Tell the user in two lines what was saved and where. Save nothing the user did not say or confirm.
