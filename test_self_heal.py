import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import apple_music_discord
from apple_music_discord import executable_is_stale, parse_music_payload

# A framework build of python re-execs itself into Python.app, so a copied
# python binary reports the framework's path rather than the copy's. The stub
# below never re-execs, which is what makes the deletion observable.
STUB_SOURCE = """
#include <unistd.h>
int main(void) { for (;;) pause(); return 0; }
"""


class StaleExecutableTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _reap(self, proc):
        if proc.poll() is None:
            proc.kill()
        proc.wait()

    def _spawn_stub(self):
        """Run a stub binary from a Homebrew-shaped versioned directory."""
        source = os.path.join(self.root, "stub.c")
        with open(source, "w") as handle:
            handle.write(STUB_SOURCE)

        version_dir = os.path.join(self.root, "Cellar", "stub", "1.0.0")
        binary = os.path.join(version_dir, "bin", "stub")
        os.makedirs(os.path.dirname(binary))

        built = subprocess.run(["xcrun", "clang", "-o", binary, source],
                               capture_output=True, text=True)
        if built.returncode != 0:
            self.skipTest(f"clang unavailable: {built.stderr.strip()[:120]}")

        proc = subprocess.Popen([binary])
        self.addCleanup(self._reap, proc)

        for _ in range(100):
            if not executable_is_stale(proc.pid):
                return proc, binary, version_dir
            time.sleep(0.02)
        self.fail("stub process never became path-resolvable")

    def test_running_process_with_intact_executable_is_not_stale(self):
        proc, _, _ = self._spawn_stub()
        self.assertFalse(executable_is_stale(proc.pid))

    def test_detects_executable_deleted_underneath_running_process(self):
        proc, binary, _ = self._spawn_stub()
        os.unlink(binary)
        self.assertTrue(executable_is_stale(proc.pid))

    def test_detects_homebrew_style_version_directory_removal(self):
        proc, _, version_dir = self._spawn_stub()
        shutil.rmtree(version_dir)
        self.assertTrue(executable_is_stale(proc.pid))

    def test_our_own_process_is_not_stale(self):
        self.assertFalse(executable_is_stale())

    def test_exited_process_is_not_reported_as_stale(self):
        # A reaped pid reports ESRCH, not ENOENT. Treating that as stale would
        # restart the app for the wrong reason.
        proc = subprocess.Popen(["/bin/echo"], stdout=subprocess.DEVNULL)
        proc.wait()
        self.assertFalse(executable_is_stale(proc.pid))


class StaleExecutableGuardTests(unittest.TestCase):
    """tick() must bail out before touching Discord or Music when we are stale."""

    def setUp(self):
        self.parasite = apple_music_discord.JsonParasite()

    def test_tick_exits_non_zero_so_launchd_respawns(self):
        with mock.patch.object(apple_music_discord, "executable_is_stale", return_value=True), \
             mock.patch.object(apple_music_discord, "get_apple_music_info") as music, \
             mock.patch.object(apple_music_discord.os, "_exit") as exit_call:
            self.parasite.tick()

        exit_call.assert_called_once_with(1)
        music.assert_not_called()
        self.assertEqual(self.parasite.status, "Restarting...")

    def test_tick_proceeds_normally_when_not_stale(self):
        with mock.patch.object(apple_music_discord, "executable_is_stale", return_value=False), \
             mock.patch.object(apple_music_discord, "connect_rpc", side_effect=OSError("no discord")), \
             mock.patch.object(apple_music_discord.os, "_exit") as exit_call:
            self.parasite.tick()

        exit_call.assert_not_called()
        self.assertEqual(self.parasite.status, "Waiting for Discord...")


