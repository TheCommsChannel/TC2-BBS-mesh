"""Characterization tests for the current conversation behaviour.

These lock the observable behaviour of the BBS *before* the Session/flows
refactor, so the migration can be proven behaviour-preserving.

They drive the real ``message_processing.process_message`` through a fake
meshtastic interface and capture what the BBS sends back. The harness's
``Session.advance(message) -> [replies]`` is deliberately shaped like the
future ``session.advance(node, message)`` seam: when the real Session lands,
it drops in behind this same contract and these tests should stay green.

Pure and fast — no radio, no real database, no 2-second pacing. Runs under
pytest, or standalone (``python test_characterization.py``).
"""

import os
import sys

# Run from anywhere: put the repo root on the path before importing the modules
# under test. Keeps `python tests/test_x.py` working alongside pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import message_processing
from settings import Config, Menus
from database import Database
from js8_db import Js8Database
from runtime import Runtime
from session import Session as RealSession
from fakes import FakeTransport, make_node

MENUS = Menus(main=["Q", "B", "U", "X"],
              bbs=["M", "B", "C", "J", "X"],
              utilities=["S", "F", "W", "X"])


def _config(bbs_nodes=(), allowed_nodes=()):
    """The config the router reads, built as a value. No file is opened."""
    return Config(menus=MENUS, fortunes=["Stay curious"],
                  bbs_nodes=list(bbs_nodes), allowed_nodes=list(allowed_nodes))


# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------

class Session:
    """Thin shim over process_message, shaped like the Session seam."""

    def __init__(self, transport, runtime, node_num):
        self.transport = transport
        self.runtime = runtime
        self.db = runtime.database
        self.node = node_num

    def advance(self, message):
        """Feed one inbound message, return the replies sent to this node."""
        self.transport.clear()
        message_processing.process_message(self.node, message, self.transport, self.runtime)
        return self.transport.sent_to(self.node)

    def broadcasts(self):
        """Text sent to anywhere other than this node (e.g. mesh broadcast)."""
        return [text for dest, text in self.transport.outbox if dest != self.node]

    def sync(self, message):
        """Feed one inbound sync message from a peer BBS Node."""
        self.transport.clear()
        message_processing.process_message(self.node, message, self.transport, self.runtime,
                                           is_sync_message=True)
        return list(self.transport.outbox)


SENDER_NUM = 1001
SENDER_ID = "!sender"


def new_session(allowed_nodes=(), bbs_nodes=(), extra_nodes=None):
    """Fresh conversation: a fresh Session, in-memory stores, config as a value.

    Every test builds its own Runtime — including its own Session, which owns
    the conversation state — so nothing leaks between tests through a module
    global.
    """
    database = Database(":memory:")
    database.initialize_schema()
    runtime = Runtime(config=_config(bbs_nodes=bbs_nodes, allowed_nodes=allowed_nodes),
                      database=database, js8_database=Js8Database(None),
                      session=RealSession())

    nodes = {SENDER_ID: make_node(SENDER_NUM, "SEND", "Sender Node")}
    if extra_nodes:
        nodes.update(extra_nodes)
    return Session(FakeTransport(nodes, my_num=9999), runtime, SENDER_NUM)


def joined(replies):
    return "\n".join(replies)


# --------------------------------------------------------------------------
# Navigation
# --------------------------------------------------------------------------

def test_unknown_message_shows_main_menu():
    s = new_session()
    r = joined(s.advance("hello"))
    assert "💾TC² BBS💾" in r
    assert "[B]BS" in r


def test_main_menu_shows_empty_mail_count():
    s = new_session()
    r = joined(s.advance("hello"))
    assert "✉️:0" in r


def test_enter_bbs_menu():
    s = new_session()
    r = joined(s.advance("b"))
    assert "📰BBS Menu📰" in r
    assert "[M]ail" in r


def test_enter_utilities_menu():
    s = new_session()
    r = joined(s.advance("u"))
    assert "🛠️Utilities Menu🛠️" in r


def test_quick_help_leaf():
    s = new_session()
    r = joined(s.advance("q"))
    assert "QUICK COMMANDS" in r


def test_fortune_leaf():
    s = new_session()
    s.advance("u")
    r = joined(s.advance("f"))
    assert "Stay curious" in r


