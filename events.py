"""What happened, as data.

The records the stores produce and Replication consumes. Keeping them in
their own module lets persistence and replication both depend on the events
without depending on each other.
"""

from dataclasses import dataclass
from enum import Enum


class Origin(Enum):
    """Where a record came from.

    LOCAL — a Node on this server created it; it must be synced to peers.
    SYNCED — it arrived from a peer BBS Node; it must not be echoed back.
    """

    LOCAL = "local"
    SYNCED = "synced"


@dataclass(frozen=True)
class BulletinPosted:
    board: str
    sender_short_name: str
    subject: str
    content: str
    unique_id: str


@dataclass(frozen=True)
class MailSent:
    sender_id: str
    sender_short_name: str
    recipient_id: str
    subject: str
    content: str
    unique_id: str


@dataclass(frozen=True)
class BulletinDeleted:
    unique_id: str


@dataclass(frozen=True)
class MailDeleted:
    unique_id: str


@dataclass(frozen=True)
class ChannelAdded:
    name: str
    url: str
