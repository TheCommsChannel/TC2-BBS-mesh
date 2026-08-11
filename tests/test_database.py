"""Tests for the BBS Database — the persistence seam.

Constructed with ":memory:" and passed in, the way Js8Database already is. No
module global is reassigned (see docs/adr/0004).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from events import BulletinPosted, MailSent, ChannelAdded, BulletinDeleted, MailDeleted


def fresh():
    db = Database(":memory:")
    db.initialize_schema()
    return db


def test_insert_bulletin_returns_a_record():
    db = fresh()
    event = db.insert_bulletin("General", "AA", "Subj", "Body")
    assert isinstance(event, BulletinPosted)
    assert event.board == "General"
    assert event.unique_id


def test_bulletin_round_trips():
    db = fresh()
    db.insert_bulletin("General", "AA", "Subj", "Body", unique_id="u1")
    rows = db.get_bulletins("general")   # COLLATE NOCASE
    assert rows[0][1] == "Subj"


def test_bulletin_delete_by_unique_id():
    db = fresh()
    db.insert_bulletin("General", "AA", "S", "B", unique_id="u1")
    assert isinstance(db.delete_bulletin("u1"), BulletinDeleted)
    assert db.get_bulletins("General") == []


def test_bulletin_delete_absent_returns_none():
    assert fresh().delete_bulletin("nope") is None


def test_mail_round_trips_and_is_addressed():
    db = fresh()
    db.insert_mail("!s", "S", "!me", "Subj", "Body", unique_id="m1")
    assert len(db.get_mail("!me")) == 1
    assert db.get_mail("!someone_else") == []


def test_mail_content_requires_the_recipient():
    db = fresh()
    db.insert_mail("!s", "S", "!me", "Subj", "Body", unique_id="m1")
    mail_id = db.all_mail()[0][0]
    assert db.get_mail_content(mail_id, "!me") is not None
    assert db.get_mail_content(mail_id, "!intruder") is None


def test_mail_delete_and_sender_lookup():
    db = fresh()
    db.insert_mail("!orig", "S", "!me", "Subj", "Body", unique_id="m1")
    mail_id = db.all_mail()[0][0]
    assert db.sender_id_by_mail_id(mail_id) == "!orig"
    assert isinstance(db.delete_mail("m1"), MailDeleted)
    assert db.get_mail("!me") == []


def test_channel_round_trips():
    db = fresh()
    assert isinstance(db.insert_channel("Net", "url"), ChannelAdded)
    assert db.get_channels() == [("Net", "url")]


def test_channel_delete_by_row_id():
    db = fresh()
    db.insert_channel("Net", "url")
    row_id = db.all_channels()[0][0]
    assert db.delete_channel(row_id) is True
    assert db.delete_channel(row_id) is False


def test_two_databases_are_independent():
    a, b = fresh(), fresh()
    a.insert_channel("Only A", "url")
    assert len(a.get_channels()) == 1
    assert b.get_channels() == []


def test_connection_is_shared_across_threads():
    """The old thread-local connection could not be shared with a test thread."""
    import threading
    db = fresh()
    db.insert_channel("Net", "url")
    result = []
    t = threading.Thread(target=lambda: result.append(db.get_channels()))
    t.start(); t.join()
    assert result == [[("Net", "url")]]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"ok  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
