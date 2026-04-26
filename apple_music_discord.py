#!/usr/bin/env python3
"""
Apple Music Discord Rich Presence for macOS
"""
import os
import time
import subprocess
import sys
import threading
from urllib.parse import quote
from pypresence import Presence, exceptions

try:
    import rumps
    HAS_RUMPS = True
except ImportError:
    HAS_RUMPS = False

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
        pass
    except Exception:
        pass
    return None


def connect_rpc():
    RPC = Presence(CLIENT_ID)
    RPC.connect()
    return RPC


class JsonParasite:
    """Core polling logic, UI-agnostic."""

    def __init__(self):
        self.RPC = None
        self.last_track = None
        self.last_info = None
        self.last_position = 0
        self.session_start = None
        self.was_playing = False
        self.paused_at = None
        self.status = "Idle"
        self.track_display = ""
        self.running = True
        self.hidden = False

    def hide(self):
        self.hidden = True
        try:
            if self.RPC:
                self.RPC.clear()
                self.RPC.close()
        except Exception:
            pass
        self.RPC = None
        self.status = "Hidden"

    def unhide(self):
        self.hidden = False
        self.was_playing = False
        self.status = "Resuming..."

    def tick(self):
        if self.hidden:
            return

        if self.RPC is None:
            try:
                self.RPC = connect_rpc()
                self.status = "Connected"
            except Exception:
                self.status = "Waiting for Discord..."
                return

        try:
            track = get_apple_music_info()

            if track and track['is_playing']:
                current_key = f"{track['name']}|{track['artist']}"

                if not self.was_playing:
                    if self.session_start is None:
                        self.session_start = time.time()
                    self.paused_at = None

                if self.last_track != current_key or not self.was_playing:
                    self.last_track = current_key
                    self.last_info = track
                    self.was_playing = True

                pos = int(track['position'])
                dur = int(track['duration'])
                self.last_position = pos
                progress = f"{pos // 60}:{pos % 60:02d} / {dur // 60}:{dur % 60:02d}"

                album = track['album']
                hover = f"{track['name']} - {album}" if album else track['name']
                search_url = f"https://music.apple.com/search?term={quote(track['name'] + ' ' + track['artist'])}"

                title = f"{track['name']} - {album}" if album else track['name']

                self.RPC.update(
                    details=title[:128],
                    state=f"by {track['artist'][:120]} · {progress}",
                    large_image="apple_music",
                    large_text=hover[:128],
                    small_image="playing",
                    small_text="Playing",
                    start=self.session_start,
                    buttons=[{"label": "Search on Apple Music", "url": search_url}],
                )

                self.status = "Sharing"
                self.track_display = f"{track['name']} - {track['artist']}"

            else:
                if self.was_playing:
                    self.was_playing = False
                    self.paused_at = time.time()

                if self.paused_at and time.time() - self.paused_at >= IDLE_TIMEOUT:
                    self.RPC.clear()
                    self.last_track = None
                    self.last_info = None
                    self.session_start = None
                    self.paused_at = None
                    self.status = "Idle"
                    self.track_display = ""
                elif self.last_info:
                    pos = self.last_position
                    dur = int(self.last_info['duration'])
                    progress = f"{pos // 60}:{pos % 60:02d} / {dur // 60}:{dur % 60:02d}"

                    paused_title = f"{self.last_info['name']} - {self.last_info['album']}" if self.last_info['album'] else self.last_info['name']

                    self.RPC.update(
                        details=paused_title[:128],
                        state=f"by {self.last_info['artist'][:120]} · {progress}",
                        large_image="apple_music",
                        large_text=f"{self.last_info['name']} - {self.last_info['album']}"[:128] if self.last_info['album'] else self.last_info['name'][:128],
                        small_image="paused",
                        small_text="Paused",
                        start=self.session_start,
                    )
                    self.status = "Paused"

        except (exceptions.DiscordNotFound, exceptions.InvalidPipe,
                exceptions.PipeClosed, BrokenPipeError,
                ConnectionResetError, OSError):
            try:
                self.RPC.close()
            except Exception:
                pass
            self.RPC = None
            self.was_playing = False
            self.status = "Reconnecting..."
        except exceptions.InvalidID:
            self.status = "Invalid Client ID"
            self.running = False
        except Exception as e:
            self.status = f"Error: {e}"

    def cleanup(self):
        try:
            if self.RPC:
                self.RPC.clear()
                self.RPC.close()
        except Exception:
            pass


def run_headless(parasite):
    """Terminal-only mode (no menu bar icon)."""
    print("🎵 Apple Music Discord Rich Presence")
    print("=" * 40)
    print("⏳ Monitoring... (Ctrl+C to stop)")
    print()

    try:
        while parasite.running:
            parasite.tick()
            prev = parasite.status
            if parasite.status != prev or parasite.status == "Playing":
                print(f"[{parasite.status}] {parasite.track_display}")
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        parasite.cleanup()
        print("\n👋 Goodbye!")


def run_menubar(parasite):
    """Menu bar mode using rumps."""

    class MusicRPCApp(rumps.App):
        def __init__(self):
            super().__init__("🎵", quit_button=None)
            self.menu = [
                rumps.MenuItem("Apple Music Discord RPC", callback=None),
                None,
                rumps.MenuItem("Status: Starting...", callback=None),
                rumps.MenuItem("Track: —", callback=None),
                None,
                rumps.MenuItem("Hide Status", callback=self.toggle_visibility),
                None,
                rumps.MenuItem("Quit", callback=self.quit_app),
            ]
            self.status_item = self.menu["Status: Starting..."]
            self.track_item = self.menu["Track: —"]
            self.visibility_item = self.menu["Hide Status"]

        @rumps.timer(5)
        def poll(self, _):
            parasite.tick()

            state = parasite.status
            self.status_item.title = f"Status: {state}"

            if parasite.track_display:
                self.track_item.title = parasite.track_display[:60]
            else:
                self.track_item.title = "Track: —"

            if parasite.hidden:
                self.title = "🙈"
            elif state == "Sharing":
                self.title = "🎵"
            elif state == "Paused":
                self.title = "⏸"
            elif state == "Idle":
                self.title = "🎵"
            else:
                self.title = "⚠️"

        def toggle_visibility(self, sender):
            if parasite.hidden:
                parasite.unhide()
                sender.title = "Hide Status"
            else:
                parasite.hide()
                sender.title = "Share Status"

        def quit_app(self, _):
            parasite.running = False
            parasite.cleanup()
            rumps.quit_application()

    try:
        from AppKit import NSApplication
        NSApplication.sharedApplication().setActivationPolicy_(1)
    except ImportError:
        pass

    MusicRPCApp().run()


def main():
    if not CLIENT_ID:
        print("❌ Set DISCORD_CLIENT_ID environment variable first.")
        print("   Create an app at https://discord.com/developers/applications")
        sys.exit(1)

    parasite = JsonParasite()

    if HAS_RUMPS and "--no-gui" not in sys.argv:
        run_menubar(parasite)
    else:
        run_headless(parasite)


if __name__ == "__main__":
    main()
