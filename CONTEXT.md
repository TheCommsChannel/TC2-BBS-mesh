# TC²-BBS

A bulletin-board system that runs over a Meshtastic mesh. Nodes hold private
conversations with the BBS by exchanging text messages; the BBS offers mail,
public bulletin boards, and a shared channel directory, and replicates them
with peer BBS servers. An optional JS8Call bridge pulls in messages heard over
HF radio.

## Language

### Participants

**Node**:
A Meshtastic device (and the person using it) that talks to the BBS. Identified
by a node id and addressed by its Short Name.
_Avoid_: user, device, station (Station is a JS8Call concept — see below).

**Short Name**:
A node's brief handle, used to address Mail. Not unique — several nodes may
share one, which the conversation resolves by asking the sender to choose.
_Avoid_: callsign (that is JS8Call's term).

**BBS Node**:
A peer BBS server that this server syncs Bulletins and Mail with. Listed in
config; messages from a BBS Node are treated as Sync, not conversation.
_Avoid_: sync node, peer server.

### Content

**Bulletin**:
A public message posted to a Board and visible to every Node.

**Board**:
A named category of Bulletins with a posting policy. The set is fixed —
General, Info, News, Urgent.
_Avoid_: forum, category, channel (Channel is a different thing here).

**Urgent Board**:
The Board whose policy gates posting behind the Allow List and broadcasts every
new post to the whole mesh.

**Broadcast**:
A one-way notify sent to the whole mesh at once, used to announce a new Urgent
Bulletin. Distinct from Sync: it reaches every Node, not just BBS Nodes, and
carries a nudge to read rather than the content to replicate.

**Mail**:
A private message from one Node to another, held in the recipient's mailbox
until read or deleted.
_Avoid_: DM, message (too general).

**Channel Directory**:
A shared list of Meshtastic Channels — each a name plus a channel URL or PSK —
that Nodes can browse and contribute to.

**Channel**:
An entry in the Channel Directory: a joinable Meshtastic channel, not a
conversation topic.

### Interaction

**Session**:
One Node's ongoing conversation with the BBS — the current topic, the step
within it, and any half-entered content. Each Node has at most one.
_Avoid_: connection, state (too general).

**Flow**:
One topic of conversation, start to finish — Mail, Bulletins, Stats, and so on.
A Session is always inside exactly one Flow (menu navigation included).
_Avoid_: handler, wizard, dialog.

**Quick Command**:
A shorthand that performs a whole action in one message instead of stepping
through a Flow — e.g. `SM,,` to send mail, `CB,,` to check bulletins.
_Avoid_: shortcut, hotkey.

**Allow List**:
The set of Nodes permitted to post to the Urgent Board. Empty means anyone may.
_Avoid_: whitelist, permissions.

**Sync**:
Replication of a Bulletin, Mail, or a deletion from this server to its BBS
Nodes, carried as specially-prefixed mesh messages. Distinct from conversation.
_Avoid_: broadcast (that is the mesh-wide notify for Urgent), federation.

**Origin**:
Where a record came from — created by a local Node, or arrived from a peer BBS
Node. A record that arrived from a peer is never synced back out.
_Avoid_: source, direction.

### JS8Call bridge

**Station**:
A callsign heard over JS8Call. A radio identity, distinct from a mesh Node.
_Avoid_: node, user.

**Group**:
A JS8Call group address that Stations send to. An Urgent Group additionally
triggers a mesh-wide notify when a message arrives for it.
