"""Tests for the node roster: pure reads over the node map."""

import os
import sys

# Run from anywhere: put the repo root on the path before importing the modules
# under test. Keeps `python tests/test_x.py` working alongside pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import roster
from roster import Node

NODES = {
    "!a": {"num": 1, "user": {"shortName": "AA", "longName": "Alpha"}},
    "!b": {"num": 2, "user": {"shortName": "BB", "longName": "Bravo"}},
    "!c": {"num": 3, "user": {"shortName": "AA", "longName": "Alpha Two"}},
}


def test_id_from_num():
    assert roster.id_from_num(NODES, 2) == "!b"


def test_id_from_num_unknown():
    assert roster.id_from_num(NODES, 99) is None


def test_short_name():
    assert roster.short_name(NODES, "!a") == "AA"
    assert roster.short_name(NODES, "!zz") is None


def test_short_name_of_an_unnamed_node_is_none_not_a_crash():
    """It used to raise KeyError, a third failure mode for one question."""
    assert roster.short_name({"!x": {"num": 9, "user": {}}}, "!x") is None


def test_long_name_falls_back_for_a_stranger():
    assert roster.long_name(NODES, "!b") == "Bravo"
    assert roster.long_name(NODES, "!zz") == "Node !zz"


def test_find_by_short_name_is_case_insensitive():
    found = roster.find_by_short_name(NODES, "bb")
    assert found == [Node(id="!b", short_name="BB", long_name="Bravo")]


def test_find_by_short_name_returns_every_match():
    """Short names are not unique; the mail flow asks the sender to choose."""
    found = roster.find_by_short_name(NODES, "AA")
    assert sorted(n.id for n in found) == ["!a", "!c"]


def test_find_by_short_name_unknown():
    assert roster.find_by_short_name(NODES, "zz") == []


def test_node_carries_an_id_not_a_number():
    """The old dict called this key 'num' while holding a node id."""
    node = roster.find_by_short_name(NODES, "bb")[0]
    assert node.id == "!b"
    assert node.long_name == "Bravo"


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
