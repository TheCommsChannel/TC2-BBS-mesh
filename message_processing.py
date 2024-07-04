import logging

from meshtastic import BROADCAST_NUM

from command_handlers import (
    handle_mail_command, handle_bulletin_command, handle_exit_command,
    handle_help_command, handle_stats_command, handle_fortune_command,
    handle_bb_steps, handle_mail_steps, handle_stats_steps, handle_wall_of_shame_command,
    handle_channel_directory_command, handle_channel_directory_steps
)

from db_operations import add_bulletin, add_mail, delete_bulletin, delete_mail, get_db_connection
from utils import get_user_state, get_node_short_name, get_node_id_from_num, send_message

command_handlers = {
    "m": handle_mail_command,
    "b": handle_bulletin_command,
    "s": handle_stats_command,
    "f": handle_fortune_command,
    "w": handle_wall_of_shame_command,
    "exit": handle_exit_command,
    "h": handle_help_command,
    "c": handle_channel_directory_command
}

def process_message(sender_id, message, interface, is_sync_message=False):
    state = get_user_state(sender_id)
    message_lower = message.lower()
    bbs_nodes = interface.bbs_nodes

    if is_sync_message:
        if message.startswith("BULLETIN|"):
            parts = message.split("|")
            board, sender_short_name, subject, content, unique_id = parts[1], parts[2], parts[3], parts[4], parts[5]
            add_bulletin(board, sender_short_name, subject, content, [], interface, unique_id=unique_id)

            if board.lower() == "urgent":
                notification_message = f"💥NEW URGENT BULLETIN💥\nFrom: {sender_short_name}\nTitle: {subject}"
                send_message(notification_message, BROADCAST_NUM, interface)
        elif message.startswith("MAIL|"):
            parts = message.split("|")
            sender_id, sender_short_name, recipient_id, subject, content, unique_id = parts[1], parts[2], parts[3], parts[4], parts[5], parts[6]
            add_mail(sender_id, sender_short_name, recipient_id, subject, content, [], interface, unique_id=unique_id)
        elif message.startswith("DELETE_BULLETIN|"):
            unique_id = message.split("|")[1]
            delete_bulletin(unique_id, [], interface)
        elif message.startswith("DELETE_MAIL|"):
            unique_id = message.split("|")[1]
            logging.info(f"Processing delete mail with unique_id: {unique_id}")
            recipient_id = get_recipient_id_by_mail(unique_id)  # Fetch the recipient_id using this helper function
            delete_mail(unique_id, recipient_id, [], interface)
    else:
        if message_lower in command_handlers:
            command_handlers[message_lower](sender_id, interface)
        elif state:
            command = state['command']
            step = state['step']

            if command == 'MAIL':
                handle_mail_steps(sender_id, message, step, state, interface, bbs_nodes)
            elif command == 'BULLETIN':
                handle_bb_steps(sender_id, message, step, state, interface, bbs_nodes)
            elif command == 'STATS':
                handle_stats_steps(sender_id, message, step, interface, bbs_nodes)
            elif command == 'CHANNEL_DIRECTORY':
                handle_channel_directory_steps(sender_id, message, step, state, interface)
        else:
            handle_help_command(sender_id, interface)

def on_receive(packet, interface):
    try:
        if 'decoded' in packet and packet['decoded']['portnum'] == 'TEXT_MESSAGE_APP':
            message_bytes = packet['decoded']['payload']
            message_string = message_bytes.decode('utf-8')
            sender_id = packet['from']
            to_id = packet.get('to')
            sender_node_id = packet['fromId']

            sender_short_name = get_node_short_name(sender_node_id, interface)
            receiver_short_name = get_node_short_name(get_node_id_from_num(to_id, interface),
                                                      interface) if to_id else "Group Chat"
            logging.info(f"Received message from user '{sender_short_name}' to {receiver_short_name}: {message_string}")

            bbs_nodes = interface.bbs_nodes
            is_sync_message = any(message_string.startswith(prefix) for prefix in
                                  ["BULLETIN|", "MAIL|", "DELETE_BULLETIN|", "DELETE_MAIL|"])

            if sender_node_id in bbs_nodes:
                if is_sync_message:
                    process_message(sender_id, message_string, interface, is_sync_message=True)
                else:
                    logging.info("Ignoring non-sync message from known BBS node")
            elif to_id is not None and to_id != 0 and to_id != 255 and to_id == interface.myInfo.my_node_num:
                process_message(sender_id, message_string, interface, is_sync_message=False)
            else:
                logging.info("Ignoring message sent to group chat or from unknown node")
    except KeyError as e:
        logging.error(f"Error processing packet: {e}")

def get_recipient_id_by_mail(unique_id):
    # Fix for Mail Delete sync issue
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT recipient FROM mail WHERE unique_id = ?", (unique_id,))
    result = c.fetchone()
    if result:
        return result[0]
    return None
