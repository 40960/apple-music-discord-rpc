import unittest
from unittest import mock

import apple_music_discord as amd


class DiscoveryStalenessTests(unittest.TestCase):
    """Deciding whether the expensive owner lookup has to run again."""

    def cache(self, sockets, at):
        return {"sockets": sockets, "clients": [], "at": at}

    def test_empty_cache_is_stale(self):
        self.assertTrue(amd.discovery_is_stale(["/tmp/discord-ipc-0"],
                                               self.cache(None, 0.0), now=100.0))

    def test_unchanged_sockets_within_ttl_are_fresh(self):
        cache = self.cache(["/tmp/discord-ipc-0"], at=100.0)
        self.assertFalse(amd.discovery_is_stale(["/tmp/discord-ipc-0"], cache, now=105.0))

    def test_a_new_socket_forces_an_immediate_refresh(self):
        cache = self.cache(["/tmp/discord-ipc-0"], at=100.0)
        self.assertTrue(amd.discovery_is_stale(
            ["/tmp/discord-ipc-0", "/tmp/discord-ipc-1"], cache, now=101.0))

    def test_a_disappearing_socket_forces_an_immediate_refresh(self):
        cache = self.cache(["/tmp/discord-ipc-0"], at=100.0)
        self.assertTrue(amd.discovery_is_stale([], cache, now=101.0))

    def test_cache_expires_after_the_ttl(self):
        cache = self.cache(["/tmp/discord-ipc-0"], at=100.0)
        self.assertTrue(amd.discovery_is_stale(["/tmp/discord-ipc-0"], cache,
                                               now=100.0 + amd.DISCOVERY_TTL))


class DiscoveryCachingTests(unittest.TestCase):
    """The lsof work must not run on every poll."""

    def setUp(self):
        amd.reset_discovery_cache()
        self.addCleanup(amd.reset_discovery_cache)

    def _patch(self, sockets, resolver):
        return (mock.patch.object(amd, "discord_socket_paths", side_effect=sockets),
                mock.patch.object(amd, "resolve_discord_clients", side_effect=resolver))

    def test_repeated_polls_resolve_owners_only_once(self):
        socks, res = self._patch(lambda: ["/tmp/discord-ipc-0"], lambda s: ["stable"])
        with socks, res as resolver:
            for _ in range(10):
                amd.discover_discord_clients()

        self.assertEqual(resolver.call_count, 1)

    def test_cached_result_is_returned_verbatim(self):
        socks, res = self._patch(lambda: ["/tmp/discord-ipc-0"], lambda s: ["stable"])
        with socks, res:
            first = amd.discover_discord_clients()
            second = amd.discover_discord_clients()

        self.assertEqual(first, ["stable"])
        self.assertEqual(second, ["stable"])

    def test_socket_change_resolves_again_without_waiting_for_the_ttl(self):
        seen = [["/tmp/discord-ipc-0"], ["/tmp/discord-ipc-0", "/tmp/discord-ipc-1"]]
        socks, res = self._patch(lambda: seen.pop(0), lambda s: list(s))
        with socks, res as resolver:
            amd.discover_discord_clients()
            amd.discover_discord_clients()

        self.assertEqual(resolver.call_count, 2)

    def test_force_bypasses_the_cache(self):
        socks, res = self._patch(lambda: ["/tmp/discord-ipc-0"], lambda s: ["stable"])
        with socks, res as resolver:
            amd.discover_discord_clients()
            amd.discover_discord_clients(force=True)

        self.assertEqual(resolver.call_count, 2)


if __name__ == "__main__":
    unittest.main()
