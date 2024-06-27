import logging
import os
import random
import time

from config_init import initialize_config
from db_operations import (
    add_bulletin, add_mail, delete_mail,
    get_bulletin_content, get_bulletins,
    get_mail, get_mail_content,
    add_channel, get_channels
)
from utils import (
    get_node_id_from_num, get_node_info,
    get_node_short_name, send_message,
    update_user_state
)

config, interface_type, hostname, port, bbs_nodes = initialize_config()


def get_node_name(node_id, interface):
    node_info = interface.nodes.get(node_id)
    if node_info:
        return node_info['user']['longName']
    return f"Node {node_id}"


def handle_mail_command(sender_id, interface):
    response = "✉️ MAIL MENU ✉️\nWhat would you like to do with mail?\n[0]Read  [1]Send  [2]Exit"
    send_message(response, sender_id, interface)
    update_user_state(sender_id, {'command': 'MAIL', 'step': 1})


def handle_bulletin_command(sender_id, interface):
    response = "📰 BULLETIN MENU 📰\nWhich board would you like to enter?\n[0]General  [1]Info  [2]News  [3]Urgent  [4]Exit"
    send_message(response, sender_id, interface)
    update_user_state(sender_id, {'command': 'BULLETIN', 'step': 1})


def handle_exit_command(sender_id, interface):
    send_message("Type 'HELP' for a list of commands.", sender_id, interface)
    update_user_state(sender_id, None)


def handle_help_command(sender_id, interface, state=None):
    title = "█▓▒░ TC² BBS ░▒▓█\n"
    commands = [
        "[M]ail Menu",
        "[B]ulletin Menu",
        "[S]tats Menu",
        "[F]ortune",
        "[W]all of Shame",
        "[C]hannel Directory",
        "EXIT: Exit current menu",
        "[H]elp"
    ]
    if state and 'command' in state:
        current_command = state['command']
        if current_command == 'MAIL':
            commands = [
                "[0]Read Mail",
                "[1]Send Mail",
                "[2]Exit Mail Menu"
            ]
        elif current_command == 'BULLETIN':
            commands = [
                "[0]General Board",
                "[1]Info Board",
                "[2]News Board",
                "[3]Urgent Board",
                "[4]Exit Bulletin Menu"
            ]
        elif current_command == 'STATS':
            commands = [
                "[0]Total Nodes",
                "[1]Total HW Models",
                "[2]Total Roles",
                "[3]Back"
            ]
    response = title + "Available commands:\n" + "\n".join(commands)
    send_message(response, sender_id, interface)


def handle_stats_command(sender_id, interface):
    response = "What stats would you like to view?\n[0]Node Numbers  [1]Hardware  [2]Roles  [3]Main Menu"
    send_message(response, sender_id, interface)
    update_user_state(sender_id, {'command': 'STATS', 'step': 1})


def handle_fortune_command(sender_id, interface):
    try:
        with open(os.getenv('FORTUNE_FILE','data/fortunes.txt'), 'r') as file:
            fortunes = file.readlines()
        if not fortunes:
            send_message("No fortunes available.", sender_id, interface)
            return
        fortune = random.choice(fortunes).strip()
        decorated_fortune = f"🔮 {fortune} 🔮"
        send_message(decorated_fortune, sender_id, interface)
    except Exception as e:
        send_message(f"Error generating fortune: {e}", sender_id, interface)


