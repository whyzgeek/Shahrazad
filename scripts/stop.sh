#!/bin/bash
# Stops everything scripts/start.sh started.
cd "$(dirname "$0")/.." || exit 1
R=run
for n in app spark sparklm gemma voxtral; do
  if [ -f "${R:?}/${n:?}.pid" ]; then
    kill -TERM -- "-$(cat "${R:?}/${n:?}.pid")" 2>/dev/null
    rm -f "${R:?}/${n:?}.pid"
  fi
done
echo stopped
