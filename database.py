"""The BBS store: bulletins, mail, and the channel directory.

One object owns the path, the connection and the schema, and is handed to
whoever needs it — the same shape as `Js8Database`. Nothing reaches for a
module global, so tests construct a `Database(":memory:")` and pass it in
rather than rebinding a name (see docs/adr/0004).

Pure persistence: writers return a record describing what happened. Deciding
whether that record is synced to peer BBS Nodes or broadcast to the mesh
belongs to Replication, not here (see docs/adr/0002).
"""

import logging
import sqlite3
import threading
import uuid
from datetime import datetime

from events import BulletinDeleted, BulletinPosted, ChannelAdded, MailDeleted, MailSent

#: Where the store lives unless a caller says otherwise.
DEFAULT_PATH = 'bulletins.db'


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M')


class Database:
    """SQLite behind a small interface.

    The connection is shared across threads — the server writes from the mesh
    reader thread and initialises from the main one. CPython reports
    `sqlite3.threadsafety == 3`, which permits that, but the lock makes it true
    regardless of how the local SQLite was built. The previous implementation
    kept a thread-local connection, which is why an in-memory database could
    not be shared with a test.
    """

    def __init__(self, path=DEFAULT_PATH):
        self._path = path
        self._connection = None
        self._lock = threading.Lock()

    def _connect(self):
        if self._connection is None:
            self._connection = sqlite3.connect(self._path, check_same_thread=False)
        return self._connection

    def initialize_schema(self):
        with self._lock:
            connection = self._connect()
            connection.execute('''CREATE TABLE IF NOT EXISTS bulletins (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            board TEXT NOT NULL,
                            sender_short_name TEXT NOT NULL,
                            date TEXT NOT NULL,
                            subject TEXT NOT NULL,
                            content TEXT NOT NULL,
                            unique_id TEXT NOT NULL
                        )''')
            connection.execute('''CREATE TABLE IF NOT EXISTS mail (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            sender TEXT NOT NULL,
                            sender_short_name TEXT NOT NULL,
                            recipient TEXT NOT NULL,
                            date TEXT NOT NULL,
                            subject TEXT NOT NULL,
                            content TEXT NOT NULL,
                            unique_id TEXT NOT NULL
                        )''')
            connection.execute('''CREATE TABLE IF NOT EXISTS channels (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL,
                            url TEXT NOT NULL
                        )''')
            connection.commit()

    # --- plumbing ---------------------------------------------------------

    def _query(self, sql, params=()):
        with self._lock:
            return self._connect().execute(sql, params).fetchall()

    def _one(self, sql, params=()):
        with self._lock:
            return self._connect().execute(sql, params).fetchone()

    def _write(self, sql, params=()):
        with self._lock:
            connection = self._connect()
            connection.execute(sql, params)
            connection.commit()

    # --- channels ---------------------------------------------------------

    def insert_channel(self, name, url):
        self._write("INSERT INTO channels (name, url) VALUES (?, ?)", (name, url))
        return ChannelAdded(name=name, url=url)

    def get_channels(self):
        return self._query("SELECT name, url FROM channels")

    def all_channels(self):
        """Every channel with its row id, for the admin tool."""
        return self._query("SELECT id, name, url FROM channels")

    def delete_channel(self, channel_id):
        """Delete by row id. Channels carry no unique_id and are never replicated."""
        if self._one("SELECT id FROM channels WHERE id = ?", (channel_id,)) is None:
            return False
        self._write("DELETE FROM channels WHERE id = ?", (channel_id,))
        return True

    # --- bulletins --------------------------------------------------------

    def insert_bulletin(self, board, sender_short_name, subject, content, unique_id=None):
        if not unique_id:
            unique_id = str(uuid.uuid4())
        self._write(
            "INSERT INTO bulletins (board, sender_short_name, date, subject, content, unique_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (board, sender_short_name, _now(), subject, content, unique_id))
        return BulletinPosted(board=board, sender_short_name=sender_short_name,
                              subject=subject, content=content, unique_id=unique_id)

    def get_bulletins(self, board):
        return self._query("SELECT id, subject, sender_short_name, date, unique_id "
                           "FROM bulletins WHERE board = ? COLLATE NOCASE", (board,))

    def all_bulletins(self):
        """Every bulletin across every board, for the admin tool.

        The unique_id comes last, which is the identity deletions use.
        """
        return self._query("SELECT id, board, sender_short_name, date, subject, unique_id "
                           "FROM bulletins")

    def get_bulletin_content(self, bulletin_id):
        return self._one("SELECT sender_short_name, date, subject, content, unique_id "
                         "FROM bulletins WHERE id = ?", (bulletin_id,))

    def delete_bulletin(self, unique_id):
        """Delete by unique_id — the identity peers share. Returns None if absent."""
        if self._one("SELECT unique_id FROM bulletins WHERE unique_id = ?", (unique_id,)) is None:
            logging.error(f"No bulletin found with unique_id: {unique_id}")
            return None
        self._write("DELETE FROM bulletins WHERE unique_id = ?", (unique_id,))
        return BulletinDeleted(unique_id=unique_id)

    # --- mail -------------------------------------------------------------

    def insert_mail(self, sender_id, sender_short_name, recipient_id, subject, content,
                    unique_id=None):
        if not unique_id:
            unique_id = str(uuid.uuid4())
        self._write(
            "INSERT INTO mail (sender, sender_short_name, recipient, date, subject, content, unique_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sender_id, sender_short_name, recipient_id, _now(), subject, content, unique_id))
        return MailSent(sender_id=sender_id, sender_short_name=sender_short_name,
                        recipient_id=recipient_id, subject=subject,
                        content=content, unique_id=unique_id)

    def get_mail(self, recipient_id):
        return self._query("SELECT id, sender_short_name, subject, date, unique_id "
                           "FROM mail WHERE recipient = ?", (recipient_id,))

    def all_mail(self):
        """Every mail in every mailbox, for the admin tool.

        The unique_id comes last, which is the identity deletions use.
        """
        return self._query("SELECT id, sender, sender_short_name, recipient, date, subject, unique_id "
                           "FROM mail")

    def get_mail_content(self, mail_id, recipient_id):
        return self._one("SELECT sender_short_name, date, subject, content, unique_id "
                         "FROM mail WHERE id = ? and recipient = ?", (mail_id, recipient_id))

    def delete_mail(self, unique_id):
        """Delete by unique_id. Returns None if no such mail exists."""
        row = self._one("SELECT recipient FROM mail WHERE unique_id = ?", (unique_id,))
        if row is None:
            logging.error(f"No mail found with unique_id: {unique_id}")
            return None
        logging.info(f"Attempting to delete mail with unique_id: {unique_id} by {row[0]}")
        self._write("DELETE FROM mail WHERE unique_id = ?", (unique_id,))
        return MailDeleted(unique_id=unique_id)

    def sender_id_by_mail_id(self, mail_id):
        row = self._one("SELECT sender FROM mail WHERE id = ?", (mail_id,))
        return row[0] if row else None
