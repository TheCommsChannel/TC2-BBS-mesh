"""The router: decides whether an inbound message is replication or conversation,
hands conversation to the Session, and does the sending.

It talks to a Transport, never to the meshtastic interface. `on_receive` is the
one place that wraps the interface pubsub hands us.
"""

import logging

from flows.base import Deps
from adapters import Store, Lookup
from events import Origin
from replication import Replication
from transport import MeshtasticTransport
import replication
import roster


def _build_deps(sender_id, transport, runtime):
    config = runtime.config
    nodes = transport.nodes
    lookup = Lookup(nodes)
    store = Store(Replication(transport, config.bbs_nodes), runtime.database)
    return Deps(
        roster=nodes,
        store=store,
        lookup=lookup,
        node_id=lookup.id_from_num(sender_id),
        allowed_nodes=config.allowed_nodes,
        js8=runtime.js8_database,
        menus=config.menus,
        fortunes=config.fortunes,
    )


def process_message(sender_id, message, transport, runtime, is_sync_message=False):
    if is_sync_message:
        # A record from a peer: store it, then let Replication decide whether
        # the mesh needs to hear about it. It is never echoed back to peers.
        event = replication.decode(message)
        if event is None:
            logging.error(f"Unrecognized sync message: {message!r}")
            return
        peers = runtime.config.bbs_nodes
        Store(Replication(transport, peers), runtime.database).accept(event)
        Replication(transport, peers).publish(event, Origin.SYNCED)
        return

    # A conversation: the Session advances it and says what to send.
    deps = _build_deps(sender_id, transport, runtime)
    for destination, text in runtime.session.advance(sender_id, message, deps):
        transport.send(text, destination)


def check_timeouts(transport, runtime):
    """The idle-loop counterpart to process_message: no inbound packet, so
    Deps are built per node on demand instead of from one already in hand."""
    def deps_factory(sender_id):
        return _build_deps(sender_id, transport, runtime)

    for destination, text in runtime.session.check_timeouts(deps_factory):
        transport.send(text, destination)


def on_receive(packet, interface, runtime):
    """The one place that meets the meshtastic interface and wraps it."""
    try:
        if 'decoded' in packet and packet['decoded']['portnum'] == 'TEXT_MESSAGE_APP':
            message_bytes = packet['decoded']['payload']
            message_string = message_bytes.decode('utf-8')
            sender_id = packet['from']
            to_id = packet.get('to')
            sender_node_id = packet['fromId']

            transport = MeshtasticTransport(interface)
            nodes = transport.nodes

            sender_short_name = roster.short_name(nodes, sender_node_id)
            receiver_short_name = roster.short_name(nodes, roster.id_from_num(nodes, to_id)) \
                if to_id else "Group Chat"
            logging.info(f"Received message from user '{sender_short_name}' ({sender_node_id}) to {receiver_short_name}: {message_string}")

            is_sync_message = replication.is_sync_message(message_string)

            if sender_node_id in runtime.config.bbs_nodes:
                if is_sync_message:
                    process_message(sender_id, message_string, transport, runtime, is_sync_message=True)
                else:
                    logging.info("Ignoring non-sync message from known BBS node")
            elif to_id is not None and to_id != 0 and to_id != 255 and to_id == transport.my_num:
                process_message(sender_id, message_string, transport, runtime, is_sync_message=False)
            else:
                logging.info("Ignoring message sent to group chat or from unknown node")
    except KeyError as e:
        logging.error(f"Error processing packet: {e}")
