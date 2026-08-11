"""Tests for Js8Database — the JS8Call store.

Covers the two crashes the old JS8CallClient shipped: an undefined name in the
insert, and reads that raised when the tables did not exist.
"""

import os
import sys

# Run from anywhere: put the repo root on the path before importing the modules
# under test. Keeps `python tests/test_x.py` working alongside pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from js8_db import Js8Database


def fresh():
    db = Js8Database(":memory:")
    db.create_tables()
    return db


# --- inserts ---------------------------------------------------------------

def test_station_message_round_trips():
    db = fresh()
    db.insert("messages", "CALL1", "CALL2", "hello")
    rows = db.station_messages()
    assert len(rows) == 1
    assert rows[0][0] == "CALL1"
    assert rows[0][1] == "CALL2"      # 'receiver' column
    assert rows[0][2] == "hello"


def test_group_message_round_trips():
    db = fresh()
    db.insert("groups", "CALL1", "@NET", "hi group")
    assert db.group_names() == [("@NET",)]
    rows = db.messages_for_group("@NET")
    assert rows[0][0] == "CALL1"
    assert rows[0][1] == "hi group"


def test_urgent_message_round_trips():
    db = fresh()
    db.insert("urgent", "CALL1", "@URGNT", "mayday")
    rows = db.urgent_messages()
    assert rows[0][0] == "CALL1"
    assert rows[0][1] == "@URGNT"     # 'groupname' column
    assert rows[0][2] == "mayday"


def test_unknown_table_is_rejected():
    db = fresh()
    try:
        db.insert("bulletins; DROP TABLE groups", "a", "b", "c")
    except ValueError:
        return
    raise AssertionError("expected ValueError for an unknown table")


# --- graceful reads --------------------------------------------------------

def test_reads_are_empty_when_unconfigured():
    db = Js8Database(None)
    assert not db.configured
    assert db.group_names() == []
    assert db.station_messages() == []
    assert db.urgent_messages() == []
    assert db.messages_for_group("@NET") == []


def test_reads_are_empty_when_tables_missing():
    # A database file that exists but was never initialized.
    db = Js8Database(":memory:")
    assert db.group_names() == []
    assert db.station_messages() == []
    assert db.urgent_messages() == []


def test_insert_when_unconfigured_is_a_noop():
    db = Js8Database(None)
    db.insert("messages", "CALL1", "CALL2", "hello")   # must not raise


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
