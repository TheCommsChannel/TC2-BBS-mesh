"""Tests for the Session — it owns where each Node stands in its conversation.

The point of candidate 02: the per-node state lives on the Session object, not
in a module global. These tests drive real flows and assert the state persisted
by observing what the next message does, and that two Sessions are independent.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from session import Session
from flows.base import Deps
from settings import Menus

MENUS = Menus(main=["Q", "B", "U", "X"],
              bbs=["M", "B", "C", "J", "X"],
              utilities=["S", "F", "W", "X"])


class FakeStore:
    def get_mail(self, node_id):
        return []

    def get_bulletins(self, board):
        return []

    def get_channels(self):
        return []


def deps():
    return Deps(store=FakeStore(), menus=MENUS, fortunes=[], node_id="!me", roster={})


def texts(outbound):
    return [text for _, text in outbound]


def test_advance_returns_outbound_addressed_to_the_node():
    out = Session().advance(42, "hello", deps())
    assert out                                   # something was said
    assert all(dest == 42 for dest, _ in out)


def test_unknown_message_shows_the_main_menu():
    out = Session().advance(1, "hello", deps())
    assert any("TC² BBS" in t for t in texts(out))


def test_state_persists_across_advance_calls():
    """Entering the BBS menu, then 'm', reaches Mail — only possible if the
    Session remembered that node 1 was in the BBS menu."""
    s = Session()
    first = s.advance(1, "b", deps())
    assert any("BBS Menu" in t for t in texts(first))

    second = s.advance(1, "m", deps())
    assert any("Mail Menu" in t for t in texts(second))


def test_exit_from_a_flow_returns_to_main():
    s = Session()
    s.advance(1, "b", deps())          # into the bbs menu
    out = s.advance(1, "x", deps())
    assert any("TC² BBS" in t for t in texts(out))


def test_two_sessions_do_not_share_state():
    a, b = Session(), Session()
    a.advance(1, "b", deps())          # a's node 1 is in the bbs menu
    out = b.advance(1, "m", deps())    # b's node 1 has never navigated
    # b sees 'm' from the main menu, which is not a bbs selection -> main menu.
    assert any("TC² BBS" in t for t in texts(out))


def test_different_nodes_have_separate_state_in_one_session():
    s = Session()
    s.advance(1, "b", deps())          # node 1 into the bbs menu
    out = s.advance(2, "m", deps())    # node 2 is still at the main menu
    assert any("TC² BBS" in t for t in texts(out))


def test_bare_quick_command_shows_its_usage_instead_of_the_main_menu():
    """PB (no ,,args) used to miss the "pb,," prefix match entirely and fall
    through to ordinary menu routing, silently resetting to the main menu."""
    out = Session().advance(1, "PB", deps())
    assert any("Post Bulletin Quick Command format" in t for t in texts(out))

    out = Session().advance(1, "CB", deps())
    assert any("Check Bulletins Quick Command format" in t for t in texts(out))

    out = Session().advance(1, "SM", deps())
    assert any("Send Mail Quick Command format" in t for t in texts(out))

    out = Session().advance(1, "CHP", deps())
    assert any("Post Channel Quick Command format" in t for t in texts(out))


def test_full_quick_command_with_args_still_works():
    """The bare-word fallback must not shadow the existing ',,args' form."""
    out = Session().advance(1, "CB,,General", deps())
    assert any("No bulletins available on General board" in t for t in texts(out))


def test_no_arg_quick_commands_are_unaffected_by_the_bare_word_fallback():
    """CM and CHL already matched bare, with no ',,' key at all."""
    out = Session().advance(1, "CM", deps())
    assert any("no new messages" in t.lower() for t in texts(out))

    out = Session().advance(1, "CHL", deps())
    assert any("No channels available" in t for t in texts(out))


def test_typoed_comma_separator_shows_usage_instead_of_the_main_menu():
    """PB, , General,,Subj,,Body — a space snuck between the two commas, so
    the message doesn't start with the literal "pb,," prefix. It should still
    be recognized as an attempted PB and show usage, not silently reset."""
    out = Session().advance(1, "PB, , General,,Quick Command,,Body", deps())
    assert any("Post Bulletin Quick Command format" in t for t in texts(out))


def test_ordinary_text_starting_with_a_command_letter_is_not_mistaken_for_one():
    """"Small dog" starts with "sm" but has no comma right after it — must not
    be treated as a malformed SM,, attempt."""
    out = Session().advance(1, "Small dog", deps())
    assert any("TC² BBS" in t for t in texts(out))


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
