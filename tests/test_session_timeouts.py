"""Tests for Session.check_timeouts — the compose-timeout auto-post sweep.

A node sitting in a bulletin-post or mail-compose step (waiting for END) that
goes quiet for COMPOSE_TIMEOUT_SECONDS gets finished automatically: an empty
draft is discarded, a non-empty one is posted exactly as if the node had sent
"END" itself. Drives the real Session and real flows, like test_session.py —
only the store and lookup are fakes.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from session import Session, COMPOSE_TIMEOUT_SECONDS
from flows.base import Deps
from settings import Menus
from roster import Node

MENUS = Menus(main=["Q", "B", "U", "X"],
              bbs=["M", "B", "C", "J", "X"],
              utilities=["S", "F", "W", "X"])

NODE = 42
T0 = 1_000_000.0


class FakeStore:
    def __init__(self):
        self.bulletins_added = []
        self.mail_added = []
        self._mail = []

    def get_mail(self, node_id):
        return self._mail

    def get_bulletins(self, board):
        return []

    def add_bulletin(self, board, sender_short_name, subject, content):
        self.bulletins_added.append((board, sender_short_name, subject, content))
        return "uid-1"

    def add_mail(self, sender_id, sender_short_name, recipient_id, subject, content):
        self.mail_added.append((sender_id, sender_short_name, recipient_id, subject, content))
        return "uid-1"


class FakeLookup:
    def __init__(self):
        self._nodes = {"bob": [Node("!bob", "BOB", "Bob Node")]}
        self._names = {"!bob": "Bob Node"}

    def node_info(self, short_name):
        return self._nodes.get(short_name, [])

    def node_name(self, node_id):
        return self._names.get(node_id, f"Node {node_id}")

    def short_name(self, node_id):
        return "ME" if node_id == "!me" else None


def deps(store):
    return Deps(store=store, lookup=FakeLookup(), menus=MENUS, fortunes=[],
                node_id="!me", roster={})


def texts(outbound):
    return [text for _, text in outbound]


def deps_factory(store):
    return lambda node: deps(store)


def enter_bulletin_compose(session, store, now=T0):
    session.advance(NODE, "b", deps(store), now=now)          # bbs menu
    session.advance(NODE, "b", deps(store), now=now)          # bulletin menu
    session.advance(NODE, "g", deps(store), now=now)          # General board
    session.advance(NODE, "p", deps(store), now=now)          # post -> subject prompt
    session.advance(NODE, "My Subject", deps(store), now=now)  # -> BULLETIN_POST_CONTENT


def enter_mail_compose(session, store, now=T0):
    session.advance(NODE, "b", deps(store), now=now)          # bbs menu
    session.advance(NODE, "m", deps(store), now=now)          # mail menu
    session.advance(NODE, "s", deps(store), now=now)          # send -> short name prompt
    session.advance(NODE, "bob", deps(store), now=now)        # recipient resolved -> subject prompt
    session.advance(NODE, "Greetings", deps(store), now=now)  # -> MAIL step 7


# --- bulletins ---------------------------------------------------------------

def test_bulletin_compose_not_yet_expired_does_nothing():
    store = FakeStore()
    s = Session()
    enter_bulletin_compose(s, store)
    s.advance(NODE, "line one", deps(store), now=T0)

    out = s.check_timeouts(deps_factory(store), now=T0 + COMPOSE_TIMEOUT_SECONDS - 1)
    assert out == []
    assert store.bulletins_added == []


def test_bulletin_compose_with_content_auto_posts_like_manual_end():
    store = FakeStore()
    s = Session()
    enter_bulletin_compose(s, store)
    s.advance(NODE, "line one", deps(store), now=T0)

    out = s.check_timeouts(deps_factory(store), now=T0 + COMPOSE_TIMEOUT_SECONDS + 1)
    assert store.bulletins_added == [("General", "ME", "My Subject", "line one\n")]
    assert any("posted to General" in t for t in texts(out))

    # Landed back at the Bulletin menu, same as a manual END.
    assert any("Bulletin Menu" in t for t in texts(out))


def test_bulletin_compose_with_empty_content_is_discarded_silently():
    store = FakeStore()
    s = Session()
    enter_bulletin_compose(s, store)   # no content line sent

    out = s.check_timeouts(deps_factory(store), now=T0 + COMPOSE_TIMEOUT_SECONDS + 1)
    assert out == []
    assert store.bulletins_added == []

    # State was cleared, not left mid-compose.
    again = s.advance(NODE, "hello", deps(store))
    assert any("TC² BBS" in t for t in texts(again))


# --- mail ----------------------------------------------------------------

def test_mail_compose_with_content_auto_sends_like_manual_end():
    store = FakeStore()
    s = Session()
    enter_mail_compose(s, store)
    s.advance(NODE, "Body line", deps(store), now=T0)

    out = s.check_timeouts(deps_factory(store), now=T0 + COMPOSE_TIMEOUT_SECONDS + 1)
    assert store.mail_added == [("!me", "ME", "!bob", "Greetings", "Body line\n")]
    assert any("mailbox of Bob Node" in t for t in texts(out))
    assert any(dest == "!bob" for dest, _ in out)   # the recipient notification


def test_mail_compose_with_empty_content_is_discarded_silently():
    store = FakeStore()
    s = Session()
    enter_mail_compose(s, store)   # no content line sent

    out = s.check_timeouts(deps_factory(store), now=T0 + COMPOSE_TIMEOUT_SECONDS + 1)
    assert out == []
    assert store.mail_added == []


# --- the timer is inactivity-based, not a fixed deadline from entry ---------

def test_timer_resets_on_each_line_sent():
    store = FakeStore()
    s = Session()
    enter_bulletin_compose(s, store, now=T0)
    # Goes quiet for a while, then types a line — the clock should restart here.
    s.advance(NODE, "line one", deps(store), now=T0 + 250)

    just_under = T0 + 250 + COMPOSE_TIMEOUT_SECONDS - 1
    out = s.check_timeouts(deps_factory(store), now=just_under)
    assert out == []
    assert store.bulletins_added == []

    past = T0 + 250 + COMPOSE_TIMEOUT_SECONDS + 1
    out = s.check_timeouts(deps_factory(store), now=past)
    assert store.bulletins_added == [("General", "ME", "My Subject", "line one\n")]


# --- out of scope: other states are left alone ------------------------------

def test_node_outside_compose_is_never_touched():
    store = FakeStore()
    s = Session()
    s.advance(NODE, "b", deps(store), now=T0)   # sitting at the BBS menu, not composing

    out = s.check_timeouts(deps_factory(store), now=T0 + COMPOSE_TIMEOUT_SECONDS + 100)
    assert out == []

    # Still at the BBS menu — 'm' should reach Mail, proving state survived.
    again = s.advance(NODE, "m", deps(store))
    assert any("Mail Menu" in t for t in texts(again))


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
