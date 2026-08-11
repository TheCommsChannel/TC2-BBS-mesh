"""Bulletin conversation: browse boards, read, post.

Collapses six legacy state strings (BULLETIN_MENU / BULLETIN_ACTION /
BULLETIN_READ / BULLETIN_POST / BULLETIN_POST_CONTENT) and the urgent
permission + broadcast branches into one flow. The set of boards and the
urgent policy come from the Board value type; enforcement of the allow-list
stays here, where the acting node is known.

Pure: reads and writes go through the injected store; the confirmation text
is returned, and the post's side effects (peer sync, urgent broadcast) are the
store's Replication, not this flow's.
"""

import board as boards
from flows.base import stay, end, keep, goto, GOTO_MAIN, UNKNOWN_NODE_REPLY

BULLETIN_MENU = ("📰Bulletin Menu📰\nWhich board would you like to enter?\n"
                 "[G]eneral  [I]nfo  [N]ews  [U]rgent")

_LETTER_TO_BOARD = {
    "g": boards.GENERAL,
    "i": boards.INFO,
    "n": boards.NEWS,
    "u": boards.URGENT,
}

POST_USAGE = "Post Bulletin Quick Command format:\nPB,,{board_name},,{subject},,{content}"
CHECK_USAGE = "Check Bulletins Quick Command format:\nCB,,board_name"
NO_PERMISSION = "You don't have permission to post to this board."


def _unknown_board(name):
    known = [b.name for b in boards.BOARDS]
    listed = ", ".join(known[:-1]) + f", or {known[-1]}"
    return f"Unknown board '{name}'. Try {listed}."


def _may_post(board, deps):
    """The Urgent board's allow-list, enforced wherever a post arrives from."""
    if not board.requires_post_permission:
        return True
    return not deps.allowed_nodes or deps.node_id in deps.allowed_nodes


def _board_menu(board_name, deps):
    """The [R]ead/[P]ost prompt for one board, and the state that awaits it —
    where every dead end within a board (empty list, denied post, junk
    input) returns to, instead of bouncing out to the BBS or main menu."""
    bulletins = deps.store.get_bulletins(board_name)
    reply = f"{board_name} has {len(bulletins)} messages.\n[R]ead  [P]ost"
    return {"command": "BULLETIN_ACTION", "step": 2, "board": board_name}, reply


MAX_ITEMS_PER_MESSAGE = 4
MAX_MESSAGE_CHARS = 200


def _pack_lines(header, items, max_items=MAX_ITEMS_PER_MESSAGE, max_chars=MAX_MESSAGE_CHARS):
    """Pack header + items into messages of at most max_items lines each,
    splitting early if a message would otherwise exceed max_chars."""
    messages = []
    current = [header]
    count = 0
    for item in items:
        candidate_text = "\n".join(current + [item])
        if count > 0 and (count >= max_items or len(candidate_text) > max_chars):
            messages.append("\n".join(current))
            current = [item]
            count = 1
        else:
            current.append(item)
            count += 1
    messages.append("\n".join(current))
    return messages


def _bulletin_list(board_name, deps):
    """The numbered listing for one board, or None if it's empty."""
    bulletins = deps.store.get_bulletins(board_name)
    if not bulletins:
        return None, []
    header = f"Select a bulletin number to view from {board_name}:"
    items = [f"[{b[0]}] {b[1]}" for b in bulletins]
    messages = _pack_lines(header, items)
    return {"command": "BULLETIN_READ", "step": 3, "board": board_name}, messages


