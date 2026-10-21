#!/usr/bin/env bash
# Move the vendor/public-apis pin to upstream's latest commit and commit the change.
# Does nothing if the pin is already current. Never pushes: the caller decides that.
set -euo pipefail

SUB=vendor/public-apis
BOT_NAME="github-actions[bot]"
BOT_EMAIL="41898282+github-actions[bot]@users.noreply.github.com"

before=$(git rev-parse "HEAD:$SUB")
git submodule update --init --remote --depth 1 "$SUB"
after=$(git -C "$SUB" rev-parse HEAD)

if [ "$before" = "$after" ]; then
  echo "public-apis already at ${after:0:7}; nothing to bump"
  exit 0
fi

git add "$SUB"
git -c user.name="$BOT_NAME" -c user.email="$BOT_EMAIL" commit -q \
  -m "Bump public-apis to ${after:0:7}" \
  -m "https://github.com/public-apis/public-apis/compare/${before}...${after}"

echo "bumped public-apis ${before:0:7} -> ${after:0:7}"
