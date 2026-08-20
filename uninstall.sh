#!/bin/bash
set -uo pipefail

LABEL="com.40960.apple-music-discord-rpc"
removed=0

# Both the current label and the pre-namespacing one it may still be installed under
for plist_name in "$LABEL.plist" "com.apple-music-discord-rpc.plist"; do
    plist_path="$HOME/Library/LaunchAgents/$plist_name"
    [ -f "$plist_path" ] || continue
    echo "🛑 Stopping and removing $plist_name..."
    launchctl bootout "gui/$UID/${plist_name%.plist}" 2>/dev/null || true
    launchctl bootout "gui/$UID/$plist_name" 2>/dev/null || true
    rm -f "$plist_path"
    removed=1
done

if [ "$removed" -eq 1 ]; then
    echo "✅ Uninstalled."
    echo "   Log kept at ~/Library/Logs/apple-music-discord-rpc.log"
else
    echo "Nothing to uninstall."
fi
