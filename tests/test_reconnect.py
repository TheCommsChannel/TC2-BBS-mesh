"""Tests for reconnect.Supervisor — rebuilding a dead meshtastic interface.

No real sockets: FakeTransport stands in for Transport, and rebuild_interface
is a plain callable a test can make raise or succeed. Time is injected via
`now`, never slept for real.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reconnect import Supervisor
from fakes import FakeTransport

T0 = 1_000_000.0


class RebuildInterface:
    """A controllable rebuild_interface callable: fails until told to succeed,
    and counts every call."""

    def __init__(self):
        self.calls = 0
        self.should_fail = True
        self.next_interface = object()

    def __call__(self):
        self.calls += 1
        if self.should_fail:
            raise ConnectionRefusedError("radio unreachable")
        return self.next_interface


def sv(transport=None, rebuild=None, initial_backoff=5, max_backoff=60):
    transport = transport if transport is not None else FakeTransport(is_connected=False)
    rebuild = rebuild if rebuild is not None else RebuildInterface()
    return Supervisor(transport, rebuild,
                      initial_backoff=initial_backoff, max_backoff=max_backoff), transport, rebuild


# --- the healthy path is a cheap no-op --------------------------------------

def test_check_does_nothing_when_already_connected():
    transport = FakeTransport(is_connected=True)
    rebuild = RebuildInterface()
    supervisor, _, _ = sv(transport, rebuild)
    supervisor.check(now=T0)
    assert rebuild.calls == 0
    assert transport.reconnected_to == []


# --- backoff gating ----------------------------------------------------------

def test_check_does_nothing_before_the_backoff_delay_elapses():
    supervisor, transport, rebuild = sv(initial_backoff=5)
    supervisor.check(now=T0)          # first attempt, fails, schedules retry at T0+5
    assert rebuild.calls == 1
    supervisor.check(now=T0 + 4)      # too soon
    assert rebuild.calls == 1


def test_check_retries_once_the_backoff_delay_elapses():
    supervisor, transport, rebuild = sv(initial_backoff=5)
    supervisor.check(now=T0)          # fails, next attempt at T0+5
    assert rebuild.calls == 1
    supervisor.check(now=T0 + 5)      # elapsed
    assert rebuild.calls == 2


# --- failure backs off exponentially, capped --------------------------------

def test_failed_attempts_double_the_backoff_up_to_the_cap():
    supervisor, transport, rebuild = sv(initial_backoff=5, max_backoff=60)
    now = T0
    for _ in range(6):
        supervisor.check(now=now)
        now = supervisor._next_attempt_at   # jump straight to the next scheduled attempt
    # 5 -> 10 -> 20 -> 40 -> 60 -> 60 (capped)
    assert supervisor._backoff == 60


def test_a_failed_attempt_does_not_raise_out_of_check():
    supervisor, transport, rebuild = sv()
    supervisor.check(now=T0)          # must not raise
    assert transport.reconnected_to == []


# --- success ------------------------------------------------------------

def test_successful_reconnect_swaps_the_interface_and_resets_backoff():
    supervisor, transport, rebuild = sv(initial_backoff=5)
    supervisor.check(now=T0)                  # fails once, backoff -> 10
    rebuild.should_fail = False
    supervisor.check(now=T0 + 5)              # succeeds
    assert transport.reconnected_to == [rebuild.next_interface]
    assert supervisor._backoff == 5           # reset


# Closing the old interface on a successful reconnect is Transport's job, not
# Supervisor's — Supervisor never holds the raw interface at all (ADR-0003).
# See test_transport.py's test_reconnect_closes_the_old_interface and
# test_reconnect_swallows_a_failure_closing_the_old_interface.


# --- the pubsub event bypasses the backoff gate ------------------------------

def test_connection_lost_attempts_immediately_ignoring_backoff():
    supervisor, transport, rebuild = sv(initial_backoff=5)
    supervisor.check(now=T0)                  # fails, next attempt not until T0+5
    assert rebuild.calls == 1
    supervisor.on_connection_lost(interface=object())   # no backoff wait
    assert rebuild.calls == 2


def test_connection_lost_ignores_unexpected_pubsub_kwargs():
    supervisor, transport, rebuild = sv()
    supervisor.on_connection_lost(interface=object(), topic="whatever")  # must not raise
    assert rebuild.calls == 1


def test_connection_lost_accepts_an_injectable_now():
    """Same clock-injection seam as check(now=...), for tests that need to
    control time on this path too."""
    supervisor, transport, rebuild = sv(initial_backoff=5)
    supervisor.on_connection_lost(now=T0)
    assert rebuild.calls == 1
    supervisor.check(now=T0 + 4)              # too soon per the backoff set at T0
    assert rebuild.calls == 1


# --- re-entrancy: only one attempt in flight at a time ----------------------

def test_a_reconnect_already_in_progress_is_not_reattempted():
    supervisor, transport, rebuild = sv()
    supervisor._lock.acquire()                # simulate an attempt already in flight
    try:
        supervisor.check(now=T0)
        supervisor.on_connection_lost()
    finally:
        supervisor._lock.release()
    assert rebuild.calls == 0


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
