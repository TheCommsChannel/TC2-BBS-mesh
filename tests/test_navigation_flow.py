"""Unit tests for NavigationFlow — pure, no config file, no interface."""

import os
import sys

# Run from anywhere: put the repo root on the path before importing the modules
# under test. Keeps `python tests/test_x.py` working alongside pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flows.base import Deps, Stay, Enter
from flows.navigation import (
    BBS_TITLE, NavigationFlow, QUICK_HELP, UTILITIES_TITLE, build_menu,
)
from settings import Menus


class FakeStore:
    def __init__(self, mail=None):
        self._mail = mail or []

    def get_mail(self, recipient_id):
        return self._mail


MENUS = Menus(main=["Q", "B", "U", "X"],
              bbs=["M", "B", "C", "J", "X"],
              utilities=["S", "F", "W", "X"])


def deps(store=None, roster=None, fortunes=None):
    return Deps(store=store or FakeStore(), roster=roster or {},
                node_id="!me", menus=MENUS, fortunes=fortunes or [])


MAIN = {"command": "MAIN_MENU", "step": 1}
BBS = {"command": "MENU", "menu": "bbs", "step": 1}
UTIL = {"command": "MENU", "menu": "utilities", "step": 1}


# --- rendering -------------------------------------------------------------

def test_build_menu_labels_b_by_menu():
    assert "[B]ulletins" in build_menu(["B"], BBS_TITLE)
    assert "[B]BS" in build_menu(["B"], "anything else")


def test_main_menu_shows_unread_count():
    r = NavigationFlow().show("main", deps(FakeStore(mail=[1, 2, 3])))
    assert "✉️:3" in r.replies[0]
    assert r.outcome == Stay(MAIN)


def test_unknown_menu_name_falls_back_to_main():
    # The handler this replaces raised NameError here.
    r = NavigationFlow().show("nonsense", deps())
    assert "TC² BBS" in r.replies[0]
    assert r.outcome == Stay(MAIN)


def test_show_bbs_and_utilities():
    assert BBS_TITLE in NavigationFlow().show("bbs", deps()).replies[0]
    assert NavigationFlow().show("bbs", deps()).outcome == Stay(BBS)
    assert UTILITIES_TITLE in NavigationFlow().show("utilities", deps()).replies[0]
    assert NavigationFlow().show("utilities", deps()).outcome == Stay(UTIL)


# --- main menu -------------------------------------------------------------

def test_main_quick_help_stays_put():
    r = NavigationFlow().advance("q", MAIN, deps())
    assert r.replies == [QUICK_HELP]
    assert r.outcome == Stay(MAIN)


def test_main_b_opens_bbs_menu():
    r = NavigationFlow().advance("b", MAIN, deps())
    assert r.outcome == Stay(BBS)


def test_main_unknown_reshows_main():
    r = NavigationFlow().advance("zzz", MAIN, deps())
    assert r.outcome == Stay(MAIN)


def test_no_state_is_treated_as_main_menu():
    r = NavigationFlow().advance("q", {}, deps())
    assert r.replies == [QUICK_HELP]


# --- bbs menu: hand-offs ---------------------------------------------------

def test_bbs_selections_enter_flows():
    nav = NavigationFlow()
    assert nav.advance("m", BBS, deps()).outcome == Enter("MAIL")
    assert nav.advance("b", BBS, deps()).outcome == Enter("BULLETIN_MENU")
    assert nav.advance("c", BBS, deps()).outcome == Enter("CHANNEL_DIRECTORY")
    assert nav.advance("j", BBS, deps()).outcome == Enter("JS8CALL_MENU")


def test_bbs_unknown_falls_back_to_main():
    r = NavigationFlow().advance("zzz", BBS, deps())
    assert r.outcome == Stay(MAIN)


# --- utilities menu: enter + leaves ---------------------------------------

def test_utilities_stats_enters_flow():
    assert NavigationFlow().advance("s", UTIL, deps()).outcome == Enter("STATS")


def test_fortune_leaf_stays_in_utilities():
    r = NavigationFlow().advance("f", UTIL, deps(fortunes=["Be brief"]))
    assert r.replies == ["🔮 Be brief 🔮"]
    assert r.outcome == Stay(UTIL)


def test_fortune_with_none_available():
    r = NavigationFlow().advance("f", UTIL, deps(fortunes=[]))
    assert r.replies == ["No fortunes available."]


def test_wall_of_shame_lists_low_batteries():
    roster = {
        "!a": {"user": {"longName": "Flat"}, "deviceMetrics": {"batteryLevel": 5}},
        "!b": {"user": {"longName": "Fine"}, "deviceMetrics": {"batteryLevel": 90}},
    }
    r = NavigationFlow().advance("w", UTIL, deps(roster=roster))
    assert "Flat - Battery 5%" in r.replies[0]
    assert "Fine" not in r.replies[0]
    assert r.outcome == Stay(UTIL)


def test_wall_of_shame_when_all_healthy():
    roster = {"!b": {"user": {"longName": "Fine"}, "deviceMetrics": {"batteryLevel": 90}}}
    r = NavigationFlow().advance("w", UTIL, deps(roster=roster))
    assert r.replies == ["No devices with battery levels below 20% found."]


def test_node_without_metrics_is_not_shamed():
    roster = {"!c": {"user": {"longName": "Quiet"}}}
    r = NavigationFlow().advance("w", UTIL, deps(roster=roster))
    assert "Quiet" not in r.replies[0]


def test_repeated_x_suffix_collapses():
    # "fx" collapses to "f" -> fortune, not exit
    r = NavigationFlow().advance("fx", UTIL, deps(fortunes=["Hi"]))
    assert r.replies == ["🔮 Hi 🔮"]


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
