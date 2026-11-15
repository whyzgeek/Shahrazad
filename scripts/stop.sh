#!/bin/bash
# Stops everything scripts/start.sh started: each process it records in run/NAME.pid, with its children.
cd "$(dirname "$0")/.." || exit 1
. scripts/ui.sh
step "Stopping Shahrazad"
found=''
for f in run/*.pid; do
  [ -f "$f" ] || continue
  name=$(basename "$f" .pid); pid=$(cat "$f"); found=1
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM -- "-$pid" 2>/dev/null
    ok "$(label "$name") stopped"
  else
    info "$(label "$name") wasn't running"
  fi
  rm -f "$f"
done
[ -n "$found" ] || info "Nothing was running."
