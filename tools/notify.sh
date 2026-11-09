#!/usr/bin/env bash
# Send a milestone update to the user's Discord webhook.
# Usage: tools/notify.sh "message" [file ...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$(cat "$ROOT/.discord-webhook")"
msg="$1"; shift || true
args=(-s -o /dev/null -w '%{http_code}' -F "content=$msg")
i=0
for f in "$@"; do
  i=$((i+1))
  args+=(-F "file$i=@$f")
done
code=$(curl "${args[@]}" "$HOOK" || true)
echo "discord:$code"