class StatusFreshnessTests(unittest.TestCase):
    """A stale status must never outlive the condition that produced it."""

    def setUp(self):
        self.parasite = apple_music_discord.JsonParasite()
        self.parasite.RPC = mock.MagicMock()
        self.parasite.connected_label = "Discord"

    def _tick_with(self, track=None, error=None):
        info = mock.patch.object(
            apple_music_discord, "get_apple_music_info",
            side_effect=error if error else None,
            return_value=track)
        with mock.patch.object(apple_music_discord, "executable_is_stale", return_value=False), info:
            self.parasite.tick()

    STOPPED = {"is_playing": False, "name": "", "artist": "",
               "album": "", "duration": 0, "position": 0}

    def test_idle_status_replaces_a_stale_error(self):
        self.parasite.status = "Music unavailable: osascript timed out after 5s"

        self._tick_with(track=self.STOPPED)

        self.assertEqual(self.parasite.status, "Idle")

    def test_transient_failure_keeps_the_previous_status(self):
        self.parasite.status = "Sharing to Discord"

        self._tick_with(error=apple_music_discord.MusicQueryError("osascript timed out after 5s"))

        self.assertEqual(self.parasite.status, "Sharing to Discord")

    def test_persistent_failure_surfaces_the_error(self):
        self.parasite.status = "Sharing to Discord"
        err = apple_music_discord.MusicQueryError("osascript timed out after 5s")

        for _ in range(apple_music_discord.MUSIC_FAILURE_GRACE):
            self._tick_with(error=err)

        self.assertIn("Music unavailable", self.parasite.status)

    PAUSED = {"is_playing": False, "name": "will of the heart", "artist": "Shiro SAGISU",
              "album": "BLEACH OST 1", "duration": 228.0, "position": 148.0}

    def test_paused_track_is_shown_even_without_having_seen_it_play(self):
        """After a restart while paused, Music still reports the track."""
        self._tick_with(track=self.PAUSED)

        self.assertEqual(self.parasite.status, "Paused on Discord")
        self.assertEqual(self.parasite.track_display,
                         "will of the heart - Shiro SAGISU")

    def test_one_success_resets_the_failure_budget(self):
        err = apple_music_discord.MusicQueryError("boom")
        self._tick_with(error=err)
        self._tick_with(error=err)

        self._tick_with(track=self.STOPPED)
        self.assertEqual(self.parasite.status, "Idle")

        self._tick_with(error=err)
        self.assertEqual(self.parasite.status, "Idle")


class MusicPayloadTests(unittest.TestCase):
    def test_parses_playing_payload(self):
        track = parse_music_payload("playing|will of the heart|Shiro SAGISU|BLEACH OST 1|228.13|148.70\n")

        self.assertTrue(track["is_playing"])
        self.assertEqual(track["name"], "will of the heart")
        self.assertEqual(track["artist"], "Shiro SAGISU")
        self.assertEqual(track["album"], "BLEACH OST 1")
        self.assertAlmostEqual(track["duration"], 228.13)
        self.assertAlmostEqual(track["position"], 148.70)

    def test_reports_stopped_payload(self):
        track = parse_music_payload("stopped||||0|0\n")

        self.assertFalse(track["is_playing"])
        self.assertEqual(track["name"], "")
        self.assertEqual(track["duration"], 0)

    def test_keeps_pipe_characters_in_album_name(self):
        track = parse_music_payload("playing|Song|Artist|Best Of|Rarities|180|30\n")

        self.assertEqual(track["album"], "Best Of|Rarities")
        self.assertEqual(track["duration"], 180)
        self.assertEqual(track["position"], 30)

    def test_parses_paused_payload_with_track_details(self):
        track = parse_music_payload("paused|will of the heart|Shiro SAGISU|BLEACH OST 1|228.13|148.70\n")

        self.assertFalse(track["is_playing"])
        self.assertEqual(track["name"], "will of the heart")
        self.assertAlmostEqual(track["position"], 148.70)

    def test_rejects_truncated_payload(self):
        self.assertIsNone(parse_music_payload("playing|Song|Artist\n"))

    def test_rejects_unparsable_numbers(self):
        self.assertIsNone(parse_music_payload("playing|Song|Artist|Album|abc|30\n"))


if __name__ == "__main__":
    unittest.main()
