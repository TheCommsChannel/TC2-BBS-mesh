# Bugs found and fixed during the Session/Flow refactor

None of these were hunted. Each surfaced while rewriting the code that
contained it — which is the argument for the refactor, not a bonus from it.

Every entry was reproduced before being fixed, and each has a regression test.
Behaviour changes are called out explicitly: the refactor was otherwise
behaviour-preserving, guarded by the characterization suite in
`tests/test_characterization.py`.

---

## 1. Any node could post to the Urgent board and broadcast to the whole mesh

**Severity:** access control bypass.

`[allow_list] allowed_nodes` in `config.ini` restricts who may post to the
Urgent board — a post there broadcasts a notice to every node on the mesh.
The menu path (`[B]ulletins → [U]rgent → [P]ost`) checked the allow-list.
The `PB,,` quick command never did.

```
PB,,Urgent,,Fake alert,,ignore me
```

from a node absent from `allowed_nodes` posted the bulletin and triggered the
mesh-wide broadcast.

**Cause:** the check lived inline in the menu handler, so the second caller
never inherited it.

**Fix:** both paths now go through one `_may_post()` in `flows/bulletin.py`.

Commit `6257db4`. Tests: `tests/test_bulletin_flow.py::test_quick_post_to_urgent_respects_the_allow_list`,
`tests/test_characterization.py::test_quick_post_bulletin_to_urgent_respects_allow_list`.

---

## 2. A synced Urgent bulletin broadcast to the mesh twice

Receiving an Urgent bulletin from a peer BBS node sent two identical
`💥NEW URGENT BULLETIN💥` notices to the whole mesh.

**Cause:** the broadcast decision existed in two places — inside
`db_operations.add_bulletin` (outside the `if bbs_nodes` guard) and again in
the sync-receive branch of `message_processing`.

**Fix:** persistence no longer transmits. `Replication.publish(event, origin)`
is the single place that decides both sync and broadcast, driven by the
Board's `broadcasts_on_post` policy rather than a `board.lower() == "urgent"`
string test.

**Behaviour change:** one broadcast instead of two.

Commit `4fb33ef`. Test: `tests/test_characterization.py::test_synced_urgent_bulletin_broadcasts_once`.

---

## 3. Replicated bulletin deletions silently did nothing

`delete_bulletin` deleted by the local autoincrement `id`:

```sql
DELETE FROM bulletins WHERE id = ?
```

while its only caller — the `DELETE_BULLETIN|` sync branch — passed a
`unique_id`. The statement matched no rows, every time. Nobody noticed because
nothing in the codebase ever *originates* a bulletin deletion (`db_admin.py`
deletes directly, without syncing), so the broken path was only ever reached
from a peer.

**Fix:** `delete_bulletin(unique_id)` matches on `unique_id`, the identity
peers actually share, and returns `None` when the bulletin is absent.

**Behaviour change:** a replicated deletion now deletes.

Commit `4fb33ef`. Test: `tests/test_characterization.py::test_synced_bulletin_deletion_removes_it`.

---

## 4. The `CHP,,` quick command could never succeed

```python
parts = message.split("|", 3)          # splits on "|"
if len(parts) != 3:
    send_message("Post Channel Quick Command format:\nCHP,,{channel_name},,{channel_url}")
```

The parser split on `|` while its own usage text promised `,,`. Any well-formed
`CHP,,Name,,url` produced a single part, failed the length check, and printed
the usage. Adding a channel by quick command had never worked.

**Fix:** `split(",,", 2)`, matching the documented format.

**Behaviour change:** the command works.

Commit `6257db4`. Tests: `tests/test_channel_flow.py::test_quick_post_adds_channel`,
`tests/test_characterization.py::test_quick_post_channel_actually_works`.

---

## 5 & 6. Every JS8Call message crashed the JS8Call thread

Two independent faults on the same code path:

```python
def insert_message(self, table, sender, recipient, message):
    ...
    self.db_conn.execute(..., (sender, receiver_or_group, message))   # 5: undefined name
```

`receiver_or_group` does not exist; the parameter is `recipient`. The
surrounding `except sqlite3.Error` does not catch `NameError`, so it escaped.

