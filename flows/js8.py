"""JS8Call conversation: browse what was heard over HF radio.

Reads Group, Station and Urgent messages through the injected JS8Call
database. Pure — no sqlite connections opened here, and an unconfigured
bridge simply reads as empty rather than raising at the user.
"""

from flows.base import stay, goto, GOTO_MAIN

JS8_MENU = ("JS8Call Menu:\n[G]roup Messages\n[S]tation Messages\n"
            "[U]rgent Messages\nE[X]IT")


class Js8Flow:
    TOPICS = ["JS8CALL_MENU", "GROUP_MESSAGES"]

    def entry(self, deps):
        return stay({"command": "JS8CALL_MENU", "step": 1}, replies=[JS8_MENU])

    def advance(self, message, state, deps):
        if state.get("command") == "GROUP_MESSAGES":
            return self._select_group(message, state, deps)

        choice = message.lower().strip()
        if len(choice) == 2 and choice[1] == "x":
            choice = choice[0]

        if choice == "x":
            return goto(GOTO_MAIN)
        if choice == "g":
            return self._group_menu(deps)
        if choice == "s":
            return self._station_messages(deps)
        if choice == "u":
            return self._urgent_messages(deps)
        return self._at_menu(["Invalid option. Please choose again."])

    # --- menus ------------------------------------------------------------

    def _at_menu(self, replies):
        """Say something, then sit back at the JS8Call menu."""
        return stay({"command": "JS8CALL_MENU", "step": 1}, replies=replies + [JS8_MENU])

    def _group_listing(self, groups):
        return "Group Messages Menu:\n" + "\n".join(
            f"[{i}] {group[0]}" for i, group in enumerate(groups))

    def _group_menu(self, deps):
        groups = deps.js8.group_names()
        if not groups:
            return self._at_menu(["No group messages available."])
        return stay({"command": "GROUP_MESSAGES", "step": 1, "groups": groups},
                    replies=[self._group_listing(groups)])

    def _station_messages(self, deps):
        messages = deps.js8.station_messages()
        if not messages:
            return self._at_menu(["No station messages available."])
        listing = "Station Messages:\n" + "\n".join(
            f"[{i + 1}] {m[0]} -> {m[1]}: {m[2]} ({m[3]})"
            for i, m in enumerate(messages))
        return self._at_menu([listing])

    def _urgent_messages(self, deps):
        messages = deps.js8.urgent_messages()
        if not messages:
            return self._at_menu(["No urgent messages available."])
        listing = "Urgent Messages:\n" + "\n".join(
            f"[{i + 1}] {m[0]} -> {m[1]}: {m[2]} ({m[3]})"
            for i, m in enumerate(messages))
        return self._at_menu([listing])

    # --- picking a group --------------------------------------------------

    def _select_group(self, message, state, deps):
        groups = state.get("groups", [])
        try:
            groupname = groups[int(message)][0]
        except (IndexError, ValueError):
            available = deps.js8.group_names()
            listing = (self._group_listing(available) if available
                       else "No group messages available.")
            return self._at_menu(["Invalid group selection. Please choose again.", listing])

        messages = deps.js8.messages_for_group(groupname)
        if not messages:
            return self._at_menu([f"No messages for group {groupname}."])
        listing = f"Messages for group {groupname}:\n" + "\n".join(
            f"[{i + 1}] {m[0]}: {m[1]} ({m[2]})" for i, m in enumerate(messages))
        return self._at_menu([listing])
