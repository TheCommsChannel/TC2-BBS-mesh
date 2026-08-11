"""Tests for the admin console's selection logic and the store it reads.

The console itself (prompts, ANSI bold, the menu loop) is left alone; what is
tested is everything it decides before touching the database.
"""

import os
import sys

# Run from anywhere: put the repo root on the path before importing the modules
# under test. Keeps `python tests/test_x.py` working alongside pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import contextlib
import io

import db_admin
from database import Database


def fresh_db():
    database = Database(":memory:")
    database.initialize_schema()
    return database


def seed():
    db = fresh_db()
    db.insert_bulletin("General", "AA", "B1", "body", unique_id="bu1")
    db.insert_bulletin("News", "BB", "B2", "body", unique_id="bu2")
    db.insert_mail("!s1", "S1", "!me", "M1", "body", unique_id="mu1")
    db.insert_mail("!s2", "S2", "!me", "M2", "body", unique_id="mu2")
    db.insert_channel("Net", "url1")
    db.insert_channel("Backup", "url2")
    return db


def quietly(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args)


# --- parse_selection (pure) ------------------------------------------------

def test_parse_selection_splits_and_trims():
    assert db_admin.parse_selection(" 1, 2 ,3 ") == ["1", "2", "3"]


def test_parse_selection_ignores_empties():
    assert db_admin.parse_selection("1,,2,") == ["1", "2"]


def test_parse_selection_cancels_on_x():
    assert db_admin.parse_selection("X") is None
    assert db_admin.parse_selection("1,x,3") is None


# --- unique_ids_for (pure) -------------------------------------------------

ROWS = [(1, "General", "AA", "d", "B1", "bu1"),
        (2, "News", "BB", "d", "B2", "bu2")]


def test_unique_ids_for_maps_displayed_ids():
    found, unknown = db_admin.unique_ids_for(ROWS, ["1", "2"])
    assert found == ["bu1", "bu2"]
    assert unknown == []


def test_unique_ids_for_reports_unknown():
    found, unknown = db_admin.unique_ids_for(ROWS, ["2", "99"])
    assert found == ["bu2"]
    assert unknown == ["99"]


def test_row_ids_for_channels():
    rows = [(1, "Net", "url1"), (2, "Backup", "url2")]
    found, unknown = db_admin.row_ids_for(rows, ["2", "7"])
    assert found == ["2"]
    assert unknown == ["7"]


# --- listings return lists -------------------------------------------------

def test_list_mail_returns_every_row():
    """It used to rebind the loop variable and return only the last row."""
    db = seed()
    mail = quietly(db_admin.list_mail, db)
    assert isinstance(mail, list)
    assert len(mail) == 2


def test_list_bulletins_returns_every_row():
    db = seed()
    assert len(quietly(db_admin.list_bulletins, db)) == 2


def test_list_channels_returns_every_row():
    db = seed()
    assert len(quietly(db_admin.list_channels, db)) == 2


def test_listings_are_empty_on_a_fresh_database():
    db = fresh_db()
    assert quietly(db_admin.list_mail, db) == []
    assert quietly(db_admin.list_bulletins, db) == []
    assert quietly(db_admin.list_channels, db) == []


# --- the store the admin tool deletes through -----------------------------

def test_delete_bulletin_by_unique_id():
    db = seed()
    assert db.delete_bulletin("bu1") is not None
    assert [row[0] for row in db.all_bulletins()] == [2]


def test_delete_mail_by_unique_id():
    db = seed()
    assert db.delete_mail("mu2") is not None
    assert [row[6] for row in db.all_mail()] == ["mu1"]


def test_delete_channel_by_row_id():
    db = seed()
    assert db.delete_channel(1) is True
    assert [row[1] for row in db.all_channels()] == ["Backup"]


def test_delete_channel_reports_a_miss():
    db = seed()
    assert db.delete_channel(99) is False
    assert len(db.all_channels()) == 2


def test_two_databases_do_not_share_state():
    """Each Database owns its own connection; nothing is global."""
    first, second = fresh_db(), fresh_db()
    first.insert_channel("Only In First", "url")
    assert len(first.all_channels()) == 1
    assert second.all_channels() == []


def test_admin_does_not_declare_the_schema():
    """The schema lives in Database. db_admin used to keep its own copy."""
    assert not hasattr(db_admin, "initialize_database")
    assert not hasattr(db_admin, "get_db_connection")


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