```python
self.insert_urgent('urgent', sender, receiver, msg)                   # 6: no such method
```

`insert_urgent` was never defined — `AttributeError`.

Between them, every `RX.DIRECTED` message the bridge received raised: urgent
messages hit the missing method, group and station messages hit the undefined
name. The exception escaped `process()`, escaped `connect()` (which catches
only `ConnectionRefusedError`), and killed the client. The JS8Call bridge
stored nothing, ever. It went unnoticed because `example_config.ini` ships with
the `[js8call]` section commented out.

**Fix:** writes go through `js8_db.Js8Database.insert(table, sender, counterparty, message)`,
which takes the column from a table allow-list. Both call sites use it.

**Behaviour change:** the bridge stores messages.

Commit `f8b0352`. Tests: `tests/test_js8_db.py` (all), verified end-to-end against
`JS8CallClient.process`.

---

## 7. The JS8Call reader and writer used different databases

`JS8CallClient` wrote to the configured `[js8call] db_file`. The three read
handlers each hardcoded `sqlite3.connect('js8call.db')`. Any custom `db_file`
meant the BBS browsed an empty database while the bridge filled another.

**Fix:** one `settings.js8_database()` shared by both.

Commit `f8b0352`.

---

## 8. Browsing JS8Call before it was configured raised at the user

The read handlers ran `SELECT` against tables that only `JS8CallClient` creates.
With the bridge unconfigured, `sqlite3.connect('js8call.db')` created an empty
file and the `SELECT` raised `sqlite3.OperationalError`, uncaught.

**Fix:** `Js8Database` reads return `[]` when the bridge is unconfigured or the
tables do not exist. An unconfigured bridge is an empty inbox, not an error.

**Behaviour change:** "No group messages available." instead of a crash.

Commit `f8b0352`. Test: `tests/test_characterization.py::test_js8call_reads_answer_gracefully_when_unconfigured`.

---

## 9. `handle_help_command` raised `NameError` for unknown menus

```python
if menu_name:
    if menu_name == 'bbs':          response = build_menu(...)
    elif menu_name == 'utilities':  response = build_menu(...)
    # any other name: `response` is never assigned
send_message(response, ...)
```

Unreachable at the time — the function was only ever called with `'bbs'`,
`'utilities'`, or `None` — but a latent trap for the next caller.

**Fix:** `NavigationFlow.show()` falls back to the main menu for any
unrecognized name.

Commit `ff0354a`. Test: `tests/test_navigation_flow.py::test_unknown_menu_name_falls_back_to_main`.

---

## 10. `CB,,` and `PB,,` did not validate the board

`CB,,Sports` raised `StopIteration` out of a generator expression, was swallowed
by a bare `except Exception`, and answered `"Error processing check bulletin
command."` — a message that described the wrong thing.

`PB,,Sports,,subject,,content` did not validate at all, and inserted a bulletin
onto a board no menu can reach and `Replication` will not broadcast.

**Fix:** both resolve the board through `Board.from_name`, which returns `None`
for an unknown name, and answer
`Unknown board 'Sports'. Try General, Info, News, or Urgent.`

**Behaviour change:** honest error messages; no orphan bulletins.

Commit `6257db4`.

---

## 11. The JS8Call listener blocked the server, then died or spun

`JS8CallClient.connect()` looped on `sock.recv()` and never returned, and
`server.main()` called it inline:

```python
if js8call_client.db_conn:
    js8call_client.connect()      # never returns
try:
    while True:                   # never reached
        time.sleep(1)
except KeyboardInterrupt:         # never installed
    interface.close()
```

With JS8Call enabled the server had no shutdown handler at all. `Ctrl-C` landed
inside `recv()` and unwound past `interface.close()`.

The loop itself handled neither end of the connection:

- **Peer hangs up cleanly** (Linux): `recv()` returns `b''`, and
  `if not content: continue` spins a tight loop, burning a core forever.
- **Peer resets** (Windows): `ConnectionResetError` escapes `connect()`, which
  catches only `ConnectionRefusedError`, and kills the thread — or, run inline,
  the server.

