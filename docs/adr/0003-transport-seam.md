# The radio sits behind a Transport seam

The meshtastic interface was threaded through nearly every function as a
parameter. It was not travelling because callers needed to transmit — `server.py`
assigned `interface.bbs_nodes` and `interface.allowed_nodes`, so the object was
also the config bag. Nothing could be tested without a fake that answered
`sendText`, `nodes`, `myInfo`, and two attributes meshtastic has never heard of.

We split it three ways. `transport.py` owns sending: `send(text, destination)`,
with the 200-character chunking, the two-second pacing, and the logging behind
it. `roster.py` answers questions about the node map as pure functions over a
dict. `settings` owns `bbs_nodes` and `allowed_nodes`, which are configuration.
`utils.py` keeps only the conversation state.

`MeshtasticTransport` and the tests' `FakeTransport` are two real adapters, so
the seam earns itself rather than being hypothetical. `FakeTransport` records
instead of transmitting and does not sleep, which is why the suite no longer
patches the clock.

`on_receive(packet, interface)` is the one function that still meets the
interface, because `pubsub` chooses that signature for us. It wraps the
interface in a `MeshtasticTransport` and passes that inward. The wrapper is
constructed per message rather than held in a module global: a two-field object
is cheaper than the coupling, and it leaves `process_message` able to take a
`FakeTransport` in tests.

Do not reach for the interface from anywhere else, and do not hang state on it.
That is the habit this removes.
