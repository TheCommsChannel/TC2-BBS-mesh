"""Bulletin boards as a value type.

Deep module: the fixed set of boards, the index<->name mapping, and each
board's posting policy live behind one small interface. Replaces the
``{0: "General", 1: "Info", 2: "News", 3: "Urgent"}`` dict that was copied
across command_handlers and message_processing, and the scattered
``board.lower() == "urgent"`` string checks.

Board owns identity and policy *flags* only. It never touches the meshtastic
interface, the config, or the node allow-list. Enforcement of the urgent
post permission stays with the caller (BulletinFlow), which asks a board
``requires_post_permission`` and then checks the allow-list itself.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Board:
    """A single bulletin board and its posting policy.

    Attributes:
        name: Display name, e.g. "General". Stored on bulletin rows and used
            in the peer-sync protocol, so treated as the board's identity.
        index: Menu position 0..3, as sent by the stepped bulletin flow.
        is_urgent: True for the Urgent board. Callers use this instead of a
            ``name.lower() == "urgent"`` string test.
        requires_post_permission: Posting is gated by the node allow-list.
            Board only reports the requirement; the caller enforces it.
        broadcasts_on_post: A successful post is broadcast to the mesh.
    """

    name: str
    index: int
    is_urgent: bool = False
    requires_post_permission: bool = False
    broadcasts_on_post: bool = False

    @staticmethod
    def from_index(index) -> Optional["Board"]:
        """Return the board at ``index``, or None if out of range.

        Accepts anything int-coercible (menu input arrives as a string).
        A non-numeric value yields None rather than raising.
        """
        try:
            index = int(index)
        except (TypeError, ValueError):
            return None
        return _BY_INDEX.get(index)

    @staticmethod
    def from_name(name) -> Optional["Board"]:
        """Return the board named ``name`` (case-insensitive), or None.

        Case-insensitive to match the ``COLLATE NOCASE`` lookup used when
        reading bulletins out of the database.
        """
        if name is None:
            return None
        return _BY_NAME.get(str(name).strip().lower())


GENERAL = Board("General", 0)
INFO = Board("Info", 1)
NEWS = Board("News", 2)
URGENT = Board(
    "Urgent",
    3,
    is_urgent=True,
    requires_post_permission=True,
    broadcasts_on_post=True,
)

#: All boards in menu order. Callers iterate this instead of hardcoding the set.
BOARDS: Tuple[Board, ...] = (GENERAL, INFO, NEWS, URGENT)

_BY_INDEX = {b.index: b for b in BOARDS}
_BY_NAME = {b.name.lower(): b for b in BOARDS}