**Fix:** the client owns its lifecycle. `start()` spawns a daemon listener and
returns; `close()` shuts the socket down — which unblocks a listener parked in
`recv()` — and joins it. EOF and `OSError` both end the loop cleanly.
`server.main()` no longer knows a thread exists.

**Behaviour change:** the server starts, serves, and shuts down cleanly with
JS8Call enabled.

Commit `e0968c2`. Tests: `tests/test_js8_client.py::test_close_unblocks_and_joins_the_listener`,
`::test_peer_hangup_stops_the_listener_without_spinning`,
`::test_start_returns_immediately_and_listens`.

---

## 12. JS8Call messages arriving in the same TCP segment were both discarded

```python
content = self.sock.recv(65500).decode('utf-8')
try:
    message = json.loads(content)
except ValueError:
    continue                       # drops everything in this read
```

JS8Call speaks newline-delimited JSON. A single `recv()` can carry two
messages, or half of one. `json.loads` on the raw chunk fails for both cases,
and the `continue` threw the data away without a word. TCP guarantees a byte
stream, not message boundaries — this code assumed one read meant one message.

**Fix:** `decode_messages(buffer)` accumulates bytes, splits on newlines,
parses each line, and returns the incomplete remainder for the next read. An
unparseable line is logged and skipped rather than taking its neighbours with
it.

**Behaviour change:** no silent message loss.

Commit `e0968c2`. Tests: `tests/test_js8_client.py::test_two_messages_in_one_chunk`,
`::test_message_split_across_chunks`, `::test_two_messages_in_one_segment_are_both_stored`.

---

## 13. `db_admin.list_mail()` returned one row instead of the list

```python
mail = c.fetchall()
if mail:
    for mail in mail:            # rebinds the name it is iterating
        print_bold(...)
return mail                      # the last row, not the list
```

The loop variable shadowed the list. `list_bulletins` and `list_channels` used
distinct names and were fine; only mail had it. It never surfaced because the
one caller did `if mail:` and a non-empty tuple is truthy, so the wrong type was
never noticed.

**Fix:** `for row in mail`. The listing functions are now tested for returning
every row.

Commit `6eea6cc`. Test: `tests/test_db_admin.py::test_list_mail_returns_every_row`.

---

## 14. A failed send crashed the handler that was meant to swallow it

```python
except Exception as e:
    logging.info(f"REPLY SEND ERROR {e.message}")
```

`e.message` was removed in Python 3. Any transient send failure — radio busy,
device unplugged, mesh congested — raised `AttributeError` from inside the
`except` clause. It masked the original error and unwound out of
`send_message`, past `process_message`, and into the pubsub callback.

Reproduced by making `sendText` raise `OSError("radio busy")`: the caller sees
`AttributeError: 'OSError' object has no attribute 'message'`.

**Fix:** the send loop now lives in `MeshtasticTransport.send`, logs the actual
error, and carries on to the next chunk.

**Behaviour change:** a dropped chunk is logged rather than crashing the
conversation.

Commit `c82bc49`. Test: `tests/test_transport.py::test_a_failed_send_is_logged_not_raised`.

---

## 15. `--config` did not reach most of the configuration

`server.py --config other.ini` fed the chosen file to `config_init`, which read
the `[interface]`, `[sync]` and `[allow_list]` sections from it. But
`command_handlers` opened `'config.ini'` for the `[menu]` section, and
`js8call_integration` opened `'config.ini'` for `[js8call]`. Both hardcoded the
name.

So running with an alternate config took its radio settings and peer list from
one file and its menus and JS8Call settings from another — silently, whichever
`./config.ini` happened to be lying around.

**Fix:** `settings` owns the config path. `server.main()` sets it once, and
every section is read from the same file.

**Behaviour change:** `--config` means what it says.

Commit `c82bc49`.

---

## 16. A Node the BBS could not name became the author of Bulletins and Mail

Found by the second architecture review, reproduced before it was fixed.

