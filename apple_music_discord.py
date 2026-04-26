#!/usr/bin/env python3
"""
Apple Music Discord Rich Presence for macOS
"""
import os
import time
import subprocess
import sys
from urllib.parse import quote
from pypresence import Presence, exceptions

CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "")

IDLE_TIMEOUT = int(os.environ.get("IDLE_TIMEOUT", "300"))

def get_apple_music_info():
    script = '''
    tell application "Music"
        if player state is playing then
            set track_name to name of current track
            set track_artist to artist of current track
            set track_album to album of current track
            set track_duration to duration of current track
            set player_position to player position
            set is_playing to "playing"
        else
            set is_playing to "stopped"
            set track_name to ""
            set track_artist to ""
            set track_album to ""
            set track_duration to 0
            set player_position to 0
        end if
    end tell
    return is_playing & "|" & track_name & "|" & track_artist & "|" & track_album & "|" & track_duration & "|" & player_position
    '''
    try:
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            parts = result.stdout.strip().split("|")
            if len(parts) >= 6:
                return {
                    'is_playing': parts[0] == "playing",
                    'name': parts[1] if len(parts) > 1 else "",
                    'artist': parts[2] if len(parts) > 2 else "",
                    'album': parts[3] if len(parts) > 3 else "",
                    'duration': float(parts[4]) if len(parts) > 4 and parts[4] else 0,
                    'position': float(parts[5]) if len(parts) > 5 and parts[5] else 0
                }
    except subprocess.TimeoutExpired:
        print("AppleScript timed out")
    except Exception as e:
        print(f"Error getting Apple Music info: {e}")
    return None

def connect_rpc():
    RPC = Presence(CLIENT_ID)
    RPC.connect()
    return RPC

def main():
    if not CLIENT_ID:
        print("❌ Set DISCORD_CLIENT_ID environment variable first.")
        print("   Create an app at https://discord.com/developers/applications")
        sys.exit(1)

    print("🎵 Apple Music Discord Rich Presence")
    print("=" * 40)
    print("⏳ Monitoring Apple Music... (Press Ctrl+C to stop)")
    print()

    RPC = None
    last_track = None
    last_info = None
    last_position = 0
    session_start = None
    was_playing = False
    paused_at = None

    try:
        while True:
            if RPC is None:
                try:
                    RPC = connect_rpc()
                    print("✅ Connected to Discord RPC")
                except Exception:
                    time.sleep(10)
                    continue

            try:
                track = get_apple_music_info()

                if track and track['is_playing']:
                    current_key = f"{track['name']}|{track['artist']}"

                    if not was_playing:
                        if session_start is None:
                            session_start = time.time()
                            print("🎧 Session started")
                        paused_at = None

                    if last_track != current_key or not was_playing:
                        last_track = current_key
                        last_info = track
                        was_playing = True

                        print(f"▶️  Now Playing: {track['name']} - {track['artist']}")
                        print(f"   Album: {track['album']}")
                        print(f"   Progress: {int(track['position'])//60}:{int(track['position'])%60:02d} / {int(track['duration'])//60}:{int(track['duration'])%60:02d}")
                        print()

                    pos = int(track['position'])
                    dur = int(track['duration'])
                    last_position = pos
                    progress = f"{pos//60}:{pos%60:02d} / {dur//60}:{dur%60:02d}"

                    album = track['album']
                    hover = f"{track['name']} - {album}" if album else track['name']

                    search_url = f"https://music.apple.com/search?term={quote(track['name'] + ' ' + track['artist'])}"

                    RPC.update(
                        details=track['name'][:128],
                        state=f"by {track['artist'][:120]} · {progress}",
                        large_image="apple_music",
                        large_text=hover[:128],
                        small_image="playing",
                        small_text="Playing",
                        start=session_start,
                        buttons=[{"label": "Search on Apple Music", "url": search_url}],
                    )

                else:
                    if was_playing:
                        was_playing = False
                        paused_at = time.time()
                        print("⏸️  Paused")
                        print()

                    if paused_at and time.time() - paused_at >= IDLE_TIMEOUT:
                        RPC.clear()
                        last_track = None
                        last_info = None
                        session_start = None
                        paused_at = None
                        print("💤 Idle for 5min — cleared status")
                        print()
                    elif last_info:
                        pos = last_position
                        dur = int(last_info['duration'])
                        progress = f"{pos//60}:{pos%60:02d} / {dur//60}:{dur%60:02d}"

                        RPC.update(
                            details=last_info['name'][:128],
                            state=f"by {last_info['artist'][:120]} · {progress}",
                            large_image="apple_music",
                            large_text=f"{last_info['name']} - {last_info['album']}"[:128] if last_info['album'] else last_info['name'][:128],
                            small_image="paused",
                            small_text="Paused",
                            start=session_start,
                        )

            except (exceptions.DiscordNotFound, exceptions.InvalidPipe,
                    exceptions.PipeClosed, BrokenPipeError,
                    ConnectionResetError, OSError):
                print("❌ Discord disconnected. Reconnecting...")
                try:
                    RPC.close()
                except Exception:
                    pass
                RPC = None
                was_playing = False
                continue
            except exceptions.InvalidID:
                print("❌ Invalid Client ID.")
                break
            except Exception as e:
                print(f"⚠️  Error: {e}")

            time.sleep(5)

    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
        try:
            if RPC:
                RPC.clear()
                RPC.close()
        except Exception:
            pass
        print("👋 Goodbye!")

if __name__ == "__main__":
    main()
