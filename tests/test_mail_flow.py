"""Unit tests for MailFlow — pure, with fake store + lookup.

No interface, no database. Covers the MAIL step machine and the CHECK_MAIL
read/confirm steps, including the recipient notification that rides back on
the FlowResult.
"""

import os
import sys

# Run from anywhere: put the repo root on the path before importing the modules
# under test. Keeps `python tests/test_x.py` working alongside pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flows.base import Deps, UNKNOWN_NODE_REPLY, Stay, End, Keep
from flows.mail import MailFlow, MAIL_MENU
from roster import Node


class FakeStore:
    def __init__(self, mail=None, content=None, sender_by_mail=None):
        self._mail = mail or []
        self._content = content or {}
        self._sender_by_mail = sender_by_mail or {}
        self.added = []
        self.deleted = []

    def get_mail(self, recipient_id):
        return self._mail

    def get_mail_content(self, mail_id, recipient_id):
        return self._content.get(mail_id)

    def add_mail(self, sender_id, sender_short_name, recipient_id, subject, content):
        self.added.append((sender_id, sender_short_name, recipient_id, subject, content))
        return "uid-1"

    def delete_mail(self, unique_id, recipient_id):
        self.deleted.append((unique_id, recipient_id))

    def sender_id_by_mail_id(self, mail_id):
        return self._sender_by_mail.get(mail_id)


class FakeLookup:
    def __init__(self, nodes=None, names=None, shorts=None):
        self._nodes = nodes or {}
        self._names = names or {}
        self._shorts = shorts or {}

    def node_info(self, short_name):
        return self._nodes.get(short_name, [])

    def node_name(self, node_id):
        return self._names.get(node_id, f"Node {node_id}")

    def short_name(self, node_id):
        return self._shorts.get(node_id)


def deps(store=None, lookup=None, node_id="!me"):
    return Deps(store=store or FakeStore(), lookup=lookup or FakeLookup(),
                node_id=node_id)


def st(command, step, **extra):
    return {"command": command, "step": step, **extra}


# --- MAIL menu -------------------------------------------------------------

def test_read_empty_inbox_ends():
    r = MailFlow().advance("r", st("MAIL", 1), deps())
    assert r.replies == ["There are no messages in your mailbox.📭"]
    assert r.outcome == End()


def test_read_lists_messages_and_advances():
    store = FakeStore(mail=[(5, "AA", "Hello", "2026-07-01", "u5")])
    r = MailFlow().advance("r", st("MAIL", 1), deps(store))
    assert "You have 1 mail messages" in r.replies[0]
    assert "-5-" in r.replies[1] and "From: AA" in r.replies[1]
    assert r.outcome == Stay({"command": "MAIL", "step": 2})


def test_send_prompts_for_short_name():
    r = MailFlow().advance("s", st("MAIL", 1), deps())
    assert "Short Name" in r.replies[0]
    assert r.outcome.state["step"] == 3


# --- open a message --------------------------------------------------------

def test_open_message_shows_content_and_options():
    store = FakeStore(content={5: ("AA", "2026-07-01", "Hello", "Body", "u5")})
    r = MailFlow().advance("5", st("MAIL", 2), deps(store))
    assert "From: AA" in r.replies[0]
    assert "[K]eep  [D]elete  [R]eply" in r.replies[1]
    assert r.outcome.state["step"] == 4
    assert r.outcome.state["unique_id"] == "u5"


def test_open_missing_message_reports_not_found():
    r = MailFlow().advance("9", st("MAIL", 2), deps(FakeStore(content={})))
    assert r.replies == ["Mail not found"]
    assert r.outcome == End()


# --- recipient resolution --------------------------------------------------

def test_recipient_unknown_returns_to_mail_menu():
    r = MailFlow().advance("zzz", st("MAIL", 3), deps())
    assert r.replies[0] == "I'm unable to find that node in my database."
    assert r.replies[1] == MAIL_MENU
    assert r.outcome == Stay({"command": "MAIL", "step": 1})


def test_recipient_single_prompts_subject():
    lookup = FakeLookup(nodes={"bob": [Node("!bob", "BOB", "Bob Node")]},
                        names={"!bob": "Bob Node"})
    r = MailFlow().advance("Bob", st("MAIL", 3), deps(lookup=lookup))
    assert "message to Bob Node" in r.replies[0]
    assert r.outcome == Stay({"command": "MAIL", "step": 5, "recipient_id": "!bob"})


def test_recipient_multiple_lists_choices():
    lookup = FakeLookup(nodes={"bob": [Node("!b1", "BOB", "Bob One"),
                                       Node("!b2", "BOB", "Bob Two")]})
    r = MailFlow().advance("bob", st("MAIL", 3), deps(lookup=lookup))
    assert "multiple nodes" in r.replies[0]
    assert "[0] Bob One" in r.replies
    assert r.outcome.state["step"] == 6


# --- disposition -----------------------------------------------------------

def test_delete_message():
    store = FakeStore()
    state = st("MAIL", 4, unique_id="u5", mail_id=5, sender="AA", subject="Hi", content="x")
    r = MailFlow().advance("d", state, deps(store))
    assert store.deleted == [("u5", "!me")]
    assert "deleted" in r.replies[0]
    assert r.outcome == End()