`deps.node_id` is resolved from the meshtastic node roster. A Node the BBS has
not yet seen in its nodedb resolves to `None` — a first contact, or a node
heard over a hop whose nodedb has not propagated. Four places wrote authorship
onto a record, and only one of them checked:

| Path | Derivation | Result for an unknown Node |
| --- | --- | --- |
| Bulletin, menu | `deps.roster.get(...)` then its own fallback | refused |
| Bulletin, `PB,,` | `deps.lookup.short_name(...)` | stored `None` |
| Mail, menu | `deps.lookup.short_name(...)` | stored `None` |
| Mail, `SM,,` | `deps.lookup.short_name(...)` | stored `None` |

The same domain fact — who wrote this — was derived two ways with three
failure modes. `roster.short_name` returned `None` for a missing Node but
raised `KeyError` for a Node present without a short name.

So `PB,,General,,Fake,,body` from an unknown Node answered "posted", stored a
Bulletin with a null author, and Replication encoded it to every peer as

```
BULLETIN|General|None|Fake|body|<uuid>
```

Mail was worse: it stored the Mail, and told the recipient
`You have a new mail message from None.`

**Cause:** authorship had no single derivation. The menu path guarded because
someone once wrote the guard there; the other three never inherited it.

**Fix:** `Lookup` is the only module that answers questions about a Node, and
it has one failure mode — `None` for a Node that is unknown or unnamed. All
four call sites ask it, and all four refuse the write rather than attributing
a record to nobody. `deps.roster` stops being a second door onto the same dict;
it survives only for the reports that iterate every Node (Stats, Wall of Shame).
`Deps.node_num` existed solely to build the discarded fallback, and is gone.

**Behaviour change:** an unidentified Node is refused when it tries to author a
Bulletin or Mail. It can still read the menus, browse boards, and run the
utilities — refusing authorship is not refusing the conversation.

Commit `60a9b66`. Tests: `tests/test_characterization.py::test_quick_post_by_an_unknown_node_is_refused_and_not_replicated`,
`::test_quick_send_mail_by_an_unknown_node_is_refused`,
`::test_an_unknown_node_can_still_read_the_menus`,
`tests/test_bulletin_flow.py::test_both_post_paths_refuse_a_node_without_a_short_name`,
`tests/test_roster.py::test_short_name_of_an_unnamed_node_is_none_not_a_crash`.

---

## Deliberate behaviour changes that were not bugs

- **Adding a Channel now replicates from either entry point.** Previously only
  `CHP,,` synced to peers and the menu did not — an artefact of `add_channel`
  taking the peer list as an optional argument the menu never passed. (Because
  of bug 4, `CHP,,` never ran, so in practice *no* channel ever synced.)
  Commit `14c86fd`.

- **`CHANNEL|` is now recognized as a sync message.** It was already decodable,
  but absent from the prefix list `on_receive` checks, so a peer's channel
  arrived as conversation and was answered with the main menu.
  Commit `14c86fd`.

- **Menu items and fortunes load on first use, not at import.** `command_handlers`
  read `config.ini` at module import, so importing anything required the file to
  exist. The test suite now runs with no `config.ini` present.
  Commit `ff0354a`.

- **The meshtastic interface no longer travels through the codebase.** It was
  passed to nearly every function, and `server.py` stapled `bbs_nodes` and
  `allowed_nodes` onto it — config riding on a radio object. `Transport` now
  owns sending, chunking and pacing; `roster` answers questions about the node
  map; `settings` owns the two config lists. Only `on_receive` meets the
  interface, and only `Transport` calls `sendText`.
  Commit `c82bc49`.

---

## Known, not fixed

- **Bulletin deletions never replicate.** `db_admin.py` is the only place that
  deletes a bulletin, and it has no radio — opening the serial port while the
  server holds it would conflict. So `DELETE_BULLETIN|` has a receiver and no
  sender. Deleting a bulletin leaves every peer holding its copy. (Mail is
  different: deleting mail through the BBS does replicate.)

- **The JS8Call bridge does not reconnect.** If the JS8Call instance restarts,
  the listener exits cleanly and stays down until the server is restarted.
  Adding retry with backoff is a feature, not a fix, so it was left out.
