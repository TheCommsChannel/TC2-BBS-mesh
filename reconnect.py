"""Reconnect — rebuilding a dead meshtastic interface.

Nothing in this repo retried a dropped TCP or serial connection before this;
the interface was built once in server.main() and never touched again, so a
broken socket or an unplugged cable left the BBS silently unable to send or
receive until someone restarted the process by hand.

Supervisor watches one Transport and rebuilds its interface when it dies,
retrying with a capped exponential backoff, forever — this runs unattended in
the field, nobody is watching to restart it. Two triggers feed the same retry
path: meshtastic's own "connection.lost" pubsub event (fired when its reader
thread dies from an OSError) and a polled check() driven by the caller's idle
loop (which catches failure modes the event misses — a heartbeat-thread crash
never calls the library's _disconnected(), so the event never fires for it).

Supervisor never holds the raw interface itself — only Transport may (see
ADR-0003) — it asks Transport for is_connected and hands a freshly rebuilt
interface to Transport.reconnect(), which owns closing the old one.
"""

import logging
import threading
import time

#: First retry delay in seconds; doubles after each failed attempt.
INITIAL_BACKOFF_SECONDS = 5

#: Cap on the retry delay — never wait longer than this between attempts.
MAX_BACKOFF_SECONDS = 60


class Supervisor:
    def __init__(self, transport, rebuild_interface,
                initial_backoff=INITIAL_BACKOFF_SECONDS, max_backoff=MAX_BACKOFF_SECONDS):
        self._transport = transport
        self._rebuild_interface = rebuild_interface
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._backoff = initial_backoff
        self._next_attempt_at = 0
        self._lock = threading.Lock()

    def on_connection_lost(self, now=None, **kwargs):
        """The meshtastic pubsub callback for "connection.lost" (called with
        interface=... and whatever else that topic carries — accepted and
        ignored via **kwargs). Attempts a reconnect right away, ignoring the
        backoff gate check() applies — the connection just died, there's no
        reason to wait for the next scheduled retry."""
        self._try_reconnect(now if now is not None else time.time())

    def check(self, now=None):
        """Call once per tick from the caller's idle loop. A no-op whenever
        the connection is healthy; otherwise attempts a reconnect only once
        the backoff delay has elapsed."""
        now = now if now is not None else time.time()
        if self._transport.is_connected:
            self._backoff = self._initial_backoff
            return
        if now < self._next_attempt_at:
            return
        self._try_reconnect(now)

    def _try_reconnect(self, now):
        if not self._lock.acquire(blocking=False):
            return   # an attempt is already in flight — let it finish
        try:
            if self._transport.is_connected:
                return   # recovered between the gate check and the lock
            logging.warning("Meshtastic interface down, attempting to reconnect...")
            try:
                new_interface = self._rebuild_interface()
            except Exception as error:
                logging.warning(f"Reconnect attempt failed: {error}")
                self._next_attempt_at = now + self._backoff
                self._backoff = min(self._backoff * 2, self._max_backoff)
                return
            self._transport.reconnect(new_interface)
            self._backoff = self._initial_backoff
            logging.info("Meshtastic interface reconnected.")
        finally:
            self._lock.release()
