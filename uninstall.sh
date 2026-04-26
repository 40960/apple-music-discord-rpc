#!/bin/bash

PLIST_NAME="com.apple-music-discord-rpc.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

if [ -f "$PLIST_PATH" ]; then
    echo "🛑 Stopping and removing LaunchAgent..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm "$PLIST_PATH"
    echo "✅ Uninstalled."
else
    echo "Nothing to uninstall."
fi
