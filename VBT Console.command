#!/bin/bash
# VBT Console launcher — double-click in Finder (or run from Terminal).
# Serves the parent folder of this repo (~/Projects: vbt-private + vbt-data) on
# 127.0.0.1 only — nothing leaves this Mac — then opens the console in the browser.
# Close this Terminal window (or press Ctrl-C) to stop the server.

cd "$(dirname "$0")/.." || exit 1
PORT=8787
URL="http://127.0.0.1:$PORT/vbt-private/console/"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "VBT Console is already running → $URL"
  open "$URL"
  exit 0
fi

echo "VBT Console → $URL"
echo "Serving $(pwd) on 127.0.0.1:$PORT (local only). Close this window or press Ctrl-C to stop."
(sleep 1; open "$URL") &
exec python3 -m http.server "$PORT" --bind 127.0.0.1
