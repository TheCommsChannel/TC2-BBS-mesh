"""Unit tests for BulletinFlow — pure, with a fake store.

No interface, no database. A fake store stands in for persistence; the flow's
replies and next state are asserted directly. Covers board selection, read,
post, and the urgent permission branch that consumes the Board policy flags.
"""

import os
import sys

# Run from anywhere: put the repo root on the path before importing the modules
# under test. Keeps `python tests/test_x.py` working alongside pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flows.base import Deps, UNKNOWN_NODE_REPLY, Stay, End, Keep, Goto
from flows.bulletin import BulletinFlow


class FakeStore:
    def __init__(self, bulletins=None, content=None):
        self._bulletins = bulletins or {}     # board name -> list of rows
        self._content = content or {}         # id -> content tuple
        self.added = []                       # recorded add_bulletin calls

    def get_bulletins(self, board):
        return self._bulletins.get(board, [])

    def get_bulletin_content(self, bulletin_id):
        return self._content[bulletin_id]

    def add_bulletin(self, board, sender_short_name, subject, content):
        self.added.append((board, sender_short_name, subject, content))
        return "uid-1"


class FakeLookup:
    def __init__(self, shorts=None):
        self._shorts = shorts if shorts is not None else {"!me": "ME"}

    def short_name(self, node_id):
        return self._shorts.get(node_id)


def deps(store=None, node_id="!me", allowed=None, roster=None, lookup=None):
    return Deps(
        roster=roster if roster is not None else {"!me": {"user": {"shortName": "ME"}}},
        store=store or FakeStore(),
        lookup=lookup or FakeLookup(),
        node_id=node_id,
        allowed_nodes=allowed or [],
    )


def st(command, **extra):
    return {"command": command, **extra}


# --- board selection -------------------------------------------------------

def test_select_board_reports_count_and_advances():
    store = FakeStore(bulletins={"General": [(1, "Hi", "AA", "d", "u")]})
    r = BulletinFlow().advance("g", st("BULLETIN_MENU"), deps(store))
    assert "General has 1 messages" in r.replies[0]
    assert r.outcome == Stay({"command": "BULLETIN_ACTION", "step": 2, "board": "General"})


def test_unknown_board_letter_goes_to_main():
    r = BulletinFlow().advance("z", st("BULLETIN_MENU"), deps())
    assert r.outcome == Goto("main")


def test_junk_at_board_menu_reprompts_the_board_menu():
    r = BulletinFlow().advance("q", st("BULLETIN_ACTION", board="General"), deps())
    assert r.replies[0] == "Please enter R or P."
    assert "General has 0 messages" in r.replies[1]
    assert r.outcome == Stay({"command": "BULLETIN_ACTION", "step": 2, "board": "General"})


# --- read ------------------------------------------------------------------

def test_read_empty_board_returns_to_board_menu():
    r = BulletinFlow().advance("r", st("BULLETIN_ACTION", board="News"), deps())
    assert r.replies[0] == "No bulletins in News."
    assert "News has 0 messages" in r.replies[1]
    assert r.outcome == Stay({"command": "BULLETIN_ACTION", "step": 2, "board": "News"})


def test_read_lists_bulletins():
    store = FakeStore(bulletins={"Info": [(7, "Subject A", "AA", "d", "u"),
                                          (9, "Subject B", "BB", "d", "u")]})
    r = BulletinFlow().advance("r", st("BULLETIN_ACTION", board="Info"), deps(store))
    assert r.replies == ["Select a bulletin number to view from Info:\n"
                          "[7] Subject A\n[9] Subject B"]
    assert r.outcome.state["command"] == "BULLETIN_READ"


def test_read_lists_bulletins_caps_at_four_per_message():
    bulletins = [(i, f"Subject {i}", "AA", "d", "u") for i in range(1, 6)]
    store = FakeStore(bulletins={"Info": bulletins})
    r = BulletinFlow().advance("r", st("BULLETIN_ACTION", board="Info"), deps(store))
    assert len(r.replies) == 2
    assert r.replies[0].count("[") == 4  # 4 bulletin lines packed with the header
    assert r.replies[1] == "[5] Subject 5"


def test_read_lists_bulletins_splits_on_char_limit():
    long_title = "X" * 190
    bulletins = [(1, "Short", "AA", "d", "u"), (2, long_title, "BB", "d", "u")]
    store = FakeStore(bulletins={"Info": bulletins})
    r = BulletinFlow().advance("r", st("BULLETIN_ACTION", board="Info"), deps(store))
    assert len(r.replies) == 2
    assert all(len(m) <= 200 for m in r.replies)


