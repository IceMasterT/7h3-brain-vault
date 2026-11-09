#!/usr/bin/env bash
# Install a new vault, or upgrade an existing one in place.
#
#   ./install.sh [target-dir]            new vault (default: ~/second-brain); target must be empty
#   ./install.sh --upgrade <vault-dir>   upgrade an existing vault: replaces the engine
#                                        (scripts, hooks, rules, skills, templates, manuals),
#                                        never touches your notes, and backs up every file it
#                                        replaces to .backups/upgrade-<timestamp>/
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"

# Engine paths: owned by the vault design, replaced on upgrade.
ENGINE=(
  AGENTS.md CLAUDE.md GEMINI.md README.md CLAUDE.local.md.example .gitignore .mcp.json install.sh
  .cursor/mcp.json .githooks .claude/settings.json .claude/hooks .claude/rules .claude/skills
  .agents/skills scripts _templates .obsidian/daily-notes.json
)
# Seed content: created when missing, never overwritten.
SEED=(
  _meta/identity.md _meta/index.md _meta/promotion-log.md 30-projects/now.md
  50-decisions/decisions.md 50-decisions/2026-11-09-shared-memory-for-every-ai.md
  10-notes/how-this-vault-works.md .obsidian/app.json .obsidian/core-plugins.json .obsidian/templates.json
)
FOLDERS=(00-inbox 10-notes 20-people 30-projects 40-drafts 50-decisions 60-journal
         90-archive/inbox-processed 90-archive/attachments _meta)

# sha256 of each seed file as shipped in v1. A file still matching is untouched
# by the user, so the upgrade may replace it (with a backup).
v1_pristine() {
  case "$1" in
    _meta/index.md) echo 9ab6273df5a0bb88e7d2d67283db2ed5a5843bc02d6bded7227bcdb790d5eb48 ;;
    _meta/promotion-log.md) echo b1c57d07dc47558d0e5117365e2c5d6a65a72d0fd9656ecd66f5a29140c5bcee ;;
    30-projects/now.md) echo a6a6353dcecb4cdb2d968b2dd2480baec548e2cf62d22891b222910ab1dc6dc8 ;;
    50-decisions/decisions.md) echo 4da8eb00e7449885598eab0304161e88c0e123859ffa27610f5ff2a06d6792c2 ;;
    10-notes/how-this-vault-works.md) echo 9a2c9f76b069b496d915d953c29c556fa0702c0af8c28a98af95b9519f4752e1 ;;
    .obsidian/app.json) echo c07a4b06aaef870c820eb944e2cca664d04785b5a2dd40cc86242c5b1d9fbaa4 ;;
    *) echo none ;;
  esac
}

sha256() { python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }

backup_item() {  # backup_item <relative path>: move the vault's copy into the backup folder
  mkdir -p "$BACKUP/$(dirname "$1")"
  mv "$DEST/$1" "$BACKUP/$1"
}

copy_item() {  # copy_item <relative path> <dest root>; keeps symlinks as symlinks
  local rel="$1" dest="$2"
  mkdir -p "$dest/$(dirname "$rel")"
  cp -RP "$SRC/$rel" "$dest/$rel"
}

MODE=install
if [ "${1:-}" = "--upgrade" ]; then
  MODE=upgrade
  DEST="$(cd "${2:?usage: ./install.sh --upgrade <vault-dir>}" && pwd)"
  [ -f "$DEST/CLAUDE.md" ] || [ -f "$DEST/AGENTS.md" ] || { echo "$DEST does not look like a vault."; exit 1; }
  [ "$DEST" != "$SRC" ] || { echo "Run the upgrade from a separate copy of the new vault."; exit 1; }
  STAMP="$(date +%Y%m%d-%H%M%S)"
  # Hidden from Obsidian and the search index; gitignored (git history keeps the old engine too).
  BACKUP="$DEST/.backups/upgrade-$STAMP"
  n=2
  while [ -e "$BACKUP" ]; do BACKUP="$DEST/.backups/upgrade-$STAMP-$n"; n=$((n + 1)); done
  for rel in "${ENGINE[@]}"; do
    [ -e "$SRC/$rel" ] || [ -L "$SRC/$rel" ] || continue
    if [ -e "$DEST/$rel" ] || [ -L "$DEST/$rel" ]; then backup_item "$rel"; fi
    copy_item "$rel" "$DEST"
  done
  for rel in "${SEED[@]}"; do
    if [ ! -e "$DEST/$rel" ]; then
      copy_item "$rel" "$DEST"
    elif [ "$(sha256 "$DEST/$rel")" = "$(v1_pristine "$rel")" ]; then
      backup_item "$rel"  # unchanged since v1: take the new version
      copy_item "$rel" "$DEST"
    fi
  done
  # Bring v1 seed files up to date without losing anything the user added.
  python3 - "$DEST" <<'PY'
