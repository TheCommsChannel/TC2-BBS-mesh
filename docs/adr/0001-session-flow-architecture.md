# Conversations are pure Flows behind a Session seam

The BBS conversation logic was a tangle of `handle_*_steps` functions that
branched on a step number, sent replies inline through the meshtastic
interface, and mutated a global state dict — untestable without faking the
whole radio. We are moving each conversation topic into a pure **Flow**
(`flows/`): `advance(message, state, deps) -> FlowResult` computes the replies
and the next state and returns them, never sending or touching the radio. A
**Session** (`session.py`) dispatches to the Flow that owns the current topic,
and the router at the seam does the sending. Collaborators a Flow needs
(persistence, node lookup) are injected via `Deps` — the seams where
candidates 01 (transport) and 02 (persistence/sync split) will later land.

We chose this for testability and locality: a Flow is exercised through its
interface with no interface or database, and a topic's steps live in one
module instead of being smeared across the router and the handler bodies.

The migration is deliberately incremental. Migrated topics (Stats, Bulletins,
Mail) are owned end-to-end by the Session seam; topics not yet moved (Channel
Directory, JS8Call, menu navigation) fall through to the legacy
`handle_*_steps` path unchanged. This is why two dispatch styles coexist in
`message_processing.py` — it is a transitional state, not a design in tension.
Do not "finish" one style prematurely or pass the interface into a Flow to
make a migration quicker; that reintroduces the coupling this removes.
