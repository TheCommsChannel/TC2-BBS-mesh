"""Channel Directory conversation: browse and contribute Channels.

Owns the stepped directory (view / post) and the numbered read that the CHL
quick command seeds. Pure: the directory is read and written through the
injected store, which syncs a new Channel to peer BBS Nodes.

Adding a Channel now replicates regardless of whether it arrived through this
menu or the CHP,, quick command — previously only the quick command synced.
"""

from flows.base import stay, end, keep, goto, GOTO_MAIN

CHANNEL_MENU = ("📚CHANNEL DIRECTORY📚\nWhat would you like to do?\n"
                "[V]iew  [P]ost  E[X]IT")


POST_USAGE = "Post Channel Quick Command format:\nCHP,,{channel_name},,{channel_url}"


class ChannelFlow:
    TOPICS = ["CHANNEL_DIRECTORY", "LIST_CHANNELS", "CHECK_CHANNEL"]
    QUICK_COMMANDS = {"chp,,": "quick_post", "chl": "quick_list"}

    def entry(self, deps):
        return stay({"command": "CHANNEL_DIRECTORY", "step": 1}, replies=[CHANNEL_MENU])

    # --- quick commands ---------------------------------------------------

    def quick_post(self, message, deps):
        """CHP,,{name},,{url} — add a channel without stepping.

        The old parser split on "|" while its own usage text promised ",,",
        so this command could never succeed.
        """
        parts = message.split(",,", 2)
        if len(parts) != 3 or not parts[1].strip() or not parts[2].strip():
            return keep(replies=[POST_USAGE])

        _, name, url = parts
        deps.store.add_channel(name, url)
        return keep(replies=[f"Channel '{name}' has been added to the directory."])

    def quick_list(self, message, deps):
        """CHL — list channels and wait for a number."""
        channels = deps.store.get_channels()
        if not channels:
            return keep(replies=["No channels available in the directory."])
        listing = "Available Channels:\n"
        for i, channel in enumerate(channels):
            listing += f"{i + 1:02d}. Name: {channel[0]}\n"
        listing += "\nPlease reply with the number of the channel you want to view."
        return stay({"command": "LIST_CHANNELS", "step": 1, "channels": channels},
                    replies=[listing])

    def advance(self, message, state, deps):
        command = state.get("command")
        if command in ("LIST_CHANNELS", "CHECK_CHANNEL"):
            return self._read_numbered(message, state)

        message = message.strip()
        if len(message) == 2 and message[1] == "x":
            message = message[0]

        step = state.get("step")
        if step == 1:
            return self._menu(message, deps)
        if step == 2:
            return self._view(message, deps)
        if step == 3:
            return self._name(message)
        if step == 4:
            return self._url(message, state, deps)
        return stay(state)

    def _menu(self, message, deps):
        choice = message.lower()
        if choice == "x":
            return goto(GOTO_MAIN)
        if choice == "v":
            channels = deps.store.get_channels()
            if not channels:
                return stay({"command": "CHANNEL_DIRECTORY", "step": 1},
                            replies=["No channels available in the directory.", CHANNEL_MENU])
            listing = "Select a channel number to view:\n" + "\n".join(
                f"[{i}] {channel[0]}" for i, channel in enumerate(channels))
            return stay({"command": "CHANNEL_DIRECTORY", "step": 2}, replies=[listing])
        if choice == "p":
            return stay({"command": "CHANNEL_DIRECTORY", "step": 3},
                        replies=["Name your channel for the directory:"])
        # Legacy stayed silent on anything else.
        return stay({"command": "CHANNEL_DIRECTORY", "step": 1})

    def _view(self, message, deps):
        index = int(message)
        channels = deps.store.get_channels()
        replies = []
        if 0 <= index < len(channels):
            name, url = channels[index]
            replies.append(f"Channel Name: {name}\nChannel URL:\n{url}")
        replies.append(CHANNEL_MENU)
        return stay({"command": "CHANNEL_DIRECTORY", "step": 1}, replies=replies)

    def _name(self, message):
        return stay({"command": "CHANNEL_DIRECTORY", "step": 4, "channel_name": message},
                    replies=["Send a message with your channel URL or PSK:"])

    def _url(self, message, state, deps):
        name = state["channel_name"]
        deps.store.add_channel(name, message)
        return stay(
            {"command": "CHANNEL_DIRECTORY", "step": 1},
            replies=[f"Your channel '{name}' has been added to the directory.", CHANNEL_MENU])

    def _read_numbered(self, message, state):
        channels = state.get("channels", [])
        try:
            index = int(message) - 1
        except ValueError:
            return stay(state, replies=["Invalid input. Please enter a valid channel number."])
        if index < 0 or index >= len(channels):
            return stay(state, replies=["Invalid channel number. Please try again."])
        name, url = channels[index]
        return end(replies=[f"Channel Name: {name}\nChannel URL: {url}"])
