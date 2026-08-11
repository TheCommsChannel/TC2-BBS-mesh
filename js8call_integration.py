"""The JS8Call bridge: listens to a JS8Call instance and stores what it hears.

The client owns its own thread. `start()` returns immediately; `close()` stops
the listener and waits for it. Callers never see a socket or a thread.

Browsing what it stored is Js8Flow's job. Writes go through the shared
Js8Database, so the writer and the reader cannot point at different files.
"""

from socket import socket, AF_INET, SOCK_STREAM, SHUT_RDWR
import json
import threading
import time
import logging

from meshtastic import BROADCAST_NUM

#: How long close() waits for the listener to notice and stop.
_JOIN_TIMEOUT = 2.0


def to_message(typ, value='', params=None):
    if params is None:
        params = {}
    return json.dumps({'type': typ, 'value': value, 'params': params})


def decode_messages(buffer, logger=None):
    """Split a byte buffer into complete JS8Call messages.

    JS8Call speaks newline-delimited JSON. A single recv() may carry several
    messages, or half of one. Returns the messages that are complete and the
    bytes left over for the next read.

    The previous implementation called json.loads on whatever one recv()
    returned and dropped everything on a parse error, so two messages arriving
    in one TCP segment were both lost silently.
    """
    logger = logger or logging.getLogger('js8call')
    messages = []
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            logger.warning(f"Discarding unparseable JS8Call message: {line[:80]!r}")
            continue
        if message:
            messages.append(message)
    return messages, buffer


class JS8CallClient:
    def __init__(self, transport, js8_config, js8_database, logger=None):
        self.logger = logger or logging.getLogger('js8call')
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        self.server = (js8_config.host, js8_config.port)
        self.js8groups = list(js8_config.groups)
        self.js8urgent = list(js8_config.urgent)
        self.store_messages = js8_config.store_messages

        self.connected = False
        self.sock = None
        self.transport = transport
        self.database = js8_database
        self._thread = None

        if self.database.configured:
            self.database.create_tables()
            self.logger.info("JS8Call database tables created or verified.")
        else:
            self.logger.info("JS8Call configuration not found. Skipping JS8Call integration.")

    # --- lifecycle --------------------------------------------------------

    def start(self):
        """Listen in the background. Returns immediately.

        Does nothing when the bridge is not configured, so the caller does not
        have to know what "configured" means.
        """
        if not self.database.configured:
            return
        if not self.server[0] or not self.server[1]:
            self.logger.info("JS8Call server configuration not found. Skipping JS8Call connection.")
            return
        self._thread = threading.Thread(target=self._run, name='js8call', daemon=True)
        self._thread.start()

    def close(self):
        """Stop listening and wait for the listener to finish."""
        self.connected = False
        sock, self.sock = self.sock, None
        if sock is not None:
            try:
                sock.shutdown(SHUT_RDWR)   # unblocks a listener parked in recv()
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=_JOIN_TIMEOUT)

    # --- the listener -----------------------------------------------------

    def _run(self):
        try:
            self._listen()
        except ConnectionRefusedError:
            self.logger.error(f"Connection to JS8Call server {self.server} refused.")
        except OSError as error:
            self.logger.error(f"JS8Call connection lost: {error}")
        finally:
            self.connected = False
            sock, self.sock = self.sock, None
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass

    def _listen(self):
        self.logger.info(f"Connecting to {self.server}")
        self.sock = socket(AF_INET, SOCK_STREAM)
        self.sock.connect(self.server)
        self.connected = True
        self.send("STATION.GET_STATUS")

        buffer = b""
        while self.connected:
            try:
                chunk = self.sock.recv(65500)
            except OSError:
                # Either the peer reset us, or close() shut the socket down.
                break
            if not chunk:
                self.logger.info("JS8Call server closed the connection.")
                break

            buffer += chunk
            messages, buffer = decode_messages(buffer, self.logger)
            for message in messages:
                self.process(message)

        # A final message may arrive without its trailing newline.
        if buffer.strip():
            messages, _ = decode_messages(buffer + b"\n", self.logger)
            for message in messages:
                self.process(message)

    def send(self, *args, **kwargs):
        params = kwargs.get('params', {})
        if '_ID' not in params:
            params['_ID'] = '{}'.format(int(time.time() * 1000))
            kwargs['params'] = params
        message = to_message(*args, **kwargs)
        self.sock.send((message + '\n').encode('utf-8'))

    # --- what it heard ----------------------------------------------------

    def process(self, message):
        typ = message.get('type', '')
        value = message.get('value', '')

        if not typ:
            return

        rx_types = [
            'RX.ACTIVITY', 'RX.DIRECTED', 'RX.SPOT', 'RX.CALL_ACTIVITY',
            'RX.CALL_SELECTED', 'RX.DIRECTED_ME', 'RX.ECHO', 'RX.DIRECTED_GROUP',
            'RX.META', 'RX.MSG', 'RX.PING', 'RX.PONG', 'RX.STREAM'
        ]

        if typ not in rx_types:
            return

        if typ == 'RX.DIRECTED' and value:
            parts = value.split(' ')
            if len(parts) < 3:
                self.logger.warning(f"Unexpected message format: {value}")
                return

            sender = parts[0]
            receiver = parts[1]
            msg = ' '.join(parts[2:]).strip()

            self.logger.info(f"Received JS8Call message: {sender} to {receiver} - {msg}")

            if receiver in self.js8urgent:
                self.database.insert('urgent', sender, receiver, msg)
                notification_message = (f"💥 URGENT JS8Call Message Received 💥\n"
                                        f"From: {sender}\nCheck BBS for message")
                self.transport.send(notification_message, BROADCAST_NUM)
            elif receiver in self.js8groups:
                self.database.insert('groups', sender, receiver, msg)
            elif self.store_messages:
                self.database.insert('messages', sender, receiver, msg)
