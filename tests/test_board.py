"""Tests for the Board value type.

Pure — no meshtastic interface, no database. Runs under pytest, or standalone
(``python test_board.py``) so the suite needs no new dependency.
"""

import os
import sys

# Run from anywhere: put the repo root on the path before importing the modules
# under test. Keeps `python tests/test_x.py` working alongside pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import board
from board import Board


def test_from_index_maps_menu_positions():
    assert Board.from_index(0) is board.GENERAL
    assert Board.from_index(1) is board.INFO
    assert Board.from_index(2) is board.NEWS
    assert Board.from_index(3) is board.URGENT


def test_from_index_accepts_string_input():
    # Menu input arrives as a string.
    assert Board.from_index("3") is board.URGENT


def test_from_index_out_of_range_is_none():
    assert Board.from_index(4) is None
    assert Board.from_index(-1) is None


def test_from_index_non_numeric_is_none():
    assert Board.from_index("urgent") is None
    assert Board.from_index(None) is None


def test_from_name_is_case_insensitive():
    assert Board.from_name("Urgent") is board.URGENT
    assert Board.from_name("urgent") is board.URGENT
    assert Board.from_name("URGENT") is board.URGENT
    assert Board.from_name("  general  ") is board.GENERAL


def test_from_name_unknown_is_none():
    assert Board.from_name("Sports") is None
    assert Board.from_name("") is None
    assert Board.from_name(None) is None


def test_only_urgent_has_special_policy():
    for b in (board.GENERAL, board.INFO, board.NEWS):
        assert not b.is_urgent
        assert not b.requires_post_permission
        assert not b.broadcasts_on_post
    assert board.URGENT.is_urgent
    assert board.URGENT.requires_post_permission
    assert board.URGENT.broadcasts_on_post


def test_boards_are_in_menu_order():
    assert [b.index for b in board.BOARDS] == [0, 1, 2, 3]
    assert [b.name for b in board.BOARDS] == ["General", "Info", "News", "Urgent"]


def test_board_is_hashable_and_frozen():
    # Frozen dataclass: usable as a dict key, not mutable.
    seen = {board.URGENT: 1}
    assert seen[Board.from_name("urgent")] == 1


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
