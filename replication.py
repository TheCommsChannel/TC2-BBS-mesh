"""Replication — the one owner of what leaves this server.

Given a record and where it came from, decides two things:

* **Sync** — relay it to peer BBS Nodes, but only if it originated here.
  A record that arrived from a peer is never echoed back.
* **Broadcast** — notify the whole mesh, driven by the Board's posting policy
  rather than by a string comparison against "urgent".

It also owns the sync wire format in both directions: encoding records to the
``BULLETIN|…`` messages peers exchange, decoding them back, and recognizing
one on arrival. Previously the format was split across utils (encoding),
message_processing (decoding), and on_receive (detection) — a field could not
be added without editing all three.
"""

import logging

from meshtastic import BROADCAST_NUM

import board as boards
from events import (
    BulletinDeleted, BulletinPosted, ChannelAdded, MailDeleted, MailSent, Origin,
)
#: Prefixes that mark an inbound message as sync rather than conversation.
_SYNC_PREFIXES = ("BULLETIN|", "MAIL|", "DELETE_BULLETIN|", "DELETE_MAIL|", "CHANNEL|")


def is_sync_message(text):
    return any(text.startswith(prefix) for prefix in _SYNC_PREFIXES)


def encode(event):
    """Render a record as the mesh message peers exchange."""
    if isinstance(event, BulletinPosted):
        return (f"BULLETIN|{event.board}|{event.sender_short_name}|"
                f"{event.subject}|{event.content}|{event.unique_id}")
    if isinstance(event, MailSent):
        return (f"MAIL|{event.sender_id}|{event.sender_short_name}|"
                f"{event.recipient_id}|{event.subject}|{event.content}|{event.unique_id}")
    if isinstance(event, BulletinDeleted):
        return f"DELETE_BULLETIN|{event.unique_id}"
    if isinstance(event, MailDeleted):
        return f"DELETE_MAIL|{event.unique_id}"
    if isinstance(event, ChannelAdded):
        return f"CHANNEL|{event.name}|{event.url}"
    raise TypeError(f"cannot encode {type(event).__name__}")


def decode(text):
    """Parse an inbound sync message, or return None if it isn't one."""
    parts = text.split("|")
    kind = parts[0]
    try:
        if kind == "BULLETIN":
            return BulletinPosted(board=parts[1], sender_short_name=parts[2],
                                  subject=parts[3], content=parts[4], unique_id=parts[5])
        if kind == "MAIL":
            return MailSent(sender_id=parts[1], sender_short_name=parts[2],
                            recipient_id=parts[3], subject=parts[4],
                            content=parts[5], unique_id=parts[6])
        if kind == "DELETE_BULLETIN":
            return BulletinDeleted(unique_id=parts[1])
        if kind == "DELETE_MAIL":
            return MailDeleted(unique_id=parts[1])
        if kind == "CHANNEL":
            return ChannelAdded(name=parts[1], url=parts[2])
    except IndexError:
        logging.error(f"Malformed sync message: {text!r}")
        return None
    return None


def _broadcast_text(event):
    """The mesh-wide notify for a Bulletin whose Board broadcasts on post."""
    if not isinstance(event, BulletinPosted):
        return None
    board = boards.Board.from_name(event.board)
    if board is None or not board.broadcasts_on_post:
        return None
    return (f"💥NEW URGENT BULLETIN💥\nFrom: {event.sender_short_name}\n"
            f"Title: {event.subject}\nDM 'CB,,Urgent' to view")


class Replication:
    def __init__(self, transport, peers=()):
        self._transport = transport
        self._peers = list(peers)

    def publish(self, event, origin):
        """Sync the record to peers (if local) and broadcast it (if its Board says so)."""
        if origin is Origin.LOCAL:
            self._sync_to_peers(event)

        text = _broadcast_text(event)
        if text is not None:
            self._transport.send(text, BROADCAST_NUM)

    def _sync_to_peers(self, event):
        peers = self._peers
        if not peers:
            return
        message = encode(event)
        if isinstance(event, MailSent):
            logging.info(f"SERVER SYNC: Syncing new mail message {event.subject} "
                         f"sent from {event.sender_short_name} to other BBS systems.")
        elif isinstance(event, MailDeleted):
            logging.info(f"SERVER SYNC: Sending delete mail sync message with "
                         f"unique_id: {event.unique_id}")
        for node_id in peers:
            self._transport.send(message, node_id)