def test_reply_sets_up_compose():
    state = st("MAIL", 4, unique_id="u5", mail_id=5, sender="AA", subject="Hi", content="x")
    r = MailFlow().advance("r", state, deps())
    assert "reply to AA" in r.replies[0]
    assert r.outcome.state["reply_to_mail_id"] == 5
    assert r.outcome.state["subject"] == "Re: Hi"


def test_keep_message():
    state = st("MAIL", 4, unique_id="u5", mail_id=5, sender="AA", subject="Hi", content="x")
    r = MailFlow().advance("k", state, deps())
    assert "kept in your inbox" in r.replies[0]
    assert r.outcome == End()


def test_delete_loops_back_to_the_mailbox_when_messages_remain():
    """A person new to the BBS won't know to resend CM after K/D — loop back
    into the listing automatically instead of dead-ending the conversation."""
    store = FakeStore(mail=[(6, "BB", "Second", "2026-07-16", "u6")])
    state = st("MAIL", 4, unique_id="u5", mail_id=5, sender="AA", subject="Hi", content="x")
    r = MailFlow().advance("d", state, deps(store))
    assert "deleted" in r.replies[0]
    assert "following messages" in r.replies[1]
    assert r.outcome == Stay({"command": "CHECK_MAIL", "step": 1,
                              "mail": [(6, "BB", "Second", "2026-07-16", "u6")]})


def test_keep_ends_with_the_empty_mailbox_note_when_nothing_remains():
    state = st("MAIL", 4, unique_id="u5", mail_id=5, sender="AA", subject="Hi", content="x")
    r = MailFlow().advance("k", state, deps())
    assert r.replies == ["The message has been kept in your inbox.✉️",
                         "You have no new messages."]
    assert r.outcome == End()


# --- compose + send --------------------------------------------------------

def test_compose_accumulates_content():
    state = st("MAIL", 7, recipient_id="!bob", subject="Hi", content="")
    r = MailFlow().advance("first line", state, deps())
    assert r.replies == []
    assert r.outcome.state["content"] == "first line\n"


def test_compose_end_sends_mail_and_notifies():
    store = FakeStore()
    lookup = FakeLookup(names={"!bob": "Bob Node"}, shorts={"!me": "ME"})
    state = st("MAIL", 7, recipient_id="!bob", subject="Hi", content="body\n")
    r = MailFlow().advance("END", state, deps(store, lookup))
    assert store.added == [("!me", "ME", "!bob", "Hi", "body\n")]
    assert "mailbox of Bob Node" in r.replies[0]
    assert r.notifications == [("!bob", "You have a new mail message from ME. "
                                "Check your mailbox by responding to this message with CM.")]
    assert r.outcome == Stay({"command": "MAIL", "step": 8})


def test_compose_end_reply_resolves_original_sender():
    store = FakeStore(sender_by_mail={5: "!orig"})
    lookup = FakeLookup(names={"!orig": "Orig Node"}, shorts={"!me": "ME"})
    state = st("MAIL", 7, reply_to_mail_id=5, subject="Re: Hi", content="reply\n")
    r = MailFlow().advance("END", state, deps(store, lookup))
    assert store.added[0][2] == "!orig"       # recipient resolved from mail id
    assert "mailbox of Orig Node" in r.replies[0]


def test_again_yes_reopens_menu():
    r = MailFlow().advance("y", st("MAIL", 8), deps())
    assert r.replies == [MAIL_MENU]
    assert r.outcome == Stay({"command": "MAIL", "step": 1})


def test_again_no_ends():
    r = MailFlow().advance("n", st("MAIL", 8), deps())
    assert "feel free" in r.replies[0]
    assert r.outcome == End()


# --- CHECK_MAIL ------------------------------------------------------------

def test_check_read_valid_number():
    store = FakeStore(content={5: ("AA", "2026-07-01", "Hello", "Body", "u5")})
    state = st("CHECK_MAIL", 1, mail=[(5, "AA", "Hello", "d", "u5")])
    r = MailFlow().advance("1", state, deps(store))
    assert "From: AA" in r.replies[0]
    assert r.outcome.state["step"] == 2
    assert r.outcome.state["mail_id"] == 5


def test_check_read_out_of_range():
    state = st("CHECK_MAIL", 1, mail=[(5, "AA", "Hello", "d", "u5")])
    r = MailFlow().advance("9", state, deps())
    assert "Invalid message number" in r.replies[0]
    assert r.outcome == Stay(state)


def test_check_read_non_numeric():
    state = st("CHECK_MAIL", 1, mail=[(5, "AA", "Hello", "d", "u5")])
    r = MailFlow().advance("abc", state, deps())
    assert "Invalid input" in r.replies[0]
    assert r.outcome == Stay(state)


def test_check_confirm_delete():
    store = FakeStore()
    state = st("CHECK_MAIL", 2, unique_id="u5", mail_id=5, sender="AA", subject="Hi", content="x")
    r = MailFlow().advance("d", state, deps(store))
    assert store.deleted == [("u5", "!me")]
    assert r.outcome == End()


