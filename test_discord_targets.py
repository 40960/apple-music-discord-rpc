import unittest

from apple_music_discord import (
    DiscordClient,
    choose_discord_clients,
    classify_discord_app,
    extract_pipe_number,
)


class DiscordTargetTests(unittest.TestCase):
    def test_classifies_discord_variants_from_owner_paths(self):
        self.assertEqual(classify_discord_app("/Applications/Discord.app/Contents/MacOS/Discord"), "stable")
        self.assertEqual(classify_discord_app("/Applications/Discord PTB.app/Contents/MacOS/Discord PTB"), "ptb")
        self.assertEqual(classify_discord_app("/Applications/Discord Canary.app/Contents/MacOS/Discord Canary"), "canary")
        self.assertIsNone(classify_discord_app("/Applications/Slack.app/Contents/MacOS/Slack"))

    def test_extracts_pipe_number_from_socket_path(self):
        self.assertEqual(extract_pipe_number("/tmp/discord-ipc-0"), 0)
        self.assertEqual(extract_pipe_number("/tmp/discord-ipc-12"), 12)
        self.assertIsNone(extract_pipe_number("/tmp/not-discord-ipc-0"))

    def test_auto_prefers_stable_over_ptb_regardless_of_pipe_number(self):
        clients = [
            DiscordClient("ptb", "Discord PTB", "/tmp/discord-ipc-0", 0),
            DiscordClient("stable", "Discord", "/tmp/discord-ipc-1", 1),
        ]

        chosen = choose_discord_clients(clients, "auto")

        self.assertEqual([client.variant for client in chosen], ["stable"])
        self.assertEqual(chosen[0].pipe, 1)

    def test_specific_target_selects_matching_client(self):
        clients = [
            DiscordClient("stable", "Discord", "/tmp/discord-ipc-0", 0),
            DiscordClient("ptb", "Discord PTB", "/tmp/discord-ipc-1", 1),
        ]

        chosen = choose_discord_clients(clients, "ptb")

        self.assertEqual([client.variant for client in chosen], ["ptb"])

    def test_all_selects_every_running_client_in_preferred_order(self):
        clients = [
            DiscordClient("ptb", "Discord PTB", "/tmp/discord-ipc-7", 7),
            DiscordClient("canary", "Discord Canary", "/tmp/discord-ipc-3", 3),
            DiscordClient("stable", "Discord", "/tmp/discord-ipc-2", 2),
        ]

        chosen = choose_discord_clients(clients, "all")

        self.assertEqual([client.variant for client in chosen], ["stable", "ptb", "canary"])


if __name__ == "__main__":
    unittest.main()
