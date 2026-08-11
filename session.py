"""Session — where every Node stands in its conversation, and how it advances.

The Session owns the per-node state (the topic, step, and half-entered content
that CONTEXT.md calls a Session) and the map from a topic to the flow that runs
it. Its interface is two methods:

    session.advance(node, message, deps) -> [(destination, text), ...]
    session.check_timeouts(deps_factory) -> [(destination, text), ...]

The router feeds a message in and sends the outbound messages out; it never
learns what a step is. check_timeouts is the same idea without an inbound
message — driven by the idle loop instead, it finishes any compose a node has
gone quiet on. Because the state lives on the object rather than in a module
global, two Sessions are independent and a test constructs one instead of
clearing a global (see docs/adr/0004).
"""

import re
import time

from flows.base import GOTO_MAIN, Stay, End, Keep, Goto, Enter
from flows.bulletin import BulletinFlow
from flows.channel import ChannelFlow
from flows.js8 import Js8Flow
from flows.mail import MailFlow
from flows.navigation import NavigationFlow
from flows.stats import StatsFlow

#: How long a bulletin post or mail send may sit idle, mid-compose, before
#: check_timeouts finishes it for the node — posted if there's content,
#: discarded if the draft is still empty.
COMPOSE_TIMEOUT_SECONDS = 5 * 60


def _topics(flow):
    """A flow claims one topic (TOPIC) or several (TOPICS)."""
    topics = getattr(flow, "TOPICS", None)
    return list(topics) if topics is not None else [flow.TOPIC]


def _is_composing(state):
    """The two END-driven states check_timeouts watches: a bulletin body or a
    mail body being typed in one line at a time. Every other state is out of
    scope — there's nothing to auto-finish for a menu wait."""
    if state is None:
        return False
    command = state.get("command")
    if command == "BULLETIN_POST_CONTENT":
        return True
    return command == "MAIL" and state.get("step") == 7


def _default_flows():
    return [NavigationFlow(), StatsFlow(), BulletinFlow(), MailFlow(), ChannelFlow(), Js8Flow()]


