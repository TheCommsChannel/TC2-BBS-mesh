"""Transport — the seam under the radio.

Callers say `send(text, destination)`. Splitting a long reply into payload-sized
chunks, pacing them so the mesh keeps up, and logging what went out all happen
behind that. Nobody outside this module holds the meshtastic interface.

Two adapters justify the seam: MeshtasticTransport in production, and the
FakeTransport the tests use — which records instead of transmitting, and does
not sleep.
"""

import logging
import time

from meshtastic import BROADCAST_NUM

import roster

#: Meshtastic will not carry more than this in one text payload.
MAX_PAYLOAD = 200

#: Wait between chunks so a long reply does not swamp the mesh.
PACING_SECONDS = 4


def chunks(text, size=MAX_PAYLOAD):
    """Split a reply into payload-sized pieces. An empty reply sends nothing."""
    return [text[i:i + size] for i in range(0, len(text), size)]


class MeshtasticTransport:
    def __init__(self, interface, pacing_seconds=PACING_SECONDS):
        self._interface = interface
        self._pacing_seconds = pacing_seconds

    @property
    def nodes(self):
        """The live node roster. Meshtastic keeps this up to date for us."""
        return self._interface.nodes

    @property
    def my_num(self):
        return self._interface.myInfo.my_node_num

    @property
    def is_connected(self):
        """Live off the interface, same as nodes/my_num — reconnect.Supervisor
        polls this to notice a dead connection the library's own
        "connection.lost" event didn't fire for (e.g. a heartbeat-thread
        crash bypasses it)."""
        return self._interface.isConnected.is_set()

    def reconnect(self, new_interface):
        """Swap in a freshly rebuilt interface, closing the old one first
        (best effort — it may already be half-dead). In place, not a new
        Transport, so every existing holder of this object (JS8CallClient,
        the idle loop's persistent `transport`) sees the new interface for
        free, and the raw interface never has to leave this module (ADR-0003)
        for reconnect.Supervisor to swap it."""
        try:
            self._interface.close()
        except Exception:
            pass
        self._interface = new_interface

    def send(self, text, destination):
        for chunk in chunks(text):
            try:
                packet = self._interface.sendText(
                    text=chunk,
                    destinationId=destination,
                    wantAck=True,
                    wantResponse=False,
                )
            except Exception as error:
                # The old handler read `e.message`, which does not exist in
                # Python 3, so a transient send failure raised AttributeError
                # out of the except clause and killed the caller.
                logging.warning(f"Send to {destination} failed: {error}")
            else:
                self._log_sent(chunk, destination, packet)
            time.sleep(self._pacing_seconds)

    def close(self):
        self._interface.close()

    def _log_sent(self, chunk, destination, packet):
        # destination arrives in whatever shape the caller already had it in:
        # a node num for a direct reply (Session addresses by the sender's
        # num), a node id string for a notification or a peer-sync send (both
        # already have the id, not a num), or the broadcast sentinel for an
        # urgent bulletin. id_from_num only resolves the first shape.
        if destination == BROADCAST_NUM:
            node_id, name = "broadcast", "Broadcast"
        else:
            node_id = destination if isinstance(destination, str) \
                else roster.id_from_num(self.nodes, destination)
            name = roster.short_name(self.nodes, node_id)
        shown = chunk.replace('\n', '\\n')
        logging.info(f"Sending message to user '{name}' ({node_id}) "
                     f"with sendID {packet.id}: \"{shown}\"")
