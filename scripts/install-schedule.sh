#!/usr/bin/env bash
# Install (or remove) the daily automatic update on this Mac (scripts/update.sh).
#
#   ./scripts/install-schedule.sh          install, every day 06:00 local
#   ./scripts/install-schedule.sh remove   uninstall
#   ./scripts/install-schedule.sh status   is it installed, did it last succeed
#
# Uses launchd rather than cron. The difference that matters on a laptop: if the
# machine is asleep at 06:00, launchd runs the job when it next wakes. cron just
# skips it, so a laptop that is closed every morning would never update.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
LABEL="com.civicalign.update"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$ROOT/data/update.log"

case "${1:-install}" in
  remove)
    launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "removed. Nothing is scheduled now."
    ;;
  status)
    if [ -f "$PLIST" ]; then
      echo "installed: $PLIST"
      launchctl print "gui/$UID/$LABEL" 2>/dev/null | grep -E "state|last exit" || true
      [ -f "$LOG" ] && { echo; echo "last run:"; tail -6 "$LOG"; }
    else
      echo "not installed. Run this script with no arguments to schedule it."
    fi
    ;;
  install)
    mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/data"
    cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT/scripts/update.sh</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>6</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
PLIST_EOF
    launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
    launchctl bootstrap "gui/$UID" "$PLIST"
    echo "installed. Runs every day at 06:00, or at the next wake if asleep."
    echo "  log:    $LOG"
    echo "  check:  ./scripts/install-schedule.sh status"
    echo "  remove: ./scripts/install-schedule.sh remove"
    ;;
  *) echo "usage: $0 [install|remove|status]"; exit 1 ;;
esac