def handle_stats_steps(sender_id, message, step, interface, bbs_nodes):
    if step == 1:
        choice = message.upper()
        if choice == '3':
            handle_help_command(sender_id, interface)
            return
        choice = int(choice)
        if choice == 0:
            response = "Select time period for total nodes:\n[0]ALL  [1]Last 24 Hours  [2]Last 8 Hours  [3]Last Hour"
            send_message(response, sender_id, interface)
            update_user_state(sender_id, {'command': 'STATS', 'step': 2})
        elif choice == 1:
            hw_models = {}
            for node in interface.nodes.values():
                hw_model = node['user'].get('hwModel', 'Unknown')
                hw_models[hw_model] = hw_models.get(hw_model, 0) + 1
            response = "Hardware Models:\n" + "\n".join([f"{model}: {count}" for model, count in hw_models.items()])
            send_message(response, sender_id, interface)
            handle_stats_command(sender_id, interface)
        elif choice == 2:
            roles = {}
            for node in interface.nodes.values():
                role = node['user'].get('role', 'Unknown')
                roles[role] = roles.get(role, 0) + 1
            response = "Roles:\n" + "\n".join([f"{role}: {count}" for role, count in roles.items()])
            send_message(response, sender_id, interface)
            handle_stats_command(sender_id, interface)

    elif step == 2:
        choice = int(message)
        current_time = int(time.time())
        if choice == 0:
            total_nodes = len(interface.nodes)
            send_message(f"Total nodes seen: {total_nodes}", sender_id, interface)
        else:
            time_limits = [86400, 28800, 3600]  # Last 24 hours, Last 8 hours, Last hour
            time_limit = current_time - time_limits[choice - 1]
            total_nodes = 0
            for node in interface.nodes.values():
                last_heard = node.get('lastHeard', 0)
                if last_heard is not None and last_heard >= time_limit:
                    total_nodes += 1
                    logging.info(f"Node {node.get('user', {}).get('longName', 'Unknown')} heard at {last_heard}, within limit {time_limit}")
            timeframes = ["24 hours", "8 hours", "hour"]
            send_message(f"Total nodes seen in the last {timeframes[choice - 1]}: {total_nodes}", sender_id, interface)
        handle_stats_steps(sender_id, '0', 1, interface, bbs_nodes)


def handle_bb_steps(sender_id, message, step, state, interface, bbs_nodes):
    boards = {0: "General", 1: "News", 2: "Info", 3: "Urgent"}

    if step == 1:
        if message == '4':
            handle_help_command(sender_id, interface)
            return
        board_name = boards.get(int(message))
        if board_name:
            response = f"What would you like to do in the {board_name} board?\n[0]View Bulletins  [1]Post Bulletin  [2]Exit"
            send_message(response, sender_id, interface)
            update_user_state(sender_id, {'command': 'BULLETIN', 'step': 2, 'board': board_name})
        else:
            handle_help_command(sender_id, interface)
            update_user_state(sender_id, None)

    elif step == 2:
        if message == '2':
            # Return to the bulletin menu
            response = "📰 BULLETIN MENU 📰\nWhich board would you like to enter?\n[0]General  [1]Info  [2]News  [3]Urgent  [4]Exit"
            send_message(response, sender_id, interface)
            update_user_state(sender_id, {'command': 'BULLETIN', 'step': 1})
            return
        if message == '0':
            board_name = state['board']
            bulletins = get_bulletins(board_name)
            if (bulletins):
                send_message(f"Select a bulletin number to view from {board_name}:", sender_id, interface)
                for bulletin in bulletins:
                    send_message(f"[{bulletin[0]}] {bulletin[1]}", sender_id, interface)
                update_user_state(sender_id, {'command': 'BULLETIN', 'step': 3, 'board': board_name})
            else:
                send_message(f"No bulletins in {board_name}.", sender_id, interface)
                # Go back to the board menu
                response = f"What would you like to do in the {board_name} board?\n[0]View Bulletins  [1]Post Bulletin  [2]Exit"
                send_message(response, sender_id, interface)
                update_user_state(sender_id, {'command': 'BULLETIN', 'step': 2, 'board': board_name})

        elif message == '1':
            send_message("What is the subject of your bulletin? Keep it short.", sender_id, interface)
            update_user_state(sender_id, {'command': 'BULLETIN', 'step': 4, 'board': state['board']})

    elif step == 3:
        bulletin_id = int(message)
        sender_short_name, date, subject, content, unique_id = get_bulletin_content(bulletin_id)
        send_message(f"From: {sender_short_name}\nDate: {date}\nSubject: {subject}\n- - - - - - -\n{content}", sender_id, interface)
        board_name = state['board']
        response = f"What would you like to do in the {board_name} board?\n[0]View Bulletins  [1]Post Bulletin  [2]Exit"
        send_message(response, sender_id, interface)
        update_user_state(sender_id, {'command': 'BULLETIN', 'step': 2, 'board': board_name})

    elif step == 4:
        subject = message
        send_message("Send the contents of your bulletin. Send a message with END when finished.", sender_id, interface)
        update_user_state(sender_id, {'command': 'BULLETIN', 'step': 6, 'board': state['board'], 'subject': subject, 'content': ''})

    elif step == 5:
        if message.lower() == "y":
            bulletins = get_bulletins(state['board'])
            send_message(f"Select a bulletin number to view from {state['board']}:", sender_id, interface)
            for bulletin in bulletins:
                send_message(f"[{bulletin[0]}]\nSubject: {bulletin[1]}", sender_id, interface)
            update_user_state(sender_id, {'command': 'BULLETIN', 'step': 3, 'board': state['board']})
        else:
            send_message("Okay, feel free to send another command.", sender_id, interface)
            update_user_state(sender_id, None)

    elif step == 6:
        if message.lower() == "end":
            board = state['board']
            subject = state['subject']
            content = state['content']
            node_id = get_node_id_from_num(sender_id, interface)
            node_info = interface.nodes.get(node_id)
            if node_info is None:
                send_message("Error: Unable to retrieve your node information.", sender_id, interface)
                update_user_state(sender_id, None)
                return
            sender_short_name = node_info['user'].get('shortName', f"Node {sender_id}")
            unique_id = add_bulletin(board, sender_short_name, subject, content, bbs_nodes, interface)
            send_message(f"Your bulletin '{subject}' has been posted to {board}.\n(╯°□°)╯📄📌[{board}]", sender_id, interface)
            response = f"What would you like to do in the {board} board?\n[0]View Bulletins  [1]Post Bulletin  [2]Exit"
            send_message(response, sender_id, interface)
            update_user_state(sender_id, {'command': 'BULLETIN', 'step': 2, 'board': board})
        else:
            state['content'] += message + "\n"
            update_user_state(sender_id, state)


