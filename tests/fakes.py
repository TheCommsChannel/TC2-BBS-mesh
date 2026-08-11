"""Test doubles shared across the suite.

FakeTransport is the second adapter that justifies the Transport seam: it
records what would go out instead of transmitting it, and it does not sleep.
Nothing in the tests needs a fake meshtastic interface any more.
"""


class FakeTransport:
    def __init__(self, nodes=None, my_num=9999, is_connected=True):
        self.nodes = nodes if nodes is not None else {}
        self.my_num = my_num
        self.outbox = []          # list of (destination, text)
        self.closed = False
        self.is_connected = is_connected
        self.reconnected_to = []  # every interface passed to reconnect()

    def send(self, text, destination):
        self.outbox.append((destination, text))

    def close(self):
        self.closed = True

    def reconnect(self, new_interface):
        self.is_connected = True
        self.reconnected_to.append(new_interface)

    # --- helpers for assertions -------------------------------------------

    def sent_to(self, destination):
        return [text for dest, text in self.outbox if dest == destination]

    def clear(self):
        self.outbox.clear()


def make_node(num, short, long_name, hw="TBEAM", role="CLIENT",
              last_heard=None, battery=80):
    """A row of the meshtastic node roster."""
    return {
        "num": num,
        "user": {"shortName": short, "longName": long_name,
                 "hwModel": hw, "role": role},
        "lastHeard": last_heard,
        "deviceMetrics": {"batteryLevel": battery},
    }
