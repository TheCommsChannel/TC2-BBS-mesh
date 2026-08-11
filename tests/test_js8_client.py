"""Tests for the JS8Call bridge: message framing and the listener lifecycle.

Framing is pure. The lifecycle tests drive a real loopback socket, because the
bugs being guarded against — a listener that spins on EOF, dies on reset, or
blocks the caller forever — only exist against a real socket.
"""

import os
import sys

# Run from anywhere: put the repo root on the path before importing the modules
# under test. Keeps `python tests/test_x.py` working alongside pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import socket
import threading
import time

from js8_db import Js8Database
from settings import Js8Config
from js8call_integration import JS8CallClient, decode_messages
from fakes import FakeTransport


# --------------------------------------------------------------------------
# Framing (pure)
# --------------------------------------------------------------------------

def test_single_message():
    messages, rest = decode_messages(b'{"type":"RX.PING"}\n')
    assert messages == [{"type": "RX.PING"}]
    assert rest == b""


def test_two_messages_in_one_chunk():
    """The old code called json.loads on the whole chunk and dropped both."""
    buffer = b'{"type":"A"}\n{"type":"B"}\n'
    messages, rest = decode_messages(buffer)
    assert messages == [{"type": "A"}, {"type": "B"}]
    assert rest == b""


def test_message_split_across_chunks():
    messages, rest = decode_messages(b'{"type":"RX.DIR')
    assert messages == []
    assert rest == b'{"type":"RX.DIR'

    messages, rest = decode_messages(rest + b'ECTED"}\n')
    assert messages == [{"type": "RX.DIRECTED"}]
    assert rest == b""


def test_unparseable_line_is_skipped_not_fatal():
    messages, rest = decode_messages(b'garbage\n{"type":"B"}\n')
    assert messages == [{"type": "B"}]


def test_blank_lines_ignored():
    messages, _ = decode_messages(b'\n\n{"type":"A"}\n\n')
    assert messages == [{"type": "A"}]


def test_incomplete_trailing_message_is_held():
    messages, rest = decode_messages(b'{"type":"A"}\n{"type":"B"')
    assert messages == [{"type": "A"}]
    assert rest == b'{"type":"B"'


# --------------------------------------------------------------------------
# Lifecycle (real socket)
# --------------------------------------------------------------------------

class Js8Server:
    """A stand-in JS8Call instance on loopback."""

    def __init__(self):
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.address = self._sock.getsockname()
        self.conn = None
        self._accepted = threading.Event()
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        self.conn, _ = self._sock.accept()
        self._accepted.set()

    def wait(self, timeout=2):
        assert self._accepted.wait(timeout), "client never connected"

    def send(self, raw):
        self.conn.sendall(raw)

    def hang_up(self):
        self.conn.close()

    def stop(self):
        try:
            self._sock.close()
        except OSError:
            pass


def new_client(server, urgent=(), groups=()):
    host, port = server.address
    js8_config = Js8Config(host=host, port=port, db_path=":memory:",
                           groups=list(groups), urgent=list(urgent), store_messages=True)
    database = Js8Database(":memory:")
    database.create_tables()
    return JS8CallClient(FakeTransport(), js8_config, database)


def wait_until(predicate, timeout=2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_start_returns_immediately_and_listens():
    server = Js8Server()
    client = new_client(server, groups=["@NET"])
    started = time.time()
    client.start()
    assert time.time() - started < 0.5, "start() blocked the caller"
    server.wait()
    assert wait_until(lambda: client.connected)

    server.send(b'{"type":"RX.DIRECTED","value":"CALL1 @NET hello"}\n')
    assert wait_until(lambda: client.database.messages_for_group("@NET"))
    rows = client.database.messages_for_group("@NET")
    assert rows[0][0] == "CALL1"

    client.close()
    server.stop()


def test_two_messages_in_one_segment_are_both_stored():
    server = Js8Server()
    client = new_client(server, groups=["@NET"])
    client.start()
    server.wait()
    assert wait_until(lambda: client.connected)

    server.send(b'{"type":"RX.DIRECTED","value":"A @NET one"}\n'
                b'{"type":"RX.DIRECTED","value":"B @NET two"}\n')
    assert wait_until(lambda: len(client.database.messages_for_group("@NET")) == 2)

    client.close()
    server.stop()


def test_peer_hangup_stops_the_listener_without_spinning():
    """EOF used to spin a tight loop on Linux and raise ConnectionReset on Windows."""
    server = Js8Server()
    client = new_client(server)
    client.start()
    server.wait()
    assert wait_until(lambda: client.connected)

    server.hang_up()
    assert wait_until(lambda: not client._thread.is_alive(), timeout=3), \
        "listener kept running after the peer hung up"
    assert not client.connected

    client.close()
    server.stop()


def test_close_unblocks_and_joins_the_listener():
    server = Js8Server()
    client = new_client(server)
    client.start()
    server.wait()
    assert wait_until(lambda: client.connected)

    started = time.time()
    client.close()                       # must not hang waiting on recv()
    assert time.time() - started < 2.5
    assert not client._thread.is_alive()
    assert not client.connected
    server.stop()


def test_close_is_safe_when_never_started():
    client = JS8CallClient(FakeTransport(), Js8Config(), Js8Database(None))
    client.close()                       # must not raise


def test_start_does_nothing_when_unconfigured():
    client = JS8CallClient(FakeTransport(), Js8Config(), Js8Database(None))
    client.start()
    assert client._thread is None
    assert not client.connected


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
