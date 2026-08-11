"""Unit tests for Js8Flow — pure, with a fake JS8Call store."""

import os
import sys

# Run from anywhere: put the repo root on the path before importing the modules
# under test. Keeps `python tests/test_x.py` working alongside pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flows.base import Deps, Stay, Goto
from flows.js8 import JS8_MENU, Js8Flow


class FakeJs8:
    def __init__(self, groups=None, stations=None, urgent=None, per_group=None):
        self._groups = groups or []
        self._stations = stations or []
        self._urgent = urgent or []
        self._per_group = per_group or {}

    def group_names(self):
        return self._groups

    def station_messages(self):
        return self._stations

    def urgent_messages(self):
        return self._urgent

    def messages_for_group(self, name):
        return self._per_group.get(name, [])


def deps(js8=None):
    return Deps(js8=js8 or FakeJs8())


MENU = {"command": "JS8CALL_MENU", "step": 1}


def group_state(groups):
    return {"command": "GROUP_MESSAGES", "step": 1, "groups": groups}


# --- entry + menu ----------------------------------------------------------

def test_entry_shows_menu():
    r = Js8Flow().entry(deps())
    assert r.replies == [JS8_MENU]
    assert r.outcome == Stay(MENU)


def test_invalid_option_reshows_menu():
    r = Js8Flow().advance("z", MENU, deps())
    assert r.replies == ["Invalid option. Please choose again.", JS8_MENU]
    assert r.outcome == Stay(MENU)


def test_exit_goes_to_main():
    assert Js8Flow().advance("x", MENU, deps()).outcome == Goto("main")


# --- reads when the bridge is empty or unconfigured ------------------------

def test_no_group_messages():
    r = Js8Flow().advance("g", MENU, deps())
    assert r.replies == ["No group messages available.", JS8_MENU]
    assert r.outcome == Stay(MENU)


def test_no_station_messages():
    r = Js8Flow().advance("s", MENU, deps())
    assert r.replies == ["No station messages available.", JS8_MENU]


def test_no_urgent_messages():
    r = Js8Flow().advance("u", MENU, deps())
    assert r.replies == ["No urgent messages available.", JS8_MENU]


# --- reads with content ----------------------------------------------------

def test_group_menu_lists_groups():
    js8 = FakeJs8(groups=[("@NET",), ("@EMCOMM",)])
    r = Js8Flow().advance("g", MENU, deps(js8))
    assert "[0] @NET" in r.replies[0]
    assert "[1] @EMCOMM" in r.replies[0]
    assert r.outcome == Stay(group_state([("@NET",), ("@EMCOMM",)]))


def test_station_messages_listed():
    js8 = FakeJs8(stations=[("A", "B", "hi", "2026-07-08")])
    r = Js8Flow().advance("s", MENU, deps(js8))
    assert "[1] A -> B: hi (2026-07-08)" in r.replies[0]
    assert r.replies[-1] == JS8_MENU


def test_urgent_messages_listed():
    js8 = FakeJs8(urgent=[("A", "@URGNT", "mayday", "2026-07-08")])
    r = Js8Flow().advance("u", MENU, deps(js8))
    assert "[1] A -> @URGNT: mayday (2026-07-08)" in r.replies[0]


# --- selecting a group -----------------------------------------------------

def test_select_group_shows_its_messages():
    js8 = FakeJs8(groups=[("@NET",)],
                  per_group={"@NET": [("A", "hello", "2026-07-08")]})
    r = Js8Flow().advance("0", group_state([("@NET",)]), deps(js8))
    assert "Messages for group @NET:" in r.replies[0]
    assert "[1] A: hello (2026-07-08)" in r.replies[0]
    assert r.outcome == Stay(MENU)


def test_select_group_with_no_messages():
    js8 = FakeJs8(groups=[("@NET",)])
    r = Js8Flow().advance("0", group_state([("@NET",)]), deps(js8))
    assert r.replies[0] == "No messages for group @NET."


def test_select_group_out_of_range_relists():
    js8 = FakeJs8(groups=[("@NET",)])
    r = Js8Flow().advance("9", group_state([("@NET",)]), deps(js8))
    assert r.replies[0] == "Invalid group selection. Please choose again."
    assert "[0] @NET" in r.replies[1]
    assert r.replies[-1] == JS8_MENU
    assert r.outcome == Stay(MENU)


def test_select_group_non_numeric_relists():
    js8 = FakeJs8(groups=[("@NET",)])
    r = Js8Flow().advance("abc", group_state([("@NET",)]), deps(js8))
    assert r.replies[0] == "Invalid group selection. Please choose again."


def test_select_group_when_groups_vanished():
    r = Js8Flow().advance("0", group_state([]), deps())
    assert r.replies[1] == "No group messages available."


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
