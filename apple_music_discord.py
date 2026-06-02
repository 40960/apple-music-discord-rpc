#!/usr/bin/env python3
"""
Apple Music Discord Rich Presence for macOS
"""
import os
import re
import time
import subprocess
import sys
import threading
import tempfile
from dataclasses import dataclass
from urllib.parse import quote
from pypresence import Presence, exceptions

try:
    import rumps
    HAS_RUMPS = True
except ImportError:
    HAS_RUMPS = False

CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "")
DISCORD_TARGET = os.environ.get("DISCORD_TARGET", "auto").lower()

IDLE_TIMEOUT = int(os.environ.get("IDLE_TIMEOUT", "300"))

DISCORD_VARIANTS = {
    "stable": "Discord",
    "ptb": "Discord PTB",
    "canary": "Discord Canary",
}
TARGET_ORDER = ("stable", "ptb", "canary")


@dataclass(frozen=True)
class DiscordClient:
    variant: str
    name: str
    path: str
    pipe: int


def normalize_target(target):
    target = (target or "auto").lower()
    if target == "both":
        return "all"
    if target in ("auto", "all", *TARGET_ORDER):
        return target
    return "auto"


def classify_discord_app(owner_path):
    if "/Discord PTB.app/" in owner_path:
        return "ptb"
    if "/Discord Canary.app/" in owner_path:
        return "canary"
    if "/Discord.app/" in owner_path:
        return "stable"
    return None


def extract_pipe_number(socket_path):
    match = re.search(r"/discord-ipc-(\d+)$", socket_path)
    if not match:
        return None
    return int(match.group(1))