def test_wall_of_shame_leaf():
    s = new_session(extra_nodes={"!flat": make_node(3003, "FLAT", "Flat Node", battery=5)})
    s.advance("u")
    r = joined(s.advance("w"))
    assert "Flat Node - Battery 5%" in r


def test_exit_from_deep_inside_a_flow_returns_to_main():
    s = new_session()
    s.advance("b")            # bbs menu
    s.advance("b")            # bulletin menu
    s.advance("g")            # inside General board
    r = joined(s.advance("x"))
    assert "💾TC² BBS💾" in r


def test_bbs_menu_enters_mail_flow():
    s = new_session()
    s.advance("b")
    r = joined(s.advance("m"))
    assert "✉️Mail Menu✉️" in r


def test_bbs_menu_enters_js8call():
    s = new_session()
    s.advance("b")
    r = joined(s.advance("j"))
    assert "JS8Call Menu" in r


def test_js8call_reads_answer_gracefully_when_unconfigured():
    """Browsing an unconfigured JS8Call bridge reads as empty, not as a crash.

    The old handlers opened js8call.db directly and let sqlite raise
    OperationalError at the user when the tables did not exist.
    """
    s = new_session()
    s.advance("b")
    s.advance("j")
    assert "No group messages available." in joined(s.advance("g"))
    assert "No station messages available." in joined(s.advance("s"))
    assert "No urgent messages available." in joined(s.advance("u"))


# --------------------------------------------------------------------------
# Mail
# --------------------------------------------------------------------------

def test_mail_menu_then_read_empty_inbox():
    s = new_session()
    s.advance("b")
    r = joined(s.advance("m"))
    assert "✉️Mail Menu✉️" in r

    r = joined(s.advance("r"))
    assert "no messages in your mailbox" in r


def test_mail_send_to_unknown_short_name():
    s = new_session()
    s.advance("b")
    s.advance("m")
    r = joined(s.advance("s"))
    assert "Short Name" in r

    r = joined(s.advance("zzz"))
    assert "unable to find that node" in r


def test_quick_send_mail_rejects_bad_format():
    s = new_session()
    r = joined(s.advance("sm,,foo"))
    assert "Send Mail Quick Command format" in r


def test_send_mail_end_to_end_persists_and_notifies():
    s = new_session(extra_nodes={"!bob": make_node(2002, "BOB", "Bob Node")})
    s.advance("b")            # bbs menu
    s.advance("m")            # mail menu
    s.advance("s")            # send
    r = joined(s.advance("bob"))          # resolve recipient
    assert "message to Bob Node" in r

    s.advance("Greetings")    # subject
    s.advance("Body line")    # content
    r = joined(s.advance("END"))
    assert "posted to the mailbox of Bob Node" in r

    # Recipient gets the out-of-band nudge, and the mail is stored for them.
    assert "new mail message from SEND" in joined(s.broadcasts())
    assert len(s.db.get_mail("!bob")) == 1


# --------------------------------------------------------------------------
# Stats
# --------------------------------------------------------------------------

def test_stats_node_count():
    s = new_session()
    s.advance("u")
    r = joined(s.advance("s"))
    assert "📊Stats Menu📊" in r

    r = joined(s.advance("n"))
    assert "Total nodes seen:" in r
    assert "All time: 1" in r


# --------------------------------------------------------------------------
# Bulletins (these exercise Board's territory)
# --------------------------------------------------------------------------

def test_quick_check_bulletin_empty_board():
    s = new_session()
    r = joined(s.advance("cb,,General"))
    assert "No bulletins available on General board" in r


def test_quick_check_bulletin_unknown_board():
    """Used to answer 'Error processing check bulletin command.' via StopIteration."""
    s = new_session()
    r = joined(s.advance("cb,,Sports"))
    assert "Unknown board 'Sports'" in r


def test_quick_post_bulletin_to_urgent_respects_allow_list():
    """PB,,Urgent used to bypass the allow-list and broadcast to the whole mesh."""
    s = new_session(allowed_nodes=["!someone_else"])
    r = joined(s.advance("pb,,Urgent,,Fake alert,,ignore me"))
    assert "don't have permission" in r
    assert s.db.get_bulletins("Urgent") == []
    assert [t for _, t in s.transport.outbox if "NEW URGENT BULLETIN" in t] == []


