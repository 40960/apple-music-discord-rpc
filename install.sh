#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.apple-music-discord-rpc.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

# Check for DISCORD_CLIENT_ID
if [ -z "$1" ]; then
    echo "Usage: ./install.sh <DISCORD_CLIENT_ID>"
    echo ""
    echo "Get your Client ID from https://discord.com/developers/applications"
    exit 1
fi

CLIENT_ID="$1"

# Create venv and install deps
echo "📦 Setting up Python environment..."
python3 -m venv "$SCRIPT_DIR/venv"
"$SCRIPT_DIR/venv/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"

# Unload existing agent if present
if launchctl list | grep -q "$PLIST_NAME" 2>/dev/null; then
    echo "🔄 Removing existing LaunchAgent..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

# Write LaunchAgent plist
echo "📝 Installing LaunchAgent..."
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/venv/bin/python3</string>
        <string>$SCRIPT_DIR/apple_music_discord.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>DISCORD_CLIENT_ID</key>
        <string>$CLIENT_ID</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/apple-music-discord-rpc.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/apple-music-discord-rpc.log</string>
</dict>
</plist>
EOF

# Load the agent
launchctl load "$PLIST_PATH"

echo ""
echo "✅ Installed and started!"
echo "   Menu bar icon: 🎵"
echo "   Logs: /tmp/apple-music-discord-rpc.log"
echo ""
echo "To uninstall: ./uninstall.sh"
