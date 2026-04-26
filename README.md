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

## Setup

### 1. Create a Discord Application

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** — name it whatever you want (this shows as the activity title)
3. Copy the **Application ID** (this is your Client ID)
4. Go to **Rich Presence > Art Assets** and upload two images:
   - `apple_music` — large icon (e.g. Apple Music logo)
   - `playing` — small icon for playing state
   - `paused` — small icon for paused state

### 2. Install & Run

```bash
git clone https://github.com/40960/apple-music-discord-rpc.git
cd apple-music-discord-rpc
pip install -r requirements.txt

export DISCORD_CLIENT_ID="your_application_id_here"
python apple_music_discord.py
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_CLIENT_ID` | Yes | — | Your Discord Application ID |
| `IDLE_TIMEOUT` | No | `300` | Seconds before clearing status when paused |

## How It Works

Uses AppleScript to poll Apple Music every 5 seconds, then pushes the track info to Discord via Rich Presence (pypresence).

### Display Layout

```
Playing
[App Name]                        ← set in Discord Developer Portal
Song Title
by Artist · 1:22 / 3:35
🕐 00:45:00                       ← session listening time
[Search on Apple Music]           ← visible to others only
```

## Requirements

- macOS (uses AppleScript to talk to Apple Music)
- Python 3.8+
- Discord desktop app running
- Apple Music app (not the web player)

## License

AGPL-3.0
