#!/bin/bash
# Stops everything scripts/start.sh started: each process it records in run/NAME.pid, with its children.
cd "$(dirname "$0")/.." || exit 1
for f in run/*.pid; do
  [ -f "$f" ] || continue
  kill -TERM -- "-$(cat "$f")" 2>/dev/null
  rm -f "$f"
done
echo stopped