class Session:
    def __init__(self, flows=None):
        flows = flows if flows is not None else _default_flows()
        self._states = {}                 # node -> its current conversation state
        self._last_activity = {}          # node -> time.time() of its last message

        self._flows = {}
        for flow in flows:
            for topic in _topics(flow):
                self._flows[topic] = flow
        self._navigation = next((f for f in flows if isinstance(f, NavigationFlow)), None)

        self._quick = {}
        for flow in flows:
            for prefix, method in getattr(flow, "QUICK_COMMANDS", {}).items():
                self._quick[prefix] = (flow, method)
        # Longest prefix wins, so "chp,," is never shadowed by a shorter one.
        self._quick_prefixes = sorted(self._quick, key=len, reverse=True)
        # The bare command word, args stripped, for prefixes that take args
        # ("pb,," -> "pb") — precomputed once, alongside _quick_prefixes above.
        self._quick_bare = {p: p[:-2] for p in self._quick_prefixes if p.endswith(",,")}
        # A typo'd separator still reads as an attempt at the command: the bare
        # word immediately followed by a comma (e.g. "PB, , General,,..." has a
        # stray space breaking the "pb,," prefix, but is still clearly a PB).
        self._quick_typo = {p: re.compile(rf"^{re.escape(bare)}\s*,")
                            for p, bare in self._quick_bare.items()}

    def advance(self, node, message, deps, now=None):
        """Advance `node`'s conversation by one message.

        Returns the outbound messages the router should send, as
        (destination, text) pairs — the node's replies plus any notification to
        another node. Updates this node's stored state as a side effect, and
        marks `node` active at `now` (real time by default; tests inject it),
        which is what check_timeouts measures inactivity against.
        """
        self._last_activity[node] = now if now is not None else time.time()
        result = self._route(node, message, deps)
        return self._enact(node, result, deps)

    # --- timeouts -----------------------------------------------------------

    def check_timeouts(self, deps_factory, now=None):
        """Finish any compose the node has gone quiet on.

        For each node sitting in a bulletin-post or mail-compose step with no
        activity for COMPOSE_TIMEOUT_SECONDS: an empty draft is discarded
        silently (no reply, no write), a non-empty one is finished exactly as
        if the node had sent "END" — same flow method, same reply, same
        notifications, same next state.

        `deps_factory(node) -> Deps` builds the collaborators for one node —
        there is no inbound packet here to build them from, unlike advance().
        Returns the outbound (destination, text) pairs to send, same shape as
        advance().
        """
        now = now if now is not None else time.time()
        outbound = []
        for node in list(self._states):
            state = self._states[node]
            if not _is_composing(state):
                continue
            last = self._last_activity.get(node, now)
            if now - last < COMPOSE_TIMEOUT_SECONDS:
                continue
            if not state.get("content"):
                self._states[node] = None
                self._last_activity.pop(node, None)
                continue
            deps = deps_factory(node)
            result = self._flows[state["command"]].advance("END", state, deps)
            outbound += self._enact(node, result, deps)
            self._last_activity.pop(node, None)
        return outbound

    # --- routing ----------------------------------------------------------

    def _route(self, node, message, deps):
        # Routing decisions read a stripped, lowercased copy, but the flow
        # itself receives the raw message: a content-capture step (a mail body,
        # a bulletin body) stores it verbatim, so leading whitespace and blank
        # lines must survive. Menu steps strip what they compare themselves.
        stripped = message.strip()
        lowered = stripped.lower()
        # Tolerate a repeated final character on single-letter commands (e.g. "rx").
        if len(lowered) == 2 and lowered[1] == 'x':
            lowered = lowered[0]

        # Quick commands act from anywhere, without moving the conversation.
        result = self._quick_command(stripped, deps)
        if result is not None:
            return result

        # EXIT from anywhere returns to the main menu, before any flow sees it.
        if lowered == 'x':
            return self._navigation.show(GOTO_MAIN, deps)

        # No stored state means the node is sitting at the main menu.
        state = self._states.get(node)
        topic = state['command'] if state else 'MAIN_MENU'
        if topic not in self._flows:
            return self._navigation.show(GOTO_MAIN, deps)
        return self._flows[topic].advance(
            message, state or {'command': 'MAIN_MENU', 'step': 1}, deps)

    def _quick_command(self, message, deps):
        # A prefix ending in ",," takes arguments after it (e.g. "pb,,General,,...").
        # The bare command word alone (e.g. "PB") still routes here so the flow's
        # own usage message is shown, rather than falling through to menu routing
        # as if the letters meant nothing. So does a typo'd separator (e.g. a
        # stray space in "PB, , General,,..."): anything starting with the bare
        # word immediately followed by a comma reads as an attempted quick
        # command, even if the rest doesn't parse.
        lowered = message.lower()
        for prefix in self._quick_prefixes:
            bare = self._quick_bare.get(prefix, prefix)
            if lowered.startswith(prefix) or lowered == bare:
                return self._dispatch(prefix, message, deps)
        for prefix, typo in self._quick_typo.items():
            if typo.match(lowered):
                return self._dispatch(prefix, message, deps)
        return None

    def _dispatch(self, prefix, message, deps):
        flow, method = self._quick[prefix]
        return getattr(flow, method)(message, deps)

    # --- enacting a FlowResult -------------------------------------------

    def _enact(self, node, result, deps):
        outbound = [(node, reply) for reply in result.replies]
        outbound += list(result.notifications)
        return outbound + self._apply(node, result.outcome, deps)

    def _apply(self, node, outcome, deps):
        """Enact one outcome: update this node's state, and for a hand-off,
        return the menu-or-opening's replies. Nothing else may be set — the
        outcome is a single value, so the old flag combinations can't occur."""
        if isinstance(outcome, Keep):
            return []
        if isinstance(outcome, End):
            self._states[node] = None
            return []
        if isinstance(outcome, Stay):
            self._states[node] = outcome.state
            return []
        if isinstance(outcome, Goto):
            handed_off = self._navigation.show(outcome.menu, deps)
        elif isinstance(outcome, Enter):
            handed_off = self._flows[outcome.topic].entry(deps)
        else:
            raise TypeError(f"unknown flow outcome: {outcome!r}")
        # A menu or a flow's opening settles the conversation — its outcome is a
        # terminal Stay. Applying it stores that state; it is not another
        # hand-off, so this does not chain menu-to-menu.
        replies = [(node, reply) for reply in handed_off.replies]
        return replies + self._apply(node, handed_off.outcome, deps)
