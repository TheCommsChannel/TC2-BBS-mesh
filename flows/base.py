"""Shared shapes for conversation flows.

A Flow is a deep module owning one conversation topic (mail, bulletins,
stats, ...). It is *pure*: ``advance(message, state, deps)`` computes what to
say and where the conversation goes next, and returns it — it never sends
messages, touches the radio, or reaches for a global. The router at the seam
does the sending; the collaborators a flow needs are handed in via ``Deps``.

A flow's answer is a :class:`FlowResult`: what to say (``replies`` and
``notifications``) and one :data:`Outcome` saying where the conversation goes
next. The outcome is a single value, not a set of flags, so a flow cannot ask
to enter a flow *and* show a menu at once — there is nowhere to write both.
Build one with the ``stay`` / ``end`` / ``keep`` / ``goto`` / ``enter`` helpers.
"""

from dataclasses import dataclass, field
from typing import Any, List, Union


@dataclass
class Deps:
    """Collaborators handed to a flow so it stays pure.

    Built fresh at the router edge for each message. A flow reads only the
    fields it needs; ``roster`` and the acting-node context let it make
    permission decisions without touching the radio.
    """

    roster: dict = field(default_factory=dict)   # node_id -> node dict (the live node map)
    store: Any = None                            # persistence + replication
    lookup: Any = None                           # node resolution over the roster
    node_id: Any = None                          # acting node's id, resolved from the roster
    allowed_nodes: List[str] = field(default_factory=list)   # urgent-board allow-list
    js8: Any = None                              # Js8Database — what the JS8Call bridge heard
    menus: Any = None                            # settings.Menus — which letters each menu offers
    fortunes: List[str] = field(default_factory=list)


#: A Node absent from the roster, or without a short name, cannot be named as
#: the author of anything. Authorship is stored on the record and travels to
#: peers on the wire, so the write is refused rather than attributed to nobody.
UNKNOWN_NODE_REPLY = "Error: Unable to retrieve your node information."


# Menu hand-off targets — the menus NavigationFlow knows how to render.
GOTO_MAIN = "main"
GOTO_BBS = "bbs"
GOTO_UTILITIES = "utilities"


# --- Outcome: where the conversation goes after this message ----------------
# Exactly one of these is a flow's answer. The router matches on the type, so
# the combinations the old flag fields allowed (goto *and* enter, goto *and*
# keep_state) simply cannot be written.

@dataclass(frozen=True)
class Stay:
    """Store ``state`` and wait for this node's next message."""
    state: dict


@dataclass(frozen=True)
class End:
    """End the conversation; the next message starts fresh at the main menu."""


@dataclass(frozen=True)
class Keep:
    """Leave the stored state untouched — a quick command that doesn't move you."""


@dataclass(frozen=True)
class Goto:
    """Show a menu (one of the ``GOTO_*`` names) and take the state it returns."""
    menu: str


@dataclass(frozen=True)
class Enter:
    """Hand the conversation to the flow that owns ``topic`` (its opening)."""
    topic: str


#: A flow's answer to "where next" is exactly one of these.
Outcome = Union[Stay, End, Keep, Goto, Enter]


@dataclass
class FlowResult:
    """What a flow hands back to the router.

    replies: text chunks to send to the current node, in order.
    notifications: out-of-band (destination, text) messages to other nodes —
        e.g. the "you have new mail" nudge to a recipient.
    outcome: exactly one :data:`Outcome` — where the conversation goes next.
    """

    replies: List[str] = field(default_factory=list)
    notifications: List[tuple] = field(default_factory=list)
    outcome: Outcome = field(default_factory=End)


def _lists(replies, notifications):
    return list(replies or []), list(notifications or [])


def stay(state, replies=None, notifications=None):
    """Wait at ``state`` for the next message."""
    replies, notifications = _lists(replies, notifications)
    return FlowResult(replies, notifications, Stay(state))


def end(replies=None, notifications=None):
    """End the conversation."""
    replies, notifications = _lists(replies, notifications)
    return FlowResult(replies, notifications, End())


def keep(replies=None, notifications=None):
    """Answer without moving the conversation (a quick command)."""
    replies, notifications = _lists(replies, notifications)
    return FlowResult(replies, notifications, Keep())


def goto(menu, replies=None, notifications=None):
    """Show a menu and take its state."""
    replies, notifications = _lists(replies, notifications)
    return FlowResult(replies, notifications, Goto(menu))


def enter(topic):
    """Hand the conversation to another flow's opening."""
    return FlowResult(outcome=Enter(topic))
