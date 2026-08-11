"""Mail conversation: read, send, reply, delete.

Collapses the MAIL step machine (steps 1-8) and the CHECK_MAIL read/confirm
steps into one flow. Pure: mailbox reads and writes go through the injected
store, node resolution through the injected lookup, and the "you have new
mail" nudge to the recipient rides back as a notification for the router to
send — the flow never touches the radio.

The quick-command entry points (SM,, and CM) are still seeded by the legacy
handlers; this flow owns every stepped state they lead into.
"""

from flows.base import stay, end, keep, UNKNOWN_NODE_REPLY

MAIL_MENU = ("✉️Mail Menu✉️\nWhat would you like to do with mail?\n"
             "[R]ead  [S]end E[X]IT")


def _collapse(message):
    message = message.strip()
    if len(message) == 2 and message[1].lower() == "x":
        message = message[0]
    return message


SEND_USAGE = "Send Mail Quick Command format:\nSM,,{short_name},,{subject},,{message}"


class MailFlow:
    TOPICS = ["MAIL", "CHECK_MAIL"]
    QUICK_COMMANDS = {"sm,,": "quick_send", "cm": "quick_check"}

    def entry(self, deps):
        return stay({"command": "MAIL", "step": 1}, replies=[MAIL_MENU])

    # --- quick commands ---------------------------------------------------

    def quick_send(self, message, deps):
        """SM,,{short_name},,{subject},,{message} — send without stepping."""
        parts = message.split(",,", 3)
        if len(parts) != 4:
            return keep(replies=[SEND_USAGE])

        _, short_name, subject, content = parts
        nodes = deps.lookup.node_info(short_name.lower())
        if not nodes:
            return keep(replies=[f"Node with short name '{short_name}' not found."])
        if len(nodes) > 1:
            return keep(
                replies=[f"Multiple nodes with short name '{short_name}' found. "
                         f"Please be more specific."])

        sender_short_name = deps.lookup.short_name(deps.node_id)
        if sender_short_name is None:
            return keep(replies=[UNKNOWN_NODE_REPLY])

        recipient_id = nodes[0].id
        recipient_name = deps.lookup.node_name(recipient_id)
        deps.store.add_mail(deps.node_id, sender_short_name, recipient_id, subject, content)

        notification = (f"You have a new mail message from {sender_short_name}. "
                        f"Check your mailbox by responding to this message with CM.")
        return keep(replies=[f"Mail has been sent to {recipient_name}."],
                    notifications=[(recipient_id, notification)])

    def quick_check(self, message, deps):
        """CM — list the mailbox and wait for a number."""
        state, reply = self._mailbox_listing(deps)
        if state is None:
            return keep(replies=[reply])
        return stay(state, replies=[reply])

    def _mailbox_listing(self, deps):
        """The CHECK_MAIL state to wait in plus the listing reply, or a
        (None, reply) pair when there's nothing to show — shared by the CM
        quick command and by _finish_disposition's loop-back after K/D, so
        both read the same current mailbox instead of the stale one the node
        was disposing of."""
        mail = deps.store.get_mail(deps.node_id)
        if not mail:
            return None, "You have no new messages."

        listing = "📬 You have the following messages:\n"
        for i, msg in enumerate(mail):
            listing += f"{i + 1:02d}. From: {msg[1]}, Subject: {msg[2]}\n"
        listing += "\nPlease reply with the number of the message you want to read."
        return {"command": "CHECK_MAIL", "step": 1, "mail": mail}, listing

    def _finish_disposition(self, confirmation, deps):
        """After Keep or Delete: a person new to the BBS won't know to resend
        CM to see what's left, so loop back into the listing instead of
        dead-ending — from either the menu-driven Read or the CM path."""
        state, reply = self._mailbox_listing(deps)
        if state is None:
            return end(replies=[confirmation, reply])
        return stay(state, replies=[confirmation, reply])

    def advance(self, message, state, deps):
        command = state.get("command")
        step = state.get("step")
        if command == "CHECK_MAIL":
            if step == 1:
                return self._check_read(message, state, deps)
            if step == 2:
                return self._confirm(message, state, deps)
            return stay(state)

        # command == "MAIL"
        handler = {
            1: self._menu, 2: self._open, 3: self._recipient,
            4: self._disposition, 5: self._subject, 6: self._pick_node,
            7: self._compose, 8: self._again,
        }.get(step)
        if handler is None:
            return stay(state)
        return handler(message, state, deps)

    # --- MAIL -------------------------------------------------------------

    def _menu(self, message, state, deps):
        choice = _collapse(message).lower()
        if choice == "r":
            mail = deps.store.get_mail(deps.node_id)
            if not mail:
                return end(replies=["There are no messages in your mailbox.📭"])
            replies = [f"You have {len(mail)} mail messages. "
                       f"Select a message number to read:"]
            replies += [f"-{m[0]}-\nDate: {m[3]}\nFrom: {m[1]}\nSubject: {m[2]}"
                        for m in mail]
            return stay({"command": "MAIL", "step": 2}, replies=replies)
        if choice == "s":
            return stay({"command": "MAIL", "step": 3},
                        replies=["What is the Short Name of the node you want to leave a message for?"])
        # 'x' never reaches here (intercepted upstream); mirror the no-op.
        return stay(state)

    def _open(self, message, state, deps):
        mail_id = int(message)
        content = deps.store.get_mail_content(mail_id, deps.node_id)
        if content is None:
            return end(replies=["Mail not found"])
        sender, date, subject, body, unique_id = content
        return stay(
            {"command": "MAIL", "step": 4, "mail_id": mail_id,
             "unique_id": unique_id, "sender": sender, "subject": subject, "content": body},
            replies=[f"Date: {date}\nFrom: {sender}\nSubject: {subject}\n{body}",
                     "What would you like to do with this message?\n[K]eep  [D]elete  [R]eply"])

    def _recipient(self, message, state, deps):
        short_name = message.lower()
        nodes = deps.lookup.node_info(short_name)
        if not nodes:
            return stay({"command": "MAIL", "step": 1},
                        replies=["I'm unable to find that node in my database.", MAIL_MENU])
        if len(nodes) == 1:
            recipient_id = nodes[0].id
            recipient_name = deps.lookup.node_name(recipient_id)
            return stay({"command": "MAIL", "step": 5, "recipient_id": recipient_id},
                        replies=[f"What is the subject of your message to {recipient_name}?\nKeep it short."])
        replies = ["There are multiple nodes with that short name. "
                   "Which one would you like to leave a message for?"]
        replies += [f"[{i}] {n.long_name}" for i, n in enumerate(nodes)]
        return stay({"command": "MAIL", "step": 6, "nodes": nodes}, replies=replies)

    def _disposition(self, message, state, deps):
        choice = message.lower()
        if choice == "d":
            deps.store.delete_mail(state["unique_id"], deps.node_id)
            return self._finish_disposition("The message has been deleted 🗑️", deps)
        if choice == "r":
            return stay(
                {"command": "MAIL", "step": 7, "reply_to_mail_id": state["mail_id"],
                 "subject": f"Re: {state['subject']}", "content": ""},
                replies=[f"Send your reply to {state['sender']} now, followed by a message with END"])
        return self._finish_disposition("The message has been kept in your inbox.✉️", deps)

    def _subject(self, message, state, deps):
        return stay(
            {"command": "MAIL", "step": 7, "recipient_id": state["recipient_id"],
             "subject": message, "content": ""},
            replies=["Send your message. You can send it in multiple messages if it's too long "
                     "for one.\nSend a single message with END when you're done"])

    def _pick_node(self, message, state, deps):
        selected = state["nodes"][int(message)]
        recipient_id = selected.id
        recipient_name = deps.lookup.node_name(recipient_id)
        return stay({"command": "MAIL", "step": 5, "recipient_id": recipient_id},
                    replies=[f"What is the subject of your message to {recipient_name}?\nKeep it short."])

    def _compose(self, message, state, deps):
        if message.lower() != "end":
            return stay({**state, "content": state["content"] + message + "\n"})

        if "reply_to_mail_id" in state:
            recipient_id = deps.store.sender_id_by_mail_id(state["reply_to_mail_id"])
        else:
            recipient_id = state.get("recipient_id")
        subject = state["subject"]
        content = state["content"]
        sender_short_name = deps.lookup.short_name(deps.node_id)
        if sender_short_name is None:
            return end(replies=[UNKNOWN_NODE_REPLY])

        recipient_name = deps.lookup.node_name(recipient_id)
        deps.store.add_mail(deps.node_id, sender_short_name, recipient_id, subject, content)
        notification = (f"You have a new mail message from {sender_short_name}. "
                        f"Check your mailbox by responding to this message with CM.")
        return stay(
            {"command": "MAIL", "step": 8},
            replies=[f"Mail has been posted to the mailbox of {recipient_name}.\n(╯°□°)╯📨📬"],
            notifications=[(recipient_id, notification)])

    def _again(self, message, state, deps):
        if message.lower() == "y":
            return stay({"command": "MAIL", "step": 1}, replies=[MAIL_MENU])
        return end(replies=["Okay, feel free to send another command."])

    # --- CHECK_MAIL (entered from the CM quick command) -------------------

    def _check_read(self, message, state, deps):
        mail = state.get("mail", [])
        try:
            number = int(message) - 1
        except ValueError:
            return stay(state, replies=["Invalid input. Please enter a valid message number."])
        if number < 0 or number >= len(mail):
            return stay(state, replies=["Invalid message number. Please try again."])
        mail_id = mail[number][0]
        sender, date, subject, body, unique_id = deps.store.get_mail_content(mail_id, deps.node_id)
        return stay(
            {"command": "CHECK_MAIL", "step": 2, "mail_id": mail_id,
             "unique_id": unique_id, "sender": sender, "subject": subject, "content": body},
            replies=[f"Date: {date}\nFrom: {sender}\nSubject: {subject}\n\n{body}",
                     "What would you like to do with this message?\n[K]eep  [D]elete  [R]eply"])

    def _confirm(self, message, state, deps):
        choice = _collapse(message).lower()
        if choice == "d":
            deps.store.delete_mail(state["unique_id"], deps.node_id)
            return self._finish_disposition("The message has been deleted 🗑️", deps)
        if choice == "r":
            return stay(
                {"command": "MAIL", "step": 7, "reply_to_mail_id": state["mail_id"],
                 "subject": f"Re: {state['subject']}", "content": ""},
                replies=[f"Send your reply to {state['sender']} now, followed by a message with END"])
        return self._finish_disposition("The message has been kept in your inbox.✉️", deps)
