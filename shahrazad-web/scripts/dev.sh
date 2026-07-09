#!/usr/bin/env bash
# Run Next dev with a modern Node (Next 15 needs Node >= 18).
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -x "$HOME/.local/node/bin/node" ]]; then
  export PATH="$HOME/.local/node/bin:$PATH"
fi

if command -v nvm >/dev/null 2>&1 && [[ -f .nvmrc ]]; then
  # shellcheck disable=SC1090
  source "$(nvm which node 2>/dev/null || true)" 2>/dev/null || true
fi

node scripts/check-node.mjs
exec npx next dev "$@"
