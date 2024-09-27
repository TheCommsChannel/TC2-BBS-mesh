import logging

from meshtastic import BROADCAST_NUM

from command_handlers import (
    handle_mail_command, handle_bulletin_command, handle_help_command, handle_stats_command, handle_fortune_command,
    handle_bb_steps, handle_mail_steps, handle_stats_steps, handle_wall_of_shame_command,
    handle_channel_directory_command, handle_channel_directory_steps, handle_send_mail_command,
    handle_read_mail_command, handle_check_mail_command, handle_delete_mail_confirmation, handle_post_bulletin_command,
    handle_check_bulletin_command, handle_read_bulletin_command, handle_read_channel_command,
    handle_post_channel_command, handle_list_channels_command, handle_quick_help_command
)
from db_operations import add_bulletin, add_mail, delete_bulletin, delete_mail, get_db_connection, add_channel
from js8call_integration import handle_js8call_command, handle_js8call_steps, handle_group_message_selection
from utils import get_user_state, get_node_short_name, get_node_id_from_num, send_message

main_menu_handlers = {
    "q": handle_quick_help_command,
    "b": lambda sender_id, interface: handle_help_command(sender_id, interface, 'bbs'),
    "u": lambda sender_id, interface: handle_help_command(sender_id, interface, 'utilities'),
    "x": handle_help_command
}

bbs_menu_handlers = {
    "m": handle_mail_command,
    "b": handle_bulletin_command,
    "c": handle_channel_directory_command,
    "j": handle_js8call_command,
    "x": handle_help_command
}


utilities_menu_handlers = {
    "s": handle_stats_command,
    "f": handle_fortune_command,
    "w": handle_wall_of_shame_command,
    "x": handle_help_command
}


bulletin_menu_handlers = {
    "g": lambda sender_id, interface: handle_bb_steps(sender_id, '0', 1, {'board': 'General'}, interface, None),
    "i": lambda sender_id, interface: handle_bb_steps(sender_id, '1', 1, {'board': 'Info'}, interface, None),
    "n": lambda sender_id, interface: handle_bb_steps(sender_id, '2', 1, {'board': 'News'}, interface, None),
    "u": lambda sender_id, interface: handle_bb_steps(sender_id, '3', 1, {'board': 'Urgent'}, interface, None),
    "x": handle_help_command
}


board_action_handlers = {
    "r": lambda sender_id, interface, state: handle_bb_steps(sender_id, 'r', 2, state, interface, None),
    "p": lambda sender_id, interface, state: handle_bb_steps(sender_id, 'p', 2, state, interface, None),
    "x": handle_help_command
}

def process_message(sender_id, message, interface, is_sync_message=False):
    state = get_user_state(sender_id)
    message_lower = message.lower().strip()
    message_strip = message.strip()

    bbs_nodes = interface.bbs_nodes

    # Handle repeated characters for single character commands using a prefix
    if len(message_lower) == 2 and message_lower[1] == 'x':
        message_lower = message_lower[0]

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
            recipient_id = get_recipient_id_by_mail(unique_id)
            delete_mail(unique_id, recipient_id, [], interface)
        elif message.startswith("CHANNEL|"):
            parts = message.split("|")
            channel_name, channel_url = parts[1], parts[2]
            add_channel(channel_name, channel_url)
    else:
        if message_lower.startswith("sm,,"):
            handle_send_mail_command(sender_id, message_strip, interface, bbs_nodes)
        elif message_lower.startswith("cm"):
            handle_check_mail_command(sender_id, interface)
        elif message_lower.startswith("pb,,"):
            handle_post_bulletin_command(sender_id, message_strip, interface, bbs_nodes)
        elif message_lower.startswith("cb,,"):
            handle_check_bulletin_command(sender_id, message_strip, interface)
        elif message_lower.startswith("chp,,"):
            handle_post_channel_command(sender_id, message_strip, interface)
        elif message_lower.startswith("chl"):
            handle_list_channels_command(sender_id, interface)
        else:
            if state and state['command'] == 'MENU':
                menu_name = state['menu']
                if menu_name == 'bbs':
                    handlers = bbs_menu_handlers
                elif menu_name == 'utilities':
                    handlers = utilities_menu_handlers
                else:
                    handlers = main_menu_handlers
            elif state and state['command'] == 'BULLETIN_MENU':
                handlers = bulletin_menu_handlers
            elif state and state['command'] == 'BULLETIN_ACTION':
                handlers = board_action_handlers
            elif state and state['command'] == 'JS8CALL_MENU':
                handle_js8call_steps(sender_id, message, state['step'], interface, state)
                return
            elif state and state['command'] == 'GROUP_MESSAGES':
                handle_group_message_selection(sender_id, message, state['step'], state, interface)
                return
            else:
                handlers = main_menu_handlers

            if message_lower == 'x':
                # Reset to main menu state
                handle_help_command(sender_id, interface)
                return

            if message_lower in handlers:
                if state and state['command'] in ['BULLETIN_ACTION', 'BULLETIN_READ', 'BULLETIN_POST', 'BULLETIN_POST_CONTENT']:
                    handlers[message_lower](sender_id, interface, state)
                else:
                    handlers[message_lower](sender_id, interface)
            elif state:
                command = state['command']
                step = state['step']

                if command == 'MAIL':
                    handle_mail_steps(sender_id, message, step, state, interface, bbs_nodes)
                elif command == 'BULLETIN':
                    handle_bb_steps(sender_id, message, step, state, interface, bbs_nodes)
                elif command == 'STATS':
                    handle_stats_steps(sender_id, message, step, interface)
                elif command == 'CHANNEL_DIRECTORY':
                    handle_channel_directory_steps(sender_id, message, step, state, interface)
                elif command == 'CHECK_MAIL':
                    if step == 1:
                        handle_read_mail_command(sender_id, message, state, interface)
                    elif step == 2:
                        handle_delete_mail_confirmation(sender_id, message, state, interface, bbs_nodes)
                elif command == 'CHECK_BULLETIN':
                    if step == 1:
                        handle_read_bulletin_command(sender_id, message, state, interface)
                elif command == 'CHECK_CHANNEL':
                    if step == 1:
                        handle_read_channel_command(sender_id, message, state, interface)
                elif command == 'LIST_CHANNELS':
                    if step == 1:
                        handle_read_channel_command(sender_id, message, state, interface)
                elif command == 'BULLETIN_POST':
                    handle_bb_steps(sender_id, message, 4, state, interface, bbs_nodes)
                elif command == 'BULLETIN_POST_CONTENT':
                    handle_bb_steps(sender_id, message, 5, state, interface, bbs_nodes)
                elif command == 'BULLETIN_READ':
                    handle_bb_steps(sender_id, message, 3, state, interface, bbs_nodes)
                elif command == 'JS8CALL_MENU':
                    handle_js8call_steps(sender_id, message, step, interface, state)
                elif command == 'GROUP_MESSAGES':
                    handle_group_message_selection(sender_id, message, step, state, interface)
                else:
                    handle_help_command(sender_id, interface)
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
            logging.info(f"Received message from user '{sender_short_name}' ({sender_node_id}) to {receiver_short_name}: {message_string}")

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
