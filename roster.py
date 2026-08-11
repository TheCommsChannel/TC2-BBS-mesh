"""The node roster: who is on the mesh, by id, number, and short name.

Pure reads over the node map meshtastic maintains. Nothing here knows about
the radio — hand it the dict and it answers questions about it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Node:
    """A node as the BBS refers to it.

    `id` is the mesh node id (``!433a1b2c``), which is what mail is addressed
    to and stored against. The roster's own dict is keyed by it.
    """

    id: str
    short_name: str
    long_name: str


def id_from_num(nodes, num):
    """The node id for a mesh number, or None if the node is unknown."""
    for node_id, node in nodes.items():
        if node['num'] == num:
            return node_id
    return None


def short_name(nodes, node_id):
    """The short name, or None when the node is unknown or unnamed.

    One failure mode: callers that write this down as authorship refuse the
    write rather than storing a null author.
    """
    node = nodes.get(node_id)
    if node:
        return node['user'].get('shortName')
    return None


def long_name(nodes, node_id):
    """The display name, falling back to 'Node <id>' for a stranger."""
    node = nodes.get(node_id)
    if node:
        return node['user']['longName']
    return f"Node {node_id}"


def find_by_short_name(nodes, name):
    """Every node answering to a short name. Short names are not unique."""
    name = name.lower()
    return [Node(id=node_id,
                 short_name=node['user']['shortName'],
                 long_name=node['user']['longName'])
            for node_id, node in nodes.items()
            if node['user']['shortName'].lower() == name]
