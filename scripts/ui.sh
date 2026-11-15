# Shared output for install.sh, start.sh and stop.sh: headings, ticks and plain-language problems. Sourced, not run.
# Colour only in a terminal, and never when NO_COLOR is set.
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  BOLD=$'\e[1m' DIM=$'\e[2m' GREEN=$'\e[32m' YELLOW=$'\e[33m' RED=$'\e[31m' RESET=$'\e[0m'; TTY=1
else
  BOLD='' DIM='' GREEN='' YELLOW='' RED='' RESET=''; TTY=''
fi
step(){ printf '\n%s== %s%s\n' "$BOLD" "$*" "$RESET"; }
ok(){ printf '   %s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
info(){ printf '     %s%s%s\n' "$DIM" "$*" "$RESET"; }
warn(){ printf '   %s!%s %s\n' "$YELLOW" "$RESET" "$*"; }
die(){ printf '\n%sStopped:%s %s\n' "$RED" "$RESET" "$*"; exit 1; }
# One line that rewrites itself in a terminal (a timer while something loads); elsewhere it prints nothing.
progress(){ [ -n "$TTY" ] && printf '\r\e[K   %s…%s %s' "$DIM" "$RESET" "$*"; return 0; }
progress_end(){ [ -n "$TTY" ] && printf '\r\e[K'; return 0; }
duration(){ local s=$1; if [ "$s" -ge 60 ]; then printf '%d min %d s' $((s / 60)) $((s % 60)); else printf '%d s' "$s"; fi; }

# What each process that start.sh runs is, in words.
label(){ case $1 in
  voxtral) echo "Hearing (Voxtral)" ;;
  sparklm) echo "Voice model (Spark)" ;;
  spark) echo "Voice decoder (Spark)" ;;
  gemma) echo "Brain (Gemma 4)" ;;
  app) echo "Tutor web app" ;;
  app_cloud) echo "Tutor web app, cloud copy" ;;
  app_test) echo "Tutor web app, test copy" ;;
  *) echo "$1" ;;
esac; }
