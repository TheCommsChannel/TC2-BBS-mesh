---
status: accepted — not yet fully applied
---

# Application state is passed, not global

The live state of a running BBS — where each Node stands in its conversation,
the database connection, the parsed configuration — is owned by an object and
handed to whoever needs it. No module holds mutable state on the conversation
path.

We are recording this as a decision because the codebase does not yet obey it.
Three modules still keep their state in module-level globals:

| Module | The global | Now |
| --- | --- | --- |
| ~~`utils`~~ | ~~`user_states = {}`~~ | done — the `Session` object owns it |
| ~~`db_operations`~~ | ~~`thread_local.connection`~~ | done — now a `Database` object |
| ~~`settings`~~ | ~~seven cached values behind `configure()`/`reset()`~~ | done — now a `Config` value |

**Done.** All three are gone.

The database global went first: `db_operations` became a `Database` object,
constructed in `server.main()` and handed to `on_receive` through the closure
`pubsub` already gave us, and to `db_admin.main(db)` on its own.

The settings cache went next. `settings.load()` reads the config file once and
returns a frozen `Config`; there is no `configure()`, no `reset()`, no cache.

The conversation state went last. `Session` now owns the per-node state and the
whole routing loop — `session.advance(node, message, deps)` returns what to
send. The `Session` is constructed once in `server.main()` and carried on the
`Runtime`, so the router reaches for no module; `utils.py`, which had shrunk to
that one dict, is deleted. Tests build a `Session` (inside a `Runtime`) rather
than clearing a global.

**Consequence realised.** With no module-level mutable state left on the
conversation path, the suite no longer needs process isolation. `run_tests.py`
runs every file in one interpreter; the whole suite passing there is the proof
that nothing leaks between files.

The counter-example is already in the repo. `Js8Database` owns its path and its
connection and is constructed with `":memory:"` in tests. Nothing is reassigned,
nothing leaks between tests, and the seam is an argument rather than a
monkeypatch. `db_operations` is the same kind of thing wearing a different shape.

## Why it matters

A module-level global is a seam you cannot see in any interface. Tests reach
past `Store`, past `Session`, past every seam this project built, and rebind a
name. The interface stops being the test surface.

It also costs us process isolation. `run_tests.py` runs each file in its own
interpreter precisely so that one file's substitute cannot leak into the next.
That is a real constraint bought to hide a design problem, and it will be paid
again by anyone who later wants a shared fixture, a coverage run, or pytest.

## Consequences

- `Session` should hold the Session — the concept `CONTEXT.md` defines as a
  Node's current topic, step, and half-entered content. Today it is a dict in
  `utils`, and the router reaches into it.
- The BBS store should be a `Database` object, symmetrical with `Js8Database`.
- Configuration should be a value read once and passed down, not a lazily
  cached module.
- Once all three are done, the suite can share one interpreter and
  `run_tests.py` can stop spawning a process per file.

## What this does not mean

Immutable module-level constants are fine — `board.BOARDS`, the wire-format
prefixes, menu labels. The rule is about *mutable* state that a running BBS
changes, and that a test wants to replace.

Nor does it mean threading every dependency through every call. `Deps` already
exists as the channel a Flow receives its collaborators through. The point is
that the collaborators are handed over, not reached for.
