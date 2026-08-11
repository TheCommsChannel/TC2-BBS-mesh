"""Persistence for the JS8Call message store.

A separate database from the BBS's own: it holds what was heard over HF radio,
not what Nodes posted over the mesh. One object owns the path and the
connection, so the writer (JS8CallClient) and the reader (Js8Flow) can no
longer disagree about which file they mean.

Reads degrade to an empty result when JS8Call is not configured or the tables
do not exist yet — an unconfigured bridge is an empty inbox, not an error.
"""

import logging
import sqlite3

#: Which column holds the counterparty, per table. Also the table allow-list:
#: the table name is interpolated into SQL, so it may only come from here.
_COUNTERPARTY = {
    "messages": "receiver",
    "groups": "groupname",
    "urgent": "groupname",
}


class Js8Database:
    def __init__(self, path):
        self._path = path
        self._connection = None

    @property
    def configured(self):
        return bool(self._path)

    def _connect(self):
        if self._connection is None:
            self._connection = sqlite3.connect(self._path, check_same_thread=False)
        return self._connection

    def create_tables(self):
        if not self.configured:
            return
        connection = self._connect()
        with connection:
            for table, counterparty in _COUNTERPARTY.items():
                connection.execute(f'''
                    CREATE TABLE IF NOT EXISTS {table} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sender TEXT,
                        {counterparty} TEXT,
                        message TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

    def insert(self, table, sender, counterparty, message):
        """Store one heard message. `counterparty` is a callsign or group name."""
        column = _COUNTERPARTY.get(table)
        if column is None:
            raise ValueError(f"unknown JS8Call table: {table!r}")
        if not self.configured:
            logging.error("JS8Call database is not configured.")
            return
        try:
            connection = self._connect()
            with connection:
                connection.execute(
                    f"INSERT INTO {table} (sender, {column}, message) VALUES (?, ?, ?)",
                    (sender, counterparty, message))
        except sqlite3.Error as error:
            logging.error(f"Failed to insert into JS8Call {table} table: {error}")

    def _query(self, sql, params=()):
        if not self.configured:
            return []
        try:
            return self._connect().execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            # No database file yet, or the tables have not been created.
            return []

    def group_names(self):
        return self._query("SELECT DISTINCT groupname FROM groups")

    def station_messages(self):
        return self._query("SELECT sender, receiver, message, timestamp FROM messages")

    def urgent_messages(self):
        return self._query("SELECT sender, groupname, message, timestamp FROM urgent")

    def messages_for_group(self, groupname):
        return self._query(
            "SELECT sender, message, timestamp FROM groups WHERE groupname = ?",
            (groupname,))
