#!/usr/bin/env bash
# Runs every test: none needs a GPU, a model or a key, and none touches your learner record or the running tutor.
#
#   scripts/test.sh            everything
#   scripts/test.sh python     only the Python tests (logic, routes, and whole conversations against fake models)
#   scripts/test.sh page       only the page's own code, under Node
#   scripts/test.sh browser    only the page in a phone-sized browser (needs Playwright and its Chromium)
#
# Each part has a time limit, so a hung test can't hang this script.
set -uo pipefail
cd "$(dirname "$0")/.."
. scripts/ui.sh

PYTHON=${PYTHON:-.venv-tutor/bin/python}
[ -x "$PYTHON" ] || PYTHON=python3
WHICH=${1:-all}
FAILED=()

run(){   # run NAME SECONDS COMMAND...: one part, timed and limited
  local name=$1 limit=$2; shift 2
  step "$name"
  local start=$SECONDS
  if timeout "$limit" "$@"; then
    ok "$name passed in $(duration $((SECONDS - start)))"
  else
    local code=$?
    [ "$code" -eq 124 ] && warn "$name took longer than $(duration "$limit") and was stopped" || warn "$name failed"
    FAILED+=("$name")
  fi
}

if [ "$WHICH" = all ] || [ "$WHICH" = python ]; then
  run "Python tests" 600 "$PYTHON" -m pytest -q -p no:cacheprovider tests --ignore=tests/browser
fi

if [ "$WHICH" = all ] || [ "$WHICH" = page ]; then
  if command -v node >/dev/null; then
    run "Page tests (Node)" 120 node --test tests/js/*.test.js
  else
    warn "Node.js isn't installed, so the page's own tests were skipped (they need Node 22 or newer)"
  fi
fi

if [ "$WHICH" = all ] || [ "$WHICH" = browser ]; then
  if "$PYTHON" -c "import playwright" 2>/dev/null; then
    run "Browser tests (phone)" 600 "$PYTHON" -m pytest -q -p no:cacheprovider tests/browser
  else
    warn "Playwright isn't installed, so the browser tests were skipped. To add them:"
    info "$PYTHON -m pip install -r requirements/dev.txt && $PYTHON -m playwright install chromium"
  fi
fi

if [ ${#FAILED[@]} -gt 0 ]; then
  die "failed: ${FAILED[*]}. The output above shows what went wrong."
fi
printf '\n%sAll tests passed.%s\n' "$GREEN" "$RESET"
