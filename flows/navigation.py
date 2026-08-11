"""Navigation — the root of the conversation tree.

Owns the menus: which letters each one offers, how they are labelled, and what
selecting one does. A selection either hands the conversation to another Flow
(``enter``) or is a leaf that answers and stays put — Fortune, Wall of Shame,
Quick Commands.

Pure: menu items and fortunes arrive through Deps, the mail count through the
injected store, and the node roster is already there. Rendering a menu happens
in exactly one place, which is why every other Flow can simply say
``goto=GOTO_BBS`` and stay ignorant of what a menu looks like.
"""

import random

from flows.base import stay, enter, GOTO_BBS, GOTO_MAIN, GOTO_UTILITIES

MAIN_TITLE = "💾TC² BBS💾"
BBS_TITLE = "📰BBS Menu📰"
UTILITIES_TITLE = "🛠️Utilities Menu🛠️"

QUICK_HELP = ("✈️QUICK COMMANDS✈️\nSend command below for usage info:\nSM,, - Send "
              "Mail\nCM - Check Mail\nPB,, - Post Bulletin\nCB,, - Check Bulletins\n"
              "CHP,, - Post Channel\nCHL - List Channels\n"
              "(',,' must be typed exactly - no spaces)\n")

_WALL_OF_SHAME_HEADER = "Devices with battery levels below 20%:\n"


def build_menu(items, title):
    """Render a menu from the configured letters. The B label depends on menu."""
    menu = f"{title}\n"
    for item in items:
        item = item.strip()
        if item == 'Q':
            menu += "[Q]uick Commands\n"
        elif item == 'B':
            menu += "[B]ulletins\n" if title == BBS_TITLE else "[B]BS\n"
        elif item == 'U':
            menu += "[U]tilities\n"
        elif item == 'X':
            menu += "E[X]IT\n"
        elif item == 'M':
            menu += "[M]ail\n"
        elif item == 'C':
            menu += "[C]hannel Dir\n"
        elif item == 'J':
            menu += "[J]S8CALL\n"
        elif item == 'S':
            menu += "[S]tats\n"
        elif item == 'F':
            menu += "[F]ortune\n"
        elif item == 'W':
            menu += "[W]all of Shame\n"
    return menu


class NavigationFlow:
    TOPICS = ["MAIN_MENU", "MENU"]

    def show(self, name, deps):
        """Render a menu and put the Session in it.

        An unrecognized name falls back to the main menu; the handler this
        replaces raised NameError instead.
        """
        if name == GOTO_BBS:
            return stay({"command": "MENU", "menu": "bbs", "step": 1},
                        replies=[build_menu(deps.menus.bbs, BBS_TITLE)])
        if name == GOTO_UTILITIES:
            return stay({"command": "MENU", "menu": "utilities", "step": 1},
                        replies=[build_menu(deps.menus.utilities, UTILITIES_TITLE)])

        unread = len(deps.store.get_mail(deps.node_id))
        title = f"{MAIN_TITLE} (✉️:{unread})"
        return stay({"command": "MAIN_MENU", "step": 1},
                    replies=[build_menu(deps.menus.main, title)])

    def entry(self, deps):
        return self.show(GOTO_MAIN, deps)

    def advance(self, message, state, deps):
        choice = message.strip().lower()
        if len(choice) == 2 and choice[1] == "x":
            choice = choice[0]

        if state.get("command") == "MENU":
            where = state.get("menu")
        else:
            where = GOTO_MAIN

        if where == "bbs":
            return self._bbs(choice, deps)
        if where == "utilities":
            return self._utilities(choice, state, deps)
        return self._main(choice, state, deps)

    # --- menus ------------------------------------------------------------

    def _main(self, choice, state, deps):
        if choice == "q":
            return stay(state, replies=[QUICK_HELP])
        if choice == "b":
            return self.show(GOTO_BBS, deps)
        if choice == "u":
            return self.show(GOTO_UTILITIES, deps)
        return self.show(GOTO_MAIN, deps)

    def _bbs(self, choice, deps):
        if choice == "m":
            return enter("MAIL")
        if choice == "b":
            return enter("BULLETIN_MENU")
        if choice == "c":
            return enter("CHANNEL_DIRECTORY")
        if choice == "j":
            return enter("JS8CALL_MENU")
        return self.show(GOTO_MAIN, deps)

    def _utilities(self, choice, state, deps):
        if choice == "s":
            return enter("STATS")
        if choice == "f":
            return stay(state, replies=[self._fortune(deps.fortunes)])
        if choice == "w":
            return stay(state, replies=[self._wall_of_shame(deps.roster)])
        return self.show(GOTO_MAIN, deps)

    # --- leaves -----------------------------------------------------------

    def _fortune(self, fortunes):
        if not fortunes:
            return "No fortunes available."
        return f"🔮 {random.choice(fortunes).strip()} 🔮"

    def _wall_of_shame(self, roster):
        lines = ""
        for node in roster.values():
            battery = node.get("deviceMetrics", {}).get("batteryLevel", 101)
            if battery < 20:
                lines += f"{node['user']['longName']} - Battery {battery}%\n"
        if not lines:
            return "No devices with battery levels below 20% found."
        return _WALL_OF_SHAME_HEADER + lines