def test_quick_post_bulletin_to_general_persists():
    s = new_session()
    r = joined(s.advance("pb,,general,,Subj,,Body"))
    assert "posted to General" in r
    assert len(s.db.get_bulletins("General")) == 1


def test_quick_post_channel_actually_works():
    """CHP,, split on '|' while its usage promised ',,' — it never succeeded."""
    s = new_session()
    r = joined(s.advance("chp,,MyNet,,https://example/x"))
    assert "has been added to the directory" in r
    assert s.db.get_channels() == [("MyNet", "https://example/x")]


def test_quick_command_leaves_the_conversation_where_it_was():
    s = new_session()
    s.advance("b")            # bbs menu
    s.advance("m")            # mail menu -> MAIL step 1
    s.advance("chl")          # a quick command, mid-flow
    # Still in the mail menu: 'r' reads the mailbox rather than reopening a menu.
    assert "no messages in your mailbox" in joined(s.advance("r"))


def test_post_bulletin_to_general_persists():
    s = new_session()
    s.advance("b")            # bbs menu
    s.advance("b")            # bulletin menu
    r = joined(s.advance("g"))            # General board
    assert "General has 0 messages" in r

    assert "subject" in joined(s.advance("p")).lower()
    assert "contents" in joined(s.advance("My Subject")).lower()
    s.advance("Body line one")            # accumulates, no reply
    r = joined(s.advance("END"))
    assert "posted to General" in r

    assert len(s.db.get_bulletins("General")) == 1


def test_bulletin_body_keeps_leading_whitespace():
    """A content-capture step stores the message verbatim. The routing layer
    must not strip the text before the flow sees it."""
    s = new_session()
    s.advance("b")
    s.advance("b")
    s.advance("g")            # General board
    s.advance("p")            # post
    s.advance("Subj")         # subject
    s.advance("    indented line")   # leading spaces must survive
    s.advance("END")

    bulletin_id = s.db.get_bulletins("General")[0][0]
    content = s.db.get_bulletin_content(bulletin_id)[3]
    assert content == "    indented line\n"


def test_urgent_post_denied_without_permission():
    s = new_session(allowed_nodes=["!someone_else"])
    s.advance("b")            # bbs menu
    s.advance("b")            # bulletin menu
    r = joined(s.advance("u"))            # Urgent board
    assert "Urgent has 0 messages" in r

    r = joined(s.advance("p"))
    assert "don't have permission" in r


def test_urgent_post_allowed_broadcasts():
    s = new_session(allowed_nodes=[SENDER_ID])
    s.advance("b")
    s.advance("b")
    s.advance("u")
    s.advance("p")            # permitted
    s.advance("Flash Flood")  # subject
    s.advance("Move to high ground")  # content
    s.advance("END")          # posts + broadcasts

    broadcast = joined(s.broadcasts())
    assert "NEW URGENT BULLETIN" in broadcast
    assert len(s.db.get_bulletins("Urgent")) == 1


# --------------------------------------------------------------------------
# Channel directory
# --------------------------------------------------------------------------

def test_channel_directory_view_empty():
    s = new_session()
    s.advance("b")            # bbs menu
    r = joined(s.advance("c"))
    assert "CHANNEL DIRECTORY" in r

    r = joined(s.advance("v"))
    assert "No channels available" in r


def test_channel_posted_via_menu_now_syncs_to_peers():
    """Adding a Channel replicates regardless of entry point.

    Previously only the CHP,, quick command synced; the menu path did not.
    """
    s = new_session(bbs_nodes=["!peer"])
    s.advance("b")
    s.advance("c")
    s.advance("p")            # post
    s.advance("MyNet")        # name
    r = joined(s.advance("https://example/x"))
    assert "has been added to the directory" in r

    assert s.transport.sent_to("!peer") == ["CHANNEL|MyNet|https://example/x"]
    assert s.db.get_channels() == [("MyNet", "https://example/x")]


def test_synced_channel_is_stored_not_answered():
    """An inbound CHANNEL| from a peer is ingested, not treated as conversation."""
    s = new_session()
    s.sync("CHANNEL|PeerNet|https://peer/x")
    assert s.db.get_channels() == [("PeerNet", "https://peer/x")]
    assert s.transport.outbox == []


