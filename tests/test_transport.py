"""Tests for the Transport seam: chunking, pacing, and failure handling."""

import os
import sys

# Run from anywhere: put the repo root on the path before importing the modules
# under test. Keeps `python tests/test_x.py` working alongside pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import threading
import types

import transport
from transport import MAX_PAYLOAD, MeshtasticTransport, chunks


class FakeInterface:
    """Stands in for the meshtastic interface. Only Transport ever sees one."""

    def __init__(self, nodes=None, my_num=7, fail_with=None, connected=True):
        self.nodes = nodes or {}
        self.myInfo = types.SimpleNamespace(my_node_num=my_num)
        self.sent = []
        self.closed = False
        self._fail_with = fail_with
        self._packet_id = 0
        self.isConnected = threading.Event()
        if connected:
            self.isConnected.set()

    def sendText(self, text, destinationId, wantAck=True, wantResponse=False):
        if self._fail_with is not None:
            raise self._fail_with
        self.sent.append((destinationId, text))
        self._packet_id += 1
        return types.SimpleNamespace(id=self._packet_id)

    def close(self):
        self.closed = True


def no_pacing(interface):
    return MeshtasticTransport(interface, pacing_seconds=0)


# --- chunking (pure) -------------------------------------------------------

def test_short_text_is_one_chunk():
    assert chunks("hello") == ["hello"]


def test_long_text_is_split_at_the_payload_limit():
    text = "x" * (MAX_PAYLOAD + 5)
    pieces = chunks(text)
    assert len(pieces) == 2
    assert len(pieces[0]) == MAX_PAYLOAD
    assert len(pieces[1]) == 5
    assert "".join(pieces) == text


def test_empty_text_sends_nothing():
    assert chunks("") == []


# --- sending ---------------------------------------------------------------

def test_send_delivers_one_chunk():
    interface = FakeInterface()
    no_pacing(interface).send("hello", 42)
    assert interface.sent == [(42, "hello")]


def test_send_splits_a_long_reply():
    interface = FakeInterface()
    no_pacing(interface).send("y" * (MAX_PAYLOAD + 1), 42)
    assert len(interface.sent) == 2
    assert interface.sent[0][0] == 42


def test_send_paces_between_chunks():
    interface = FakeInterface()
    slept = []
    original = transport.time.sleep
    transport.time.sleep = lambda seconds: slept.append(seconds)
    try:
        MeshtasticTransport(interface, pacing_seconds=2).send("z" * (MAX_PAYLOAD + 1), 42)
    finally:
        transport.time.sleep = original
    assert slept == [2, 2]


def test_a_failed_send_is_logged_not_raised():
    """The old handler read `e.message`, raising AttributeError from the except."""
    interface = FakeInterface(fail_with=OSError("radio busy"))
    no_pacing(interface).send("hello", 42)      # must not raise
    assert interface.sent == []


def test_a_failed_chunk_does_not_stop_the_rest():
    interface = FakeInterface(fail_with=OSError("radio busy"))
    logging.disable(logging.CRITICAL)
    try:
        no_pacing(interface).send("q" * (MAX_PAYLOAD + 1), 42)
    finally:
        logging.disable(logging.NOTSET)
    assert interface.sent == []                 # both failed, neither raised


# --- logging what was sent, for every destination shape send() accepts -----

def _capture_log(fn):
    """Run fn(), returning every message passed to logging.info."""
    logged = []
    original = transport.logging.info
    transport.logging.info = lambda msg: logged.append(msg)
    try:
        fn()
    finally:
        transport.logging.info = original
    return logged


def test_log_resolves_a_numeric_destination_by_num():
    """A direct reply: Session.advance addresses it by the sender's node num."""
    interface = FakeInterface(nodes={"!bob": {"num": 5, "user": {"shortName": "BOB"}}})
    logged = _capture_log(lambda: no_pacing(interface).send("hi", 5))
    assert logged and "'BOB'" in logged[0] and "(!bob)" in logged[0]


def test_log_resolves_a_string_node_id_destination_directly():
    """A notification or a peer-sync send: both address by node id string
    already, not a num — id_from_num can never match a string against a
    numeric 'num' field, so this used to always log 'None' (None)."""
    interface = FakeInterface(nodes={"!bob": {"num": 5, "user": {"shortName": "BOB"}}})
    logged = _capture_log(lambda: no_pacing(interface).send("hi", "!bob"))
    assert logged and "'BOB'" in logged[0] and "(!bob)" in logged[0]


def test_log_shows_broadcast_for_the_broadcast_destination():
    interface = FakeInterface()
    logged = _capture_log(lambda: no_pacing(interface).send("hi", transport.BROADCAST_NUM))
    assert logged and "Broadcast" in logged[0]


# --- the rest of the seam --------------------------------------------------

def test_nodes_are_read_live_from_the_interface():
    interface = FakeInterface(nodes={"!a": {"num": 1}})
    t = no_pacing(interface)
    assert t.nodes == {"!a": {"num": 1}}
    interface.nodes["!b"] = {"num": 2}
    assert "!b" in t.nodes


def test_my_num_comes_from_my_info():
    assert no_pacing(FakeInterface(my_num=1234)).my_num == 1234


def test_close_closes_the_interface():
    interface = FakeInterface()
    no_pacing(interface).close()
    assert interface.closed


def test_is_connected_reads_live_from_the_interface():
    interface = FakeInterface(connected=False)
    t = no_pacing(interface)
    assert t.is_connected is False
    interface.isConnected.set()
    assert t.is_connected is True


def test_reconnect_swaps_the_interface_in_place():
    original = FakeInterface(my_num=1)
    replacement = FakeInterface(my_num=2)
    t = no_pacing(original)
    t.reconnect(replacement)
    assert t.my_num == 2
    t.send("hi", 42)
    assert replacement.sent == [(42, "hi")]
    assert original.sent == []


def test_reconnect_closes_the_old_interface():
    original = FakeInterface()
    t = no_pacing(original)
    t.reconnect(FakeInterface())
    assert original.closed


def test_reconnect_swallows_a_failure_closing_the_old_interface():
    class DeadInterface:
        def close(self):
            raise OSError("already gone")

    t = MeshtasticTransport(DeadInterface(), pacing_seconds=0)
    replacement = FakeInterface()
    t.reconnect(replacement)      # must not raise
    assert t.my_num == replacement.myInfo.my_node_num


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