class BulletinFlow:
    TOPICS = [
        "BULLETIN_MENU",
        "BULLETIN_ACTION",
        "BULLETIN_READ",
        "BULLETIN_POST",
        "BULLETIN_POST_CONTENT",
        "CHECK_BULLETIN",
    ]
    QUICK_COMMANDS = {"pb,,": "quick_post", "cb,,": "quick_check"}

    def entry(self, deps):
        return stay({"command": "BULLETIN_MENU", "step": 1}, replies=[BULLETIN_MENU])

    # --- quick commands ---------------------------------------------------

    def quick_post(self, message, deps):
        """PB,,{board},,{subject},,{content} — post without stepping."""
        parts = message.split(",,", 3)
        if len(parts) != 4:
            return keep(replies=[POST_USAGE])

        _, board_name, subject, content = parts
        board = boards.Board.from_name(board_name)
        if board is None:
            return keep(replies=[_unknown_board(board_name)])
        if not _may_post(board, deps):
            return keep(replies=[NO_PERMISSION])

        sender_short_name = deps.lookup.short_name(deps.node_id)
        if sender_short_name is None:
            return keep(replies=[UNKNOWN_NODE_REPLY])

        deps.store.add_bulletin(board.name, sender_short_name, subject, content)
        return keep(
            replies=[f"Your bulletin '{subject}' has been posted to {board.name}."])

    def quick_check(self, message, deps):
        """CB,,{board} — list a board and wait for a number."""
        parts = message.split(",,", 1)
        if len(parts) != 2 or not parts[1].strip():
            return keep(replies=[CHECK_USAGE])

        board = boards.Board.from_name(parts[1])
        if board is None:
            return keep(replies=[_unknown_board(parts[1].strip())])

        bulletins = deps.store.get_bulletins(board.name)
        if not bulletins:
            return keep(replies=[f"No bulletins available on {board.name} board."])

        header = f"📰 Bulletins on {board.name} board:"
        items = [f"[{i + 1:02d}] Subject: {bulletin[1]}, "
                 f"From: {bulletin[2]}, Date: {bulletin[3]}"
                 for i, bulletin in enumerate(bulletins)]
        items.append("Please reply with the number of the bulletin you want to read.")
        messages = _pack_lines(header, items)
        return stay({"command": "CHECK_BULLETIN", "step": 1,
                     "board_name": board.name, "bulletins": bulletins}, replies=messages)

    def advance(self, message, state, deps):
        command = state.get("command")
        if command == "BULLETIN_MENU":
            return self._select_board(message, deps)
        if command == "BULLETIN_ACTION":
            return self._read_or_post(message, state, deps)
        if command == "BULLETIN_READ":
            return self._read_bulletin(message, state, deps)
        if command == "BULLETIN_POST":
            return self._take_subject(message, state)
        if command == "BULLETIN_POST_CONTENT":
            return self._take_content(message, state, deps)
        if command == "CHECK_BULLETIN":
            return self._read_numbered(message, state, deps)
        return stay(state)

    def _read_numbered(self, message, state, deps):
        """The numbered read the CB,, quick command seeds."""
        bulletins = state.get("bulletins", [])
        try:
            index = int(message) - 1
        except ValueError:
            return stay(state, replies=["Invalid input. Please enter a valid bulletin number."])
        if index < 0 or index >= len(bulletins):
            return stay(state, replies=["Invalid bulletin number. Please try again."])

        sender, date, subject, content, _ = \
            deps.store.get_bulletin_content(bulletins[index][0])
        return end(
            replies=[f"Date: {date}\nFrom: {sender}\nSubject: {subject}\n\n{content}"])

    def _select_board(self, message, deps):
        board = _LETTER_TO_BOARD.get(message.lower().strip())
        if board is None:
            # Legacy dropped unrecognized menu input back to the main menu.
            return goto(GOTO_MAIN)
        state, reply = _board_menu(board.name, deps)
        return stay(state, replies=[reply])

    def _read_or_post(self, message, state, deps):
        board_name = state["board"]
        choice = message.lower().strip()

        if choice == "r":
            list_state, replies = _bulletin_list(board_name, deps)
            if list_state is None:
                board_state, board_reply = _board_menu(board_name, deps)
                return stay(board_state,
                            replies=[f"No bulletins in {board_name}.", board_reply])
            return stay(list_state, replies=replies)

        if choice == "p":
            board = boards.Board.from_name(board_name)
            if board is not None and not _may_post(board, deps):
                board_state, board_reply = _board_menu(board_name, deps)
                return stay(board_state, replies=[NO_PERMISSION, board_reply])
            return stay({"command": "BULLETIN_POST", "step": 4, "board": board_name},
                        replies=["What is the subject of your bulletin? Keep it short."])

        # Junk input re-prompts the same board menu instead of bouncing to main.
        board_state, board_reply = _board_menu(board_name, deps)
        return stay(board_state, replies=["Please enter R or P.", board_reply])

    def _read_bulletin(self, message, state, deps):
        bulletin_id = int(message)
        board_name = state["board"]
        sender_short_name, date, subject, content, _ = \
            deps.store.get_bulletin_content(bulletin_id)
        reply = (f"From: {sender_short_name}\nDate: {date}\nSubject: {subject}\n"
                 f"- - - - - - -\n{content}")
        list_state, list_replies = _bulletin_list(board_name, deps)
        if list_state is None:
            board_state, board_reply = _board_menu(board_name, deps)
            return stay(board_state, replies=[reply, board_reply])
        return stay(list_state, replies=[reply] + list_replies)

    def _take_subject(self, message, state):
        return stay({"command": "BULLETIN_POST_CONTENT", "step": 5,
                     "board": state["board"], "subject": message, "content": ""},
                    replies=["Send the contents of your bulletin. Send a message with END when finished."])

    def _take_content(self, message, state, deps):
        if message.lower() != "end":
            return stay({**state, "content": state["content"] + message + "\n"})

        board = state["board"]
        subject = state["subject"]
        content = state["content"]
        sender_short_name = deps.lookup.short_name(deps.node_id)
        if sender_short_name is None:
            return end(replies=[UNKNOWN_NODE_REPLY])

        deps.store.add_bulletin(board, sender_short_name, subject, content)
        reply = (f"Your bulletin '{subject}' has been posted to {board}.\n"
                 f"(╯°□°)╯📄📌[{board}]")
        return stay({"command": "BULLETIN_MENU", "step": 1}, replies=[reply, BULLETIN_MENU])
