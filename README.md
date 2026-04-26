# Apple Music Discord Rich Presence

Show what you're listening to on Apple Music as your Discord status — macOS only.

<img width="491" height="195" alt="image" src="https://github.com/user-attachments/assets/bf82abd7-2546-4d34-9a55-9a38ffc545f7" />

## Features

- Displays song name, artist, album, and progress
- "Search on Apple Music" button for others to find the track
- Paused state with frozen progress
- Auto-clears after 5 minutes of inactivity
- Auto-reconnects when Discord restarts
- Session timer shows how long you've been listening
- Menu bar icon with status and hide/share toggle
- Auto-start on login via macOS LaunchAgent

## Setup

### 1. Create a Discord Application

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** — name it whatever you want (this shows as the activity title)
3. Copy the **Application ID** (this is your Client ID)
4. Go to **Rich Presence > Art Assets** and upload images:
   - `apple_music` — large icon (e.g. Apple Music logo)
   - `playing` — small icon for playing state
   - `paused` — small icon for paused state

### 2. Install

```bash
git clone https://github.com/40960/apple-music-discord-rpc.git
cd apple-music-discord-rpc
./install.sh YOUR_CLIENT_ID
```

This will:
- Create a Python virtual environment and install dependencies
- Register a macOS LaunchAgent for auto-start on login
- Start the app immediately

A 🎵 icon will appear in your menu bar.

### Uninstall

```bash
./uninstall.sh
```

### Manual Run (no auto-start)

```bash
pip install -r requirements.txt
export DISCORD_CLIENT_ID="your_id"
python apple_music_discord.py
```

Use `--no-gui` for terminal-only mode (no menu bar icon).

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_CLIENT_ID` | Yes | — | Your Discord Application ID |
| `IDLE_TIMEOUT` | No | `300` | Seconds before clearing status when paused |

## Menu Bar

| Icon | State |
|------|-------|
| 🎵 | Sharing / Idle |
| ⏸ | Paused |
| 🙈 | Hidden (status not shared) |
| ⚠️ | Error / Reconnecting |

Click the icon to see current track, status, and toggle visibility.

## How It Works

Uses AppleScript to poll Apple Music every 5 seconds, then pushes the track info to Discord via Rich Presence ([pypresence](https://github.com/qwertyquerty/pypresence)). Auto-start is handled by a standard macOS [LaunchAgent](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html) plist.

## Requirements

- macOS (uses AppleScript to talk to Apple Music)
- Python 3.8+
- Discord desktop app
- Apple Music app (not the web player)

## License

AGPL-3.0