def test_read_bulletin_shows_content_then_relists_board():
    store = FakeStore(content={7: ("AA", "2026-07-01", "Subject A", "Body", "u")},
                       bulletins={"Info": [(7, "Subject A", "AA", "d", "u")]})
    r = BulletinFlow().advance("7", st("BULLETIN_READ", board="Info"), deps(store))
    assert "From: AA" in r.replies[0]
    assert "Subject: Subject A" in r.replies[0]
    assert "Body" in r.replies[0]
    assert r.replies[1] == "Select a bulletin number to view from Info:\n[7] Subject A"
    assert r.outcome == Stay({"command": "BULLETIN_READ", "step": 3, "board": "Info"})


def test_read_bulletin_then_empty_board_returns_to_board_menu():
    store = FakeStore(content={7: ("AA", "2026-07-01", "Subject A", "Body", "u")})
    r = BulletinFlow().advance("7", st("BULLETIN_READ", board="Info"), deps(store))
    assert "From: AA" in r.replies[0]
    assert "Info has 0 messages" in r.replies[1]
    assert r.outcome == Stay({"command": "BULLETIN_ACTION", "step": 2, "board": "Info"})


# --- post + urgent permission ---------------------------------------------

def test_post_to_general_prompts_for_subject():
    r = BulletinFlow().advance("p", st("BULLETIN_ACTION", board="General"), deps())
    assert "subject" in r.replies[0].lower()
    assert r.outcome.state["command"] == "BULLETIN_POST"


def test_urgent_post_denied_when_not_allowed():
    d = deps(node_id="!me", allowed=["!someone_else"])
    r = BulletinFlow().advance("p", st("BULLETIN_ACTION", board="Urgent"), d)
    assert "don't have permission" in r.replies[0]
    assert "Urgent has 0 messages" in r.replies[1]
    assert r.outcome == Stay({"command": "BULLETIN_ACTION", "step": 2, "board": "Urgent"})


def test_urgent_post_allowed_when_listed():
    d = deps(node_id="!me", allowed=["!me"])
    r = BulletinFlow().advance("p", st("BULLETIN_ACTION", board="Urgent"), d)
    assert "subject" in r.replies[0].lower()
    assert r.outcome.state["command"] == "BULLETIN_POST"


def test_empty_allow_list_permits_urgent_post():
    # Matches legacy: no allow-list configured => anyone may post.
    d = deps(node_id="!me", allowed=[])
    r = BulletinFlow().advance("p", st("BULLETIN_ACTION", board="Urgent"), d)
    assert r.outcome.state["command"] == "BULLETIN_POST"


# --- content accumulation + commit ----------------------------------------

def test_content_accumulates_until_end():
    state = st("BULLETIN_POST_CONTENT", board="General", subject="Hi", content="")
    r = BulletinFlow().advance("line one", state, deps())
    assert r.replies == []
    assert r.outcome.state["content"] == "line one\n"


def test_end_persists_and_returns_to_bulletin_menu():
    store = FakeStore()
    state = st("BULLETIN_POST_CONTENT", board="General", subject="Hi", content="body\n")
    r = BulletinFlow().advance("END", state, deps(store))
    assert store.added == [("General", "ME", "Hi", "body\n")]
    assert "posted to General" in r.replies[0]
    assert r.outcome == Stay({"command": "BULLETIN_MENU", "step": 1})


def test_end_without_node_info_errors():
    store = FakeStore()
    state = st("BULLETIN_POST_CONTENT", board="General", subject="Hi", content="x")
    d = deps(store, node_id="!gone", roster={})   # acting node not in roster
    r = BulletinFlow().advance("END", state, d)
    assert "Unable to retrieve your node information" in r.replies[0]
    assert r.outcome == End()
    assert store.added == []


def test_quick_post_refuses_an_unidentified_poster():
    """PB,, used to store sender_short_name=None and replicate it to peers."""
    store = FakeStore()
    d = deps(store, node_id="!ghost", roster={})
    r = BulletinFlow().quick_post("pb,,General,,Subj,,Body", d)
    assert r.replies == [UNKNOWN_NODE_REPLY]
    assert store.added == []
    assert isinstance(r.outcome, Keep)


def test_both_post_paths_refuse_a_node_without_a_short_name():
    """A Node present in the roster but unnamed cannot author a Bulletin."""
    store = FakeStore()
    d = deps(store, node_id="!nameless", lookup=FakeLookup(shorts={}))

    quick = BulletinFlow().quick_post("pb,,General,,Subj,,Body", d)
    state = st("BULLETIN_POST_CONTENT", board="General", subject="Hi", content="x")
    menu = BulletinFlow().advance("END", state, d)

    assert quick.replies == [UNKNOWN_NODE_REPLY]
    assert menu.replies == [UNKNOWN_NODE_REPLY]
    assert store.added == []