def test_check_confirm_delete_loops_back_when_messages_remain():
    store = FakeStore(mail=[(6, "BB", "Second", "2026-07-16", "u6")])
    state = st("CHECK_MAIL", 2, unique_id="u5", mail_id=5, sender="AA", subject="Hi", content="x")
    r = MailFlow().advance("d", state, deps(store))
    assert "deleted" in r.replies[0]
    assert r.outcome == Stay({"command": "CHECK_MAIL", "step": 1,
                              "mail": [(6, "BB", "Second", "2026-07-16", "u6")]})


def test_check_confirm_keep_ends_when_mailbox_is_empty():
    state = st("CHECK_MAIL", 2, unique_id="u5", mail_id=5, sender="AA", subject="Hi", content="x")
    r = MailFlow().advance("k", state, deps())
    assert r.replies == ["The message has been kept in your inbox.✉️",
                         "You have no new messages."]
    assert r.outcome == End()


def test_check_confirm_reply_switches_to_mail_compose():
    state = st("CHECK_MAIL", 2, unique_id="u5", mail_id=5, sender="AA", subject="Hi", content="x")
    r = MailFlow().advance("r", state, deps())
    assert r.outcome.state["command"] == "MAIL"
    assert r.outcome.state["step"] == 7
    assert r.outcome.state["reply_to_mail_id"] == 5


# --- SM,, quick send -------------------------------------------------------

def test_quick_send_usage_on_bad_format():
    r = MailFlow().quick_send("sm,,foo", deps())
    assert "Send Mail Quick Command format" in r.replies[0]
    assert isinstance(r.outcome, Keep)


def test_quick_send_unknown_node():
    r = MailFlow().quick_send("sm,,zzz,,Subj,,Body", deps())
    assert r.replies == ["Node with short name 'zzz' not found."]
    assert isinstance(r.outcome, Keep)


def test_quick_send_ambiguous_short_name():
    lookup = FakeLookup(nodes={"bob": [Node("!b1", "BOB", "B1"),
                                       Node("!b2", "BOB", "B2")]})
    r = MailFlow().quick_send("sm,,bob,,Subj,,Body", deps(lookup=lookup))
    assert "Please be more specific" in r.replies[0]


def test_quick_send_delivers_and_notifies():
    store = FakeStore()
    lookup = FakeLookup(nodes={"bob": [Node("!bob", "BOB", "Bob Node")]},
                        names={"!bob": "Bob Node"}, shorts={"!me": "ME"})
    r = MailFlow().quick_send("sm,,bob,,Subj,,Body text", deps(store, lookup))
    assert store.added == [("!me", "ME", "!bob", "Subj", "Body text")]
    assert r.replies == ["Mail has been sent to Bob Node."]
    assert r.notifications[0][0] == "!bob"
    assert isinstance(r.outcome, Keep)


def test_quick_send_keeps_content_with_commas():
    store = FakeStore()
    lookup = FakeLookup(nodes={"bob": [Node("!bob", "BOB", "Bob")]},
                        names={"!bob": "Bob"}, shorts={"!me": "ME"})
    MailFlow().quick_send("sm,,bob,,Subj,,a,,b,,c", deps(store, lookup))
    assert store.added[0][4] == "a,,b,,c"     # only the first 3 separators split


# --- CM quick check --------------------------------------------------------

def test_quick_check_empty_mailbox():
    r = MailFlow().quick_check("cm", deps())
    assert r.replies == ["You have no new messages."]
    assert isinstance(r.outcome, Keep)


def test_quick_check_lists_and_awaits_a_number():
    store = FakeStore(mail=[(5, "AA", "Hello", "2026-07-08", "u5")])
    r = MailFlow().quick_check("cm", deps(store))
    assert "📬 You have the following messages:" in r.replies[0]
    assert "01. From: AA, Subject: Hello" in r.replies[0]
    assert r.outcome == Stay({"command": "CHECK_MAIL", "step": 1,
                            "mail": [(5, "AA", "Hello", "2026-07-08", "u5")]})


def test_quick_send_refuses_an_unidentified_sender():
    """SM,, used to store sender_short_name=None and tell the recipient
    'You have a new mail message from None.'"""
    store = FakeStore()
    lookup = FakeLookup(nodes={"bob": [Node("!bob", "BOB", "Bob Node")]},
                        names={"!bob": "Bob Node"}, shorts={})   # sender unknown
    r = MailFlow().quick_send("sm,,bob,,Subj,,Body", deps(store, lookup))
    assert r.replies == [UNKNOWN_NODE_REPLY]
    assert store.added == []
    assert r.notifications == []


def test_compose_refuses_an_unidentified_sender():
    store = FakeStore()
    lookup = FakeLookup(names={"!bob": "Bob Node"}, shorts={})   # sender unknown
    state = st("MAIL", 7, recipient_id="!bob", subject="Hi", content="body\n")
    r = MailFlow().advance("END", state, deps(store, lookup))
    assert r.replies == [UNKNOWN_NODE_REPLY]
    assert store.added == []
    assert r.outcome == End()


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
