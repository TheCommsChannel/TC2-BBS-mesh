# Replication owns sync, broadcast, and the wire format

Persisting a Bulletin or Mail also transmitted it: `add_bulletin` wrote to
SQLite, relayed to peer BBS Nodes, and broadcast Urgent posts to the mesh, and
callers suppressed the relay by passing `bbs_nodes=[]` as a magic flag. The
broadcast decision existed in two places — inside `add_bulletin` and again in
the sync-receive branch — so an Urgent Bulletin arriving from a peer notified
the mesh twice. The wire format was split three ways: encoding in `utils`,
decoding in `message_processing`, detection in `on_receive`.

We split them. `db_operations` is now pure persistence: writers return a record
(`events.py`) and never touch the radio. `Replication` takes that record plus
its **Origin** (`LOCAL` or `SYNCED`) and decides both outbound questions —
relay to peers only when local, broadcast only when the Board's
`broadcasts_on_post` policy says so. It also owns the wire format in both
directions, so a field can be added in one place and the round-trip is testable.
`adapters.Store` composes the two for callers, whose interface is unchanged.

We chose one Replication rather than separate Sync and Broadcast modules
because the decision is a single function of (record, origin, board policy);
splitting it would need a coordinator that knows both, which is where the
duplication hid in the first place. Records are data (`publish(event, origin)`)
rather than five methods, so the five shallow `send_*_to_bbs_nodes` helpers in
`utils` collapse into one module instead of being renamed.

Two behaviour changes were deliberate, not incidental: a synced Urgent Bulletin
now broadcasts once instead of twice, and `delete_bulletin` matches on
`unique_id` — it previously matched on the local autoincrement `id` while its
only caller passed a `unique_id`, so replicated deletions silently did nothing.
Do not reintroduce a `send_message` call into `db_operations` to make some
future path simpler; that is the coupling this removes.
