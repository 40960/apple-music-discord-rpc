#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.40960.apple-music-discord-rpc"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
# Shipped before the label was namespaced; removed on install so the two
# agents cannot both run and fight over the same Discord socket.
LEGACY_PLIST="$HOME/Library/LaunchAgents/com.apple-music-discord-rpc.plist"
# ~/Library/Logs persists; /tmp gets swept by macOS and launchd loses the fd.
LOG_PATH="$HOME/Library/Logs/apple-music-discord-rpc.log"

if [ -z "${1:-}" ]; then
    echo "Usage: ./install.sh <DISCORD_CLIENT_ID>"
    echo ""
    echo "Get your Client ID from https://discord.com/developers/applications"
    exit 1
fi

CLIENT_ID="$1"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

# Create venv and install deps
echo "📦 Setting up Python environment..."
python3 -m venv "$SCRIPT_DIR/venv"
"$SCRIPT_DIR/venv/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"

# Stop whatever is already running under either label
for old_label in "$LABEL" "com.apple-music-discord-rpc.plist" "com.apple-music-discord-rpc"; do
    launchctl bootout "gui/$UID/$old_label" 2>/dev/null || true
done
if [ -f "$LEGACY_PLIST" ]; then
    echo "🧹 Removing legacy LaunchAgent..."
    rm -f "$LEGACY_PLIST"
fi

# Optional settings are baked in only when set, so the app keeps its own defaults
optional_env=""
if [ -n "${DISCORD_TARGET:-}" ]; then
    optional_env+="
        <key>DISCORD_TARGET</key>
        <string>$DISCORD_TARGET</string>"
fi
if [ -n "${IDLE_TIMEOUT:-}" ]; then
    optional_env+="
        <key>IDLE_TIMEOUT</key>
        <string>$IDLE_TIMEOUT</string>"
fi

echo "📝 Installing LaunchAgent..."
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/venv/bin/python3</string>
        <string>$SCRIPT_DIR/apple_music_discord.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>DISCORD_CLIENT_ID</key>
        <string>$CLIENT_ID</string>$optional_env
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ProcessType</key>
    <string>Background</string>
    <key>StandardOutPath</key>
    <string>$LOG_PATH</string>
    <key>StandardErrorPath</key>
    <string>$LOG_PATH</string>
</dict>
</plist>
EOF

plutil -lint "$PLIST_PATH" >/dev/null

launchctl bootstrap "gui/$UID" "$PLIST_PATH"

echo ""
echo "✅ Installed and started!"
echo "   Menu bar: a music-note icon (⚠️ if something is wrong)"
echo "   Logs: $LOG_PATH"
echo ""
echo "To uninstall: ./uninstall.sh"