import re, sys, datetime
from pathlib import Path
root = Path(sys.argv[1]); today = datetime.date.today().isoformat()
idx = root / "_meta/index.md"; t = idx.read_text(encoding="utf-8")
if "[[identity]]" not in t:
    t = t.replace("## Start here\n", "## Start here\n- [[identity]]\n", 1)
if "## Sources" not in t:
    t = t.replace("## People", "## Sources\n\n## People", 1)
idx.write_text(t, encoding="utf-8")
dec = root / "50-decisions/decisions.md"; d = dec.read_text(encoding="utf-8")
line = "- 2026-11-09 [[2026-11-09-shared-memory-for-every-ai]]: One standard-library core gives every AI the same memory, rules and audit trail."
if "[[2026-11-09-shared-memory-for-every-ai]]" not in d:
    m = re.search(r"^- \d{4}-\d{2}-\d{2} ", d, re.M)
    d = d[:m.start()] + line + "\n" + d[m.start():] if m else d.rstrip() + "\n" + line + "\n"
    dec.write_text(d, encoding="utf-8")
log = root / "_meta/promotion-log.md"; p = log.read_text(encoding="utf-8")
if not p.startswith("---"):
    log.write_text(f"---\ntype: log\nstatus: active\ncreated: {today}\nupdated: {today}\ntags: [meta]\n---\n" + p,
                   encoding="utf-8")
PY
  for d in "${FOLDERS[@]}"; do mkdir -p "$DEST/$d"; done
  echo "Engine replaced. Your notes were not touched. Replaced files are in: ${BACKUP#$DEST/}/"
else
  DEST="${1:-$HOME/second-brain}"
  if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
    echo "Target $DEST is not empty. To upgrade an existing vault: ./install.sh --upgrade $DEST"
    exit 1
  fi
  mkdir -p "$DEST"
  DEST="$(cd "$DEST" && pwd)"
  for rel in "${ENGINE[@]}" "${SEED[@]}"; do
    [ -e "$SRC/$rel" ] || [ -L "$SRC/$rel" ] || continue
    copy_item "$rel" "$DEST"
  done
  for d in "${FOLDERS[@]}"; do mkdir -p "$DEST/$d" && touch "$DEST/$d/.gitkeep"; done
  [ -e "$DEST/CLAUDE.local.md" ] || cp "$DEST/CLAUDE.local.md.example" "$DEST/CLAUDE.local.md"
fi

chmod +x "$DEST"/.claude/hooks/* "$DEST"/.githooks/* "$DEST"/scripts/*.py
# Folders, skill links, git repo, pre-commit check, executable bits, search index.
python3 "$DEST/scripts/brain.py" doctor --fix || true
if git -C "$DEST" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  ( cd "$DEST" && git add -A && git commit -qm "Vault engine $MODE $(date +%Y-%m-%d)" ) \
    || echo "git commit skipped (configure git user.name and user.email, then commit)"
fi

cat <<EOF

Vault ready at: $DEST
1. Obsidian: Open folder as vault -> $DEST
2. Fill in _meta/identity.md (who you are, how you like answers). Every AI reads it.
3. Claude Code: cd "$DEST" && claude   then /context and /mcp to confirm memory and the brain server.
4. Other AIs: python3 "$DEST/scripts/brain.py" connect hermes   (or claude-desktop, cursor, codex, gemini, lm-studio)
5. Local Hermes model: python3 "$DEST/scripts/brain.py" chat --model <name>   (Ollama by default)
6. Check: python3 "$DEST/scripts/brain.py" doctor
EOF