# --- PB,, quick post -------------------------------------------------------

def test_quick_post_usage_on_bad_format():
    r = BulletinFlow().quick_post("pb,,only,,two", deps())
    assert "Post Bulletin Quick Command format" in r.replies[0]
    assert isinstance(r.outcome, Keep)


def test_quick_post_rejects_unknown_board():
    r = BulletinFlow().quick_post("pb,,Sports,,Subj,,Body", deps())
    assert r.replies == ["Unknown board 'Sports'. Try General, Info, News, or Urgent."]
    assert isinstance(r.outcome, Keep)


def test_quick_post_to_general_succeeds():
    store = FakeStore()
    r = BulletinFlow().quick_post("pb,,general,,Subj,,Body", deps(store))
    # The canonical board name is used, not whatever case was typed.
    assert store.added == [("General", "ME", "Subj", "Body")]
    assert "posted to General" in r.replies[0]
    assert isinstance(r.outcome, Keep)


def test_quick_post_to_urgent_respects_the_allow_list():
    """PB,,Urgent used to bypass the allow-list entirely and broadcast."""
    store = FakeStore()
    d = deps(store, node_id="!me", allowed=["!someone_else"])
    r = BulletinFlow().quick_post("pb,,Urgent,,Fake alert,,ignore", d)
    assert r.replies == ["You don't have permission to post to this board."]
    assert store.added == []


def test_quick_post_to_urgent_allowed_when_listed():
    store = FakeStore()
    d = deps(store, node_id="!me", allowed=["!me"])
    r = BulletinFlow().quick_post("pb,,Urgent,,Real alert,,move", d)
    assert store.added == [("Urgent", "ME", "Real alert", "move")]


def test_quick_post_to_urgent_allowed_when_no_list_configured():
    store = FakeStore()
    r = BulletinFlow().quick_post("pb,,Urgent,,Alert,,move", deps(store, allowed=[]))
    assert store.added == [("Urgent", "ME", "Alert", "move")]


# --- CB,, quick check ------------------------------------------------------

def test_quick_check_usage_on_bad_format():
    r = BulletinFlow().quick_check("cb,,", deps())
    assert "Check Bulletins Quick Command format" in r.replies[0]


def test_quick_check_rejects_unknown_board():
    r = BulletinFlow().quick_check("cb,,Sports", deps())
    assert r.replies == ["Unknown board 'Sports'. Try General, Info, News, or Urgent."]


def test_quick_check_empty_board():
    r = BulletinFlow().quick_check("cb,,news", deps())
    assert r.replies == ["No bulletins available on News board."]
    assert isinstance(r.outcome, Keep)


def test_quick_check_lists_and_awaits_a_number():
    store = FakeStore(bulletins={"Info": [(7, "Subj", "AA", "2026-07-08", "u")]})
    r = BulletinFlow().quick_check("cb,,info", deps(store))
    assert "📰 Bulletins on Info board:" in r.replies[0]
    assert "[01] Subject: Subj" in r.replies[0]
    assert r.outcome.state["command"] == "CHECK_BULLETIN"


def test_quick_check_caps_at_four_per_message():
    bulletins = [(i, f"Subj {i}", "AA", "2026-07-08", "u") for i in range(1, 6)]
    store = FakeStore(bulletins={"Info": bulletins})
    r = BulletinFlow().quick_check("cb,,info", deps(store))
    assert len(r.replies) > 1
    assert all(len(m) <= 200 for m in r.replies)
    assert sum(m.count("Subject:") for m in r.replies) == 5
    assert r.replies[-1].endswith("number of the bulletin you want to read.")


# --- CHECK_BULLETIN numbered read -----------------------------------------

def test_check_bulletin_read_valid():
    store = FakeStore(content={7: ("AA", "2026-07-08", "Subj", "Body", "u")})
    state = st("CHECK_BULLETIN", step=1, bulletins=[(7, "Subj", "AA", "d", "u")])
    r = BulletinFlow().advance("1", state, deps(store))
    assert "From: AA" in r.replies[0]
    assert "Body" in r.replies[0]
    assert r.outcome == End()


def test_check_bulletin_read_out_of_range():
    state = st("CHECK_BULLETIN", step=1, bulletins=[(7, "Subj", "AA", "d", "u")])
    r = BulletinFlow().advance("9", state, deps())
    assert "Invalid bulletin number" in r.replies[0]
    assert r.outcome == Stay(state)


def test_check_bulletin_read_non_numeric():
    state = st("CHECK_BULLETIN", step=1, bulletins=[(7, "Subj", "AA", "d", "u")])
    r = BulletinFlow().advance("abc", state, deps())
    assert "Invalid input" in r.replies[0]


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
