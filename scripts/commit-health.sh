#!/usr/bin/env bash
# Commit data/health.json as the bot and push it to main, if it changed.
# Run from the repository root, on main. Nothing else in the working tree is committed.
set -euo pipefail

FILE=data/health.json
BOT=(-c "user.name=github-actions[bot]" -c "user.email=41898282+github-actions[bot]@users.noreply.github.com")

git add -- "$FILE"

if git diff --cached --quiet; then
  echo "health state unchanged; nothing to commit"
  exit 0
fi

git "${BOT[@]}" commit -q -m "Link health check $(date -u +%F)"

# main may have moved while the probes ran (the nightly deploy can push a submodule bump).
# Replay this one commit on top rather than overwrite anything.
git "${BOT[@]}" pull --rebase -q origin main
git push -q origin HEAD:main

echo "pushed $(git rev-parse --short HEAD)"