def handle_mail_steps(sender_id, message, step, state, interface, bbs_nodes):
    if step == 1:
        choice = message
        if choice == '0':
            sender_node_id = get_node_id_from_num(sender_id, interface)
            mail = get_mail(sender_node_id)
            if mail:
                send_message(f"You have {len(mail)} mail messages. Select a message number to read:", sender_id, interface)
                for msg in mail:
                    send_message(f"✉️ {msg[0]} ✉️\nDate: {msg[3]}\nFrom: {msg[1]}\nSubject: {msg[2]}", sender_id, interface)
                update_user_state(sender_id, {'command': 'MAIL', 'step': 2})
            else:
                send_message("There are no messages in your mailbox.\n(`⌒`)", sender_id, interface)
                update_user_state(sender_id, None)
        elif choice == '1':
            send_message("What is the Short Name of the node you want to leave a message for?", sender_id, interface)
            update_user_state(sender_id, {'command': 'MAIL', 'step': 3})
        elif choice == '2':
            handle_help_command(sender_id, interface)

    elif step == 2:
        mail_id = int(message)
        sender, date, subject, content, unique_id = get_mail_content(mail_id)
        send_message(f"Date: {date}\nFrom: {sender}\nSubject: {subject}\n{content}", sender_id, interface)
        send_message("Would you like to delete this message now that you've viewed it? Y/N", sender_id, interface)
        update_user_state(sender_id, {'command': 'MAIL', 'step': 4, 'mail_id': mail_id, 'unique_id': unique_id})

    elif step == 3:
        short_name = message
        nodes = get_node_info(interface, short_name)
        if not nodes:
            send_message("I'm unable to find that node in my database.", sender_id, interface)
            handle_mail_command(sender_id, interface)
        elif len(nodes) == 1:
            recipient_id = nodes[0]['num']
            recipient_name = get_node_name(recipient_id, interface)
            send_message(f"What is the subject of your message to {recipient_name}?\nKeep it short.", sender_id, interface)
            update_user_state(sender_id, {'command': 'MAIL', 'step': 5, 'recipient_id': recipient_id})
        else:
            send_message("There are multiple nodes with that short name. Which one would you like to leave a message for?", sender_id, interface)
            for i, node in enumerate(nodes):
                send_message(f"[{i}] {node['longName']}", sender_id, interface)
            update_user_state(sender_id, {'command': 'MAIL', 'step': 6, 'nodes': nodes})

    elif step == 4:
        if message.lower() == "y":
            unique_id = state['unique_id']
            delete_mail(unique_id, bbs_nodes, interface)
            send_message("The message has been deleted 🗑️", sender_id, interface)
        else:
            send_message("The message has been kept in your inbox.✉️\nJust don't let it get as messy as your regular email inbox (ಠ_ಠ)", sender_id, interface)
        update_user_state(sender_id, None)

    elif step == 5:
        subject = message
        send_message("Send your message. You can send it in multiple messages if it's too long for one.\nSend a single message with END when you're done", sender_id, interface)
        update_user_state(sender_id, {'command': 'MAIL', 'step': 7, 'recipient_id': state['recipient_id'], 'subject': subject, 'content': ''})

    elif step == 6:
        selected_node_index = int(message)
        selected_node = state['nodes'][selected_node_index]
        recipient_id = selected_node['num']
        recipient_name = get_node_name(recipient_id, interface)
        send_message(f"What is the subject of your message to {recipient_name}?\nKeep it short.", sender_id, interface)
        update_user_state(sender_id, {'command': 'MAIL', 'step': 5, 'recipient_id': recipient_id})

    elif step == 7:
        if message.lower() == "end":
            recipient_id = state['recipient_id']
            subject = state['subject']
            content = state['content']
            recipient_name = get_node_name(recipient_id, interface)
            sender_short_name = get_node_short_name(get_node_id_from_num(sender_id, interface), interface)
            unique_id = add_mail(get_node_id_from_num(sender_id, interface), sender_short_name, recipient_id, subject, content, bbs_nodes, interface)
            send_message(f"Mail has been posted to the mailbox of {recipient_name}.\n(╯°□°)╯📨📬", sender_id, interface)

            # Send notification to the recipient
            notification_message = f"You have a new mail message from {sender_short_name}. Check your mailbox by responding to this message with M."
            send_message(notification_message, recipient_id, interface)

            update_user_state(sender_id, None)
            update_user_state(sender_id, {'command': 'MAIL', 'step': 8})
        else:
            state['content'] += message + "\n"
            update_user_state(sender_id, state)

    elif step == 8:
        if message.lower() == "y":
            handle_mail_command(sender_id, interface)
        else:
            send_message("Okay, feel free to send another command.", sender_id, interface)
            update_user_state(sender_id, None)


