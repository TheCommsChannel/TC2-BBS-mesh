"""Stats conversation: node counts, hardware models, roles.

Read-only over the node roster — no store, no lookup, no radio. The first
flow migrated out of the handle_*_steps tangle, so it doubles as the proof
that the pure Flow shape works.
"""

import time

from flows.base import stay, goto, GOTO_MAIN

_MENU = ("📊Stats Menu📊\nWhat stats would you like to view?\n"
         "[N]odes  [H]ardware  [R]oles  E[X]IT")

_TIMEFRAMES = {
    "All time": None,
    "Last 24 hours": 86400,
    "Last 8 hours": 28800,
    "Last hour": 3600,
}


class StatsFlow:
    TOPIC = "STATS"

    def entry(self, deps):
        """Greeting and starting state when Navigation hands the topic over."""
        return stay({"command": self.TOPIC, "step": 1}, replies=[_MENU])

    def advance(self, message, state, deps):
        message = message.lower().strip()
        if len(message) == 2 and message[1] == "x":
            message = message[0]

        step = state.get("step", 1)
        if step != 1:
            return stay(state)

        if message == "x":
            return goto(GOTO_MAIN)

        if message == "n":
            stat = self._node_summary(deps.roster)
        elif message == "h":
            stat = self._hardware_summary(deps.roster)
        elif message == "r":
            stat = self._role_summary(deps.roster)
        else:
            # Legacy showed nothing for unrecognized input and stayed put.
            return stay({"command": self.TOPIC, "step": 1})

        return stay({"command": self.TOPIC, "step": 1}, replies=[stat, _MENU])

    def _node_summary(self, roster):
        now = int(time.time())
        lines = []
        for period, seconds in _TIMEFRAMES.items():
            if seconds is None:
                total = len(roster)
            else:
                limit = now - seconds
                total = sum(1 for n in roster.values()
                            if n.get("lastHeard") is not None
                            and n["lastHeard"] >= limit)
            lines.append(f"- {period}: {total}")
        return "Total nodes seen:\n" + "\n".join(lines)

    def _hardware_summary(self, roster):
        counts = {}
        for n in roster.values():
            model = n["user"].get("hwModel", "Unknown")
            counts[model] = counts.get(model, 0) + 1
        return "Hardware Models:\n" + "\n".join(
            f"{model}: {count}" for model, count in counts.items())

    def _role_summary(self, roster):
        counts = {}
        for n in roster.values():
            role = n["user"].get("role", "Unknown")
            counts[role] = counts.get(role, 0) + 1
        return "Roles:\n" + "\n".join(
            f"{role}: {count}" for role, count in counts.items())
