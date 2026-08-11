#!/usr/bin/env python3

"""Database Administrator — a console for inspecting and pruning the BBS store.

It owns the console and nothing else. Every read and write goes through a
`Database`, which is the one place that knows the schema.

Deletions here are **local only**. The server replicates a mail deletion to its
peer BBS nodes when a user deletes it through the BBS; this tool has no radio,
so a record deleted here stays on every peer that has a copy.

It opens its own Database. Run it while the server is stopped.
"""

import os

from database import Database

CANCEL = 'X'


# --- selection logic (pure) ------------------------------------------------

def parse_selection(text):
    """Split a comma-separated reply into ids, or None if the user cancelled."""
    entries = [entry.strip() for entry in text.split(',') if entry.strip()]
    if any(entry.upper() == CANCEL for entry in entries):
        return None
    return entries


def unique_ids_for(rows, ids):
    """Map the ids shown in a listing onto the unique_ids deletions use.

    Rows are `(id, ..., unique_id)`. Returns the unique_ids found and the ids
    that matched nothing, so the caller can say which ones it ignored.
    """
    by_id = {str(row[0]): row[-1] for row in rows}
    found, unknown = [], []
    for wanted in ids:
        if wanted in by_id:
            found.append(by_id[wanted])
        else:
            unknown.append(wanted)
    return found, unknown


def row_ids_for(rows, ids):
    """Same, for tables whose rows have no unique_id (channels)."""
    known = {str(row[0]) for row in rows}
    found = [wanted for wanted in ids if wanted in known]
    unknown = [wanted for wanted in ids if wanted not in known]
    return found, unknown


# --- listings --------------------------------------------------------------

def list_bulletins(db):
    bulletins = db.all_bulletins()
    if bulletins:
        print_bold("Bulletins:")
        for bulletin in bulletins:
            print_bold(f"(ID: {bulletin[0]}, Board: {bulletin[1]}, "
                       f"Poster: {bulletin[2]}, Subject: {bulletin[4]})")
    else:
        print_bold("No bulletins found.")
    print_separator()
    return bulletins


def list_mail(db):
    mail = db.all_mail()
    if mail:
        print_bold("Mail:")
        for row in mail:
            print_bold(f"(ID: {row[0]}, Sender: {row[2]}, "
                       f"Recipient: {row[3]}, Subject: {row[5]})")
    else:
        print_bold("No mail found.")
    print_separator()
    return mail


def list_channels(db):
    channels = db.all_channels()
    if channels:
        print_bold("Channels:")
        for channel in channels:
            print_bold(f"(ID: {channel[0]}, Name: {channel[1]}, URL: {channel[2]})")
    else:
        print_bold("No channels found.")
    print_separator()
    return channels


# --- deletions -------------------------------------------------------------

def _ask(prompt):
    return parse_selection(input_bold(prompt))


def _report(deleted, unknown, noun):
    if unknown:
        print_bold(f"No {noun} with ID(s) {', '.join(unknown)} - ignored.")
    if deleted:
        print_bold(f"Deleted {deleted} {noun}(s). Peer BBS nodes keep their copy.")
    print_separator()


def delete_bulletins(db):
    bulletins = list_bulletins(db)
    if not bulletins:
        return
    ids = _ask("Enter the bulletin ID(s) to delete (comma-separated) or 'X' to cancel: ")
    if ids is None:
        print_bold("Deletion cancelled.")
        print_separator()
        return
    unique_ids, unknown = unique_ids_for(bulletins, ids)
    deleted = sum(1 for unique_id in unique_ids if db.delete_bulletin(unique_id))
    _report(deleted, unknown, "bulletin")


def delete_mail(db):
    mail = list_mail(db)
    if not mail:
        return
    ids = _ask("Enter the mail ID(s) to delete (comma-separated) or 'X' to cancel: ")
    if ids is None:
        print_bold("Deletion cancelled.")
        print_separator()
        return
    unique_ids, unknown = unique_ids_for(mail, ids)
    deleted = sum(1 for unique_id in unique_ids if db.delete_mail(unique_id))
    _report(deleted, unknown, "mail")


def delete_channels(db):
    channels = list_channels(db)
    if not channels:
        return
    ids = _ask("Enter the channel ID(s) to delete (comma-separated) or 'X' to cancel: ")
    if ids is None:
        print_bold("Deletion cancelled.")
        print_separator()
        return
    row_ids, unknown = row_ids_for(channels, ids)
    deleted = sum(1 for row_id in row_ids if db.delete_channel(int(row_id)))
    _report(deleted, unknown, "channel")


# --- console ---------------------------------------------------------------

def display_menu():
    print("Menu:")
    print("1. List Bulletins")
    print("2. List Mail")
    print("3. List Channels")
    print("4. Delete Bulletins")
    print("5. Delete Mail")
    print("6. Delete Channels")
    print("7. Exit")


def display_banner():
    banner = """
████████╗ ██████╗██████╗       ██████╗ ██████╗ ███████╗
╚══██╔══╝██╔════╝╚════██╗      ██╔══██╗██╔══██╗██╔════╝
   ██║   ██║      █████╔╝█████╗██████╔╝██████╔╝███████╗
   ██║   ██║     ██╔═══╝ ╚════╝██╔══██╗██╔══██╗╚════██║
   ██║   ╚██████╗███████╗      ██████╔╝██████╔╝███████║
   ╚═╝    ╚═════╝╚══════╝      ╚═════╝ ╚═════╝ ╚══════╝
Database Administrator
"""
    print_bold(banner)
    print_separator()


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def input_bold(prompt):
    print("\033[1m")  # ANSI escape code for bold text
    response = input(prompt)
    print("\033[0m")  # ANSI escape code to reset text
    return response


def print_bold(message):
    print("\033[1m" + message + "\033[0m")  # Bold text


def print_separator():
    print_bold("========================")


_ACTIONS = {
    '1': list_bulletins,
    '2': list_mail,
    '3': list_channels,
    '4': delete_bulletins,
    '5': delete_mail,
    '6': delete_channels,
}


def main(db=None):
    db = db if db is not None else Database()
    display_banner()
    db.initialize_schema()
    while True:
        display_menu()
        choice = input_bold("Enter your choice: ")
        clear_screen()
        if choice == '7':
            break
        action = _ACTIONS.get(choice)
        if action is None:
            print_bold("Invalid choice. Please try again.")
            print_separator()
            continue
        action(db)


if __name__ == "__main__":
    main()