def handle_wall_of_shame_command(sender_id, interface):
    response = "Devices with battery levels below 20%:\n"
    for node_id, node in interface.nodes.items():
        metrics = node.get('deviceMetrics', {})
        battery_level = metrics.get('batteryLevel', 101)
        if battery_level < 20:
            long_name = node['user']['longName']
            response += f"{long_name} - Battery {battery_level}%\n"
    if response == "Devices with battery levels below 20%:\n":
        response = "No devices with battery levels below 20% found."
    send_message(response, sender_id, interface)


def handle_channel_directory_command(sender_id, interface):
    response = "📚 CHANNEL DIRECTORY 📚\nWhat would you like to do in the Channel Directory?\n[0]View  [1]Post  [2]Exit"
    send_message(response, sender_id, interface)
    update_user_state(sender_id, {'command': 'CHANNEL_DIRECTORY', 'step': 1})


def handle_channel_directory_steps(sender_id, message, step, state, interface):
    if step == 1:
        choice = message
        if choice == '2':
            handle_help_command(sender_id, interface)
            return
        elif choice == '0':
            channels = get_channels()
            if channels:
                response = "Select a channel number to view:\n" + "\n".join(
                    [f"[{i}] {channel[0]}" for i, channel in enumerate(channels)])
                send_message(response, sender_id, interface)
                update_user_state(sender_id, {'command': 'CHANNEL_DIRECTORY', 'step': 2})
            else:
                send_message("No channels available in the directory.", sender_id, interface)
                handle_channel_directory_command(sender_id, interface)
        elif choice == '1':
            send_message("Name your channel for the directory:", sender_id, interface)
            update_user_state(sender_id, {'command': 'CHANNEL_DIRECTORY', 'step': 3})

    elif step == 2:
        channel_index = int(message)
        channels = get_channels()
        if 0 <= channel_index < len(channels):
            channel_name, channel_url = channels[channel_index]
            send_message(f"Channel Name: {channel_name}\nChannel URL:\n{channel_url}", sender_id, interface)
        handle_channel_directory_command(sender_id, interface)

    elif step == 3:
        channel_name = message
        send_message("Send a message with your channel URL:", sender_id, interface)
        update_user_state(sender_id, {'command': 'CHANNEL_DIRECTORY', 'step': 4, 'channel_name': channel_name})

    elif step == 4:
        channel_url = message
        channel_name = state['channel_name']
        add_channel(channel_name, channel_url)
        send_message(f"Your channel '{channel_name}' has been added to the directory.", sender_id, interface)
        handle_channel_directory_command(sender_id, interface)