# --------------------------------------------------------------------------
# Authorship: a Node the BBS cannot name may not author a record
# --------------------------------------------------------------------------

def unknown_sender_session(bbs_nodes=()):
    """A Node that is not in the roster -- the BBS has never heard its nodedb."""
    s = new_session(bbs_nodes=bbs_nodes)
    s.transport.nodes.clear()
    return s


def test_quick_post_by_an_unknown_node_is_refused_and_not_replicated():
    """It used to store BULLETIN|General|None|... and sync that to every peer."""
    s = unknown_sender_session(bbs_nodes=["!peer"])
    r = joined(s.advance("pb,,General,,Fake,,body"))
    assert "Unable to retrieve your node information" in r
    assert s.db.get_bulletins("General") == []
    assert s.transport.sent_to("!peer") == []


def test_quick_send_mail_by_an_unknown_node_is_refused():
    """It used to tell the recipient 'a new mail message from None'."""
    s = new_session(bbs_nodes=["!peer"],
                    extra_nodes={"!bob": make_node(2002, "BOB", "Bob Node")})
    del s.transport.nodes[SENDER_ID]          # the sender, not the recipient
    r = joined(s.advance("sm,,bob,,Subj,,Body"))
    assert "Unable to retrieve your node information" in r
    assert s.db.get_mail("!bob") == []
    assert s.transport.sent_to("!peer") == []
    assert s.transport.sent_to("!bob") == []


def test_an_unknown_node_can_still_read_the_menus():
    """Refusing authorship is not refusing the conversation."""
    s = unknown_sender_session()
    assert "TC² BBS" in joined(s.advance("hello"))
    assert "No bulletins available on General board" in joined(s.advance("cb,,General"))


# --------------------------------------------------------------------------
# Sync (replication from a peer BBS Node)
# --------------------------------------------------------------------------

def test_synced_urgent_bulletin_broadcasts_once():
    """An Urgent Bulletin arriving from a peer notifies the mesh exactly once.

    Before the store/replication split this fired twice: add_bulletin
    broadcast, and the sync branch broadcast again.
    """
    s = new_session()
    s.sync("BULLETIN|Urgent|AA|Flood|Move now|uid-1")

    urgent = [t for _, t in s.transport.outbox if "NEW URGENT BULLETIN" in t]
    assert len(urgent) == 1, f"expected 1 broadcast, got {len(urgent)}"
    assert len(s.db.get_bulletins("Urgent")) == 1


def test_synced_general_bulletin_does_not_broadcast():
    s = new_session()
    s.sync("BULLETIN|General|AA|Hello|Body|uid-2")

    assert [t for _, t in s.transport.outbox if "NEW URGENT BULLETIN" in t] == []
    assert len(s.db.get_bulletins("General")) == 1


def test_synced_bulletin_is_not_resynced_to_peers():
    s = new_session(bbs_nodes=["!peer"])
    s.sync("BULLETIN|General|AA|Hello|Body|uid-3")

    to_peer = s.transport.sent_to("!peer")
    assert to_peer == [], f"synced bulletin was echoed back to peers: {to_peer}"


def test_synced_mail_is_stored():
    s = new_session()
    s.sync("MAIL|!bob|BOB|!me|Subject|Body|uid-4")
    assert len(s.db.get_mail("!me")) == 1


def test_synced_bulletin_deletion_removes_it():
    """A replicated deletion matches on unique_id.

    Previously delete_bulletin matched on the local autoincrement id while the
    sync path passed a unique_id, so the row was never removed.
    """
    s = new_session()
    s.sync("BULLETIN|General|AA|Hello|Body|uid-5")
    assert len(s.db.get_bulletins("General")) == 1

    s.sync("DELETE_BULLETIN|uid-5")
    assert s.db.get_bulletins("General") == []


def test_synced_mail_deletion_removes_it():
    s = new_session()
    s.sync("MAIL|!bob|BOB|!me|Subject|Body|uid-6")
    s.sync("DELETE_MAIL|uid-6")
    assert s.db.get_mail("!me") == []


def test_unknown_sync_message_is_ignored():
    s = new_session()
    s.sync("GARBAGE|whatever")
    assert s.transport.outbox == []


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
