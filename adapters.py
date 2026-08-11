"""The collaborators a flow depends on, bound to real machinery.

``Store`` composes pure persistence with Replication: it writes the record and
hands it to Replication to decide sync and broadcast. Flows see only the small
interface — they never learn that peers or the mesh exist.

``Lookup`` answers questions about the node roster. Neither holds the radio.
"""

import roster
from events import (
    BulletinDeleted, BulletinPosted, ChannelAdded, MailDeleted, MailSent, Origin,
)


class Store:
    def __init__(self, replication, database):
        self._replication = replication
        self._db = database

    # bulletins ------------------------------------------------------------
    def get_bulletins(self, board):
        return self._db.get_bulletins(board)

    def get_bulletin_content(self, bulletin_id):
        return self._db.get_bulletin_content(bulletin_id)

    def add_bulletin(self, board, sender_short_name, subject, content):
        event = self._db.insert_bulletin(board, sender_short_name, subject, content)
        self._replication.publish(event, Origin.LOCAL)
        return event.unique_id

    # mail -----------------------------------------------------------------
    def get_mail(self, recipient_id):
        return self._db.get_mail(recipient_id)

    def get_mail_content(self, mail_id, recipient_id):
        return self._db.get_mail_content(mail_id, recipient_id)

    def add_mail(self, sender_id, sender_short_name, recipient_id, subject, content):
        event = self._db.insert_mail(sender_id, sender_short_name, recipient_id,
                                          subject, content)
        self._replication.publish(event, Origin.LOCAL)
        return event.unique_id

    def delete_mail(self, unique_id, recipient_id=None):
        event = self._db.delete_mail(unique_id)
        if event is not None:
            self._replication.publish(event, Origin.LOCAL)

    def sender_id_by_mail_id(self, mail_id):
        return self._db.sender_id_by_mail_id(mail_id)

    # channels -------------------------------------------------------------
    def get_channels(self):
        return self._db.get_channels()

    def add_channel(self, name, url):
        event = self._db.insert_channel(name, url)
        self._replication.publish(event, Origin.LOCAL)

    # replication inbound --------------------------------------------------
    def accept(self, event):
        """Persist a record that arrived from a peer BBS Node."""
        if isinstance(event, BulletinPosted):
            self._db.insert_bulletin(event.board, event.sender_short_name,
                                          event.subject, event.content,
                                          unique_id=event.unique_id)
        elif isinstance(event, MailSent):
            self._db.insert_mail(event.sender_id, event.sender_short_name,
                                      event.recipient_id, event.subject,
                                      event.content, unique_id=event.unique_id)
        elif isinstance(event, BulletinDeleted):
            self._db.delete_bulletin(event.unique_id)
        elif isinstance(event, MailDeleted):
            self._db.delete_mail(event.unique_id)
        elif isinstance(event, ChannelAdded):
            self._db.insert_channel(event.name, event.url)


class Lookup:
    """Node resolution for a flow, over the roster it is handed.

    Holds a dict, not a radio, so a flow's tests need no fake interface.
    """

    def __init__(self, nodes):
        self._nodes = nodes

    def node_info(self, short_name):
        """Every Node answering to a short name. Short names are not unique."""
        return roster.find_by_short_name(self._nodes, short_name)

    def node_name(self, node_id):
        return roster.long_name(self._nodes, node_id)

    def short_name(self, node_id):
        return roster.short_name(self._nodes, node_id)

    def id_from_num(self, num):
        return roster.id_from_num(self._nodes, num)