def owner_paths_for_socket(socket_path):
    try:
        result = subprocess.run(
            ["lsof", "-Fn", socket_path],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []
    pids = [line[1:] for line in result.stdout.splitlines() if line.startswith("p")]
    owner_paths = []
    for pid in pids:
        try:
            pid_result = subprocess.run(
                ["lsof", "-Fn", "-p", pid],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except Exception:
            continue
        if pid_result.returncode != 0:
            continue
        owner_paths.extend(
            line[1:] for line in pid_result.stdout.splitlines()
            if line.startswith("n/")
        )
    return owner_paths


def discover_discord_clients():
    tempdir = tempfile.gettempdir()
    try:
        entries = list(os.scandir(tempdir))
    except OSError:
        return []

    clients = {}
    for entry in entries:
        if not entry.name.startswith("discord-ipc-"):
            continue
        pipe = extract_pipe_number(entry.path)
        if pipe is None:
            continue

        variant = None
        for owner_path in owner_paths_for_socket(entry.path):
            variant = classify_discord_app(owner_path)
            if variant:
                break
        if not variant:
            continue

        clients[variant] = DiscordClient(
            variant=variant,
            name=DISCORD_VARIANTS[variant],
            path=entry.path,
            pipe=pipe,
        )

    return [clients[variant] for variant in TARGET_ORDER if variant in clients]


def choose_discord_clients(clients, target):
    target = normalize_target(target)
    by_variant = {client.variant: client for client in clients}

    if target == "all":
        return [by_variant[variant] for variant in TARGET_ORDER if variant in by_variant]
    if target == "auto":
        for variant in TARGET_ORDER:
            if variant in by_variant:
                return [by_variant[variant]]
        return []
    if target in by_variant:
        return [by_variant[target]]
    return []


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


class DiscordRPCGroup:
    def __init__(self, clients):
        self.clients = clients
        self.connections = []

    @property
    def label(self):
        if not self.clients:
            return "Discord"
        if len(self.clients) == 1:
            return self.clients[0].name
        return "All Running Clients"

    def connect(self):
        last_error = None
        for client in self.clients:
            try:
                rpc = Presence(CLIENT_ID, pipe=client.pipe)
                rpc.connect()
                self.connections.append((client, rpc))
            except exceptions.InvalidID:
                raise
            except Exception as error:
                last_error = error

        if not self.connections:
            if last_error:
                raise last_error
            raise exceptions.DiscordNotFound

    def update(self, **activity):
        self._call("update", **activity)

    def clear(self):
        self._call("clear")

    def close(self):
        for _, rpc in self.connections:
            try:
                rpc.close()
            except Exception:
                pass
        self.connections = []

    def _call(self, method, **kwargs):
        live_connections = []
        first_error = None

        for client, rpc in self.connections:
            try:
                getattr(rpc, method)(**kwargs)
                live_connections.append((client, rpc))
            except (exceptions.DiscordNotFound, exceptions.InvalidPipe,
                    exceptions.PipeClosed, BrokenPipeError,
                    ConnectionResetError, OSError) as error:
                first_error = first_error or error
                try:
                    rpc.close()
                except Exception:
                    pass
            except exceptions.InvalidID:
                raise

        self.connections = live_connections
        if not self.connections and first_error:
            raise first_error


def connect_rpc(target):
    clients = choose_discord_clients(discover_discord_clients(), target)
    group = DiscordRPCGroup(clients)
    group.connect()
    return group


class JsonParasite:
    """Core polling logic, UI-agnostic."""

    def __init__(self):
        self.RPC = None
        self.target = normalize_target(DISCORD_TARGET)
        self.running_clients = []
        self.connected_label = ""
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

    def refresh_discord_clients(self):
        self.running_clients = discover_discord_clients()
        return self.running_clients

    def set_target(self, target):
        target = normalize_target(target)
        if self.target == target:
            return
        self.target = target
        self.was_playing = False
        self.connected_label = ""
        try:
            if self.RPC:
                self.RPC.clear()
                self.RPC.close()
        except Exception:
            pass
        self.RPC = None
        self.status = "Switching Discord..."

    def target_label(self):
        if self.target == "auto":
            return "Auto"
        if self.target == "all":
            return "All Running Clients"
        return DISCORD_VARIANTS.get(self.target, "Auto")

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
                self.RPC = connect_rpc(self.target)
                self.connected_label = self.RPC.label
                self.status = f"Connected to {self.connected_label}"
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

                self.status = f"Sharing to {self.connected_label}"
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
                    self.status = f"Paused on {self.connected_label}"

        except (exceptions.DiscordNotFound, exceptions.InvalidPipe,
                exceptions.PipeClosed, BrokenPipeError,
                ConnectionResetError, OSError):
            try:
                self.RPC.close()
            except Exception:
                pass
            self.RPC = None
            self.connected_label = ""
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
                rumps.MenuItem("Target: Auto", callback=None),
                rumps.MenuItem("Use Auto", callback=self.select_auto),
                rumps.MenuItem("Use Discord", callback=self.select_stable),
                rumps.MenuItem("Use Discord PTB", callback=self.select_ptb),
                rumps.MenuItem("Use Discord Canary", callback=self.select_canary),
                rumps.MenuItem("Use All Running Clients", callback=self.select_all),
                None,
                rumps.MenuItem("Hide Status", callback=self.toggle_visibility),
                None,
                rumps.MenuItem("Quit", callback=self.quit_app),
            ]
            self.status_item = self.menu["Status: Starting..."]
            self.track_item = self.menu["Track: —"]
            self.target_header = self.menu["Target: Auto"]
            self.target_items = {
                "auto": self.menu["Use Auto"],
                "stable": self.menu["Use Discord"],
                "ptb": self.menu["Use Discord PTB"],
                "canary": self.menu["Use Discord Canary"],
                "all": self.menu["Use All Running Clients"],
            }
            self.visibility_item = self.menu["Hide Status"]
            self.refresh_target_menu()

        @rumps.timer(5)
        def poll(self, _):
            self.refresh_target_menu()
            parasite.tick()

            state = parasite.status
            self.status_item.title = f"Status: {state}"

            if parasite.track_display:
                self.track_item.title = parasite.track_display[:60]
            else:
                self.track_item.title = "Track: —"

            if parasite.hidden:
                self.title = "🙈"
            elif state.startswith("Sharing"):
                self.title = "🎵"
            elif state.startswith("Paused"):
                self.title = "⏸"
            elif state == "Idle":
                self.title = "🎵"
            else:
                self.title = "⚠️"

        def refresh_target_menu(self):
            clients = parasite.refresh_discord_clients()
            running_variants = {client.variant for client in clients}

            self.target_header.title = f"Target: {parasite.target_label()}"
            for target, item in self.target_items.items():
                selected = parasite.target == target
                prefix = "✓ " if selected else ""

                if target == "auto":
                    item.title = f"{prefix}Auto"
                    item.show()
                elif target == "all":
                    item.title = f"{prefix}All Running Clients"
                    item.show() if len(clients) > 1 else item.hide()
                elif target in running_variants:
                    item.title = f"{prefix}{DISCORD_VARIANTS[target]}"
                    item.show()
                else:
                    item.hide()

        def select_auto(self, _):
            parasite.set_target("auto")
            self.refresh_target_menu()

        def select_stable(self, _):
            parasite.set_target("stable")
            self.refresh_target_menu()

        def select_ptb(self, _):
            parasite.set_target("ptb")
            self.refresh_target_menu()

        def select_canary(self, _):
            parasite.set_target("canary")
            self.refresh_target_menu()

        def select_all(self, _):
            parasite.set_target("all")
            self.refresh_target_menu()

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
