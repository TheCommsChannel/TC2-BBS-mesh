import logging
import random
import time
import psutil # type: ignore

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

def get_node_name(node_id, interface):
    node_info = interface.nodes.get(node_id)
    if node_info:
        return node_info['user']['longName']
    return f"Node {node_id}"

def handle_mail_command(sender_id, interface):
    response = "✉️ MAIL MENU ✉️\n\n[0]Read\n[1]Send\n[2]Exit"
    send_message(response, sender_id, interface)
    update_user_state(sender_id, {'command': 'MAIL', 'step': 1})

def handle_bulletin_command(sender_id, interface):
    response = "📰 BULLETIN MENU 📰\n\n[0]General\n[1]Info\n[2]News\n[3]Urgent\n[4]Exit"
    send_message(response, sender_id, interface)
    update_user_state(sender_id, {'command': 'BULLETIN', 'step': 1})

def handle_exit_command(sender_id, interface):
    send_message("Type 'HELP' for a list of commands.", sender_id, interface)
    update_user_state(sender_id, None)

def handle_help_command(sender_id, interface, state=None):
    title = "█▓▒░ Yorkshire BBS ░▒▓█\n\n"
    commands = []
    if "mail" not in interface.disabled:
        commands.append("[M]ail")
    if "bulletin" not in interface.disabled:
        commands.append("[B]ulletin")
    if "stats" not in interface.disabled:
        commands.append("[S]tats")
    if "fortune" not in interface.disabled:
        commands.append("[F]ortune")
    if "wos" not in interface.disabled:
        commands.append("[W]all of Shame")
    if "channel" not in interface.disabled:
        commands.append("[C]hannel Directory")
    commands.append("[H]elp")
    
    if state and 'command' in state:
        current_command = state['command']
        if current_command == 'MAIL':
            commands = [
                "[0]Read Mail",
                "[1]Send Mail",
                "[2]Exit"
            ]
        elif current_command == 'BULLETIN':
            commands = [
                "[0]General Board",
                "[1]Info Board",
                "[2]News Board",
                "[3]Urgent Board",
                "[4]Exit"
            ]
        elif current_command == 'STATS':
            commands = [
                "[0]Mesh Stats",
                "[1]Server Stats",
                "[2]Exit"
            ]
    response = title + "\n".join(commands)
    send_message(response, sender_id, interface)

def handle_stats_command(sender_id, interface):
    response = "📈 STATS MENU 📈\n\n[0]Mesh Stats\n[1]Server Stats\n[2]Exit"
    send_message(response, sender_id, interface)
    update_user_state(sender_id, {'command': 'STATS', 'step': 1})

def handle_fortune_command(sender_id, interface):
    try:
        with open('fortunes.txt', 'r') as file:
            fortunes = file.readlines()
        if not fortunes:
            send_message("No fortunes available.", sender_id, interface)
            return
        # trunk-ignore(bandit/B311)
        fortune = random.choice(fortunes).strip()
        decorated_fortune = f"🔮 {fortune} 🔮"
        send_message(decorated_fortune, sender_id, interface)
    except Exception as e:
        send_message(f"Error generating fortune: {e}", sender_id, interface)

def handle_stats_steps(sender_id, message, step, interface, bbs_nodes):
    if step == 1: 
        if message == '2':
            handle_help_command(sender_id, interface)
            return
        if message == '0':
            response = "📈 MESH STATS 📈\n\n[0]Node Numbers\n[1]Hardware\n[2]Roles\n[3]Exit"
            send_message(response, sender_id, interface)
            update_user_state(sender_id, {'command': 'STATS', 'step': 2})
        if message == '1':
            cpu = str(psutil.cpu_freq().current)
            la1 = str(psutil.getloadavg()[0])
            la2 = str(psutil.getloadavg()[1])
            la3 = str(psutil.getloadavg()[2])
            ramu = str(psutil.virtual_memory().percent)
            response = "Version: 0.1.04_Dev\nCPU: " + cpu + "Mhz\nLoad: " + la1 + ", " + la2 + ", " + la3 + "\nRAM: " + ramu + "% Used"
            send_message(response, sender_id, interface)
            handle_stats_command(sender_id, interface)
            return

    elif step == 2:
        if message == '3':
            handle_help_command(sender_id, interface)
            return
        if message == '0':
            response = "📈 NODE NUMBERS 📈\n\n[0]ALL\n[1]Last 24 Hours\n[2]Last 8 Hours\n[3]Last Hour"
            send_message(response, sender_id, interface)
            update_user_state(sender_id, {'command': 'STATS', 'step': 3})
        elif message == '1':
            hw_models = {}
            for node in interface.nodes.values():
                hw_model = node['user'].get('hwModel', 'Unknown')
                hw_models[hw_model] = hw_models.get(hw_model, 0) + 1
            response = "Hardware Models:\n" + "\n".join([f"{model}: {count}" for model, count in hw_models.items()])
            send_message(response, sender_id, interface)
            handle_stats_command(sender_id, interface)
        elif message == '2':
            roles = {}
            for node in interface.nodes.values():
                role = node['user'].get('role', 'Unknown')
                roles[role] = roles.get(role, 0) + 1
            response = "Roles:\n" + "\n".join([f"{role}: {count}" for role, count in roles.items()])
            send_message(response, sender_id, interface)
            handle_stats_command(sender_id, interface)

    elif step == 3:
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
    boards = {0: "General", 1: "Info", 2: "News", 3: "Urgent"}

    if step == 1:
        if message == '4':
            handle_help_command(sender_id, interface)
            return
        board_name = boards.get(int(message))
        if board_name:
            response = f"📰 {board_name} MENU 📰\n\n[0]View Bulletins\n[1]Post Bulletin\n[2]Exit"
            send_message(response, sender_id, interface)
            update_user_state(sender_id, {'command': 'BULLETIN', 'step': 2, 'board': board_name})
        else:
            handle_help_command(sender_id, interface)
            update_user_state(sender_id, None)

    elif step == 2:
        if message == '2':
            # Return to the bulletin menu
            response = "📰 BULLETIN MENU 📰\n\n[0]General\n[1]Info\n[2]News\n[3]Urgent\n[4]Exit"
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
                response = f"📰 {board_name} MENU 📰\n\n[0]View Bulletins\n[1]Post Bulletin\n[2]Exit"
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
        response = f"📰 {board_name} MENU 📰\n\n[0]View Bulletins\n[1]Post Bulletin\n[2]Exit"
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
            add_bulletin(board, sender_short_name, subject, content, bbs_nodes, interface)
            send_message(f"Your bulletin '{subject}' has been posted to {board}.\n(╯°□°)╯📄📌[{board}]", sender_id, interface)
            response = f"📰 {board} MENU 📰\n\n[0]View Bulletins\n[1]Post Bulletin\n[2]Exit"
            send_message(response, sender_id, interface)
            update_user_state(sender_id, {'command': 'BULLETIN', 'step': 2, 'board': board})
        else:
            state['content'] += message + "\n"
            update_user_state(sender_id, state)

def handle_mail_steps(sender_id, message, step, state, interface, bbs_nodes):
    if step == 1:
        if message == '0':
            sender_node_id = get_node_id_from_num(sender_id, interface)
            mail = get_mail(sender_node_id)
            if mail:
                send_message(f"You have {len(mail)} mail messages. Select a message number to read:", sender_id, interface)
                for msg in mail:
                    send_message(f"✉️ {msg[0]} ✉️\nDate: {msg[3]}\nFrom: {msg[1]}\nSubject: {msg[2]}", sender_id, interface)
                update_user_state(sender_id, {'command': 'MAIL', 'step': 2})
            else:
                send_message("There are no messages in your mailbox.\n(`⌒`)", sender_id, interface)
                handle_help_command(sender_id, interface)
                update_user_state(sender_id, None)
        elif message == '1':
            send_message("What is the Short Name of the node you want to send mail to?", sender_id, interface)
            update_user_state(sender_id, {'command': 'MAIL', 'step': 3})
        elif message == '2':
            handle_help_command(sender_id, interface)

    elif step == 2:
        mail_id = int(message)
        try:          
            # ERROR: sender_id is not what is stored in the DB
            sender_node_id = get_node_id_from_num(sender_id, interface)
            sender, date, subject, content, unique_id = get_mail_content(mail_id, sender_node_id)
            send_message(f"Date: {date}\nFrom: {sender}\nSubject: {subject}\n{content}", sender_id, interface)
            send_message("Would you like to delete this message now that you've viewed it? Y/N", sender_id, interface)
            update_user_state(sender_id, {'command': 'MAIL', 'step': 4, 'mail_id': mail_id, 'unique_id': unique_id})
        except TypeError:
            # get_main_content returned None. Node tried to access somebody's else mail message
            logging.info(f"Node {sender_id} tried to access non-existent message")
            send_message("Mail not found", sender_id, interface)
            update_user_state(sender_id, None)

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
            send_message("There are multiple nodes with that short name. Which one would you like to send mail to?", sender_id, interface)
            for i, node in enumerate(nodes):
                send_message(f"[{i}] {node['longName']}", sender_id, interface)
            update_user_state(sender_id, {'command': 'MAIL', 'step': 6, 'nodes': nodes})

    elif step == 4:
        if message.lower() == "y":
            unique_id = state['unique_id']
            sender_node_id = get_node_id_from_num(sender_id, interface)
            delete_mail(unique_id, sender_node_id, bbs_nodes, interface)
            send_message("The message has been deleted 🗑️", sender_id, interface)
        else:
            send_message("The message has been kept in your inbox.✉️\nJust don't let it get as messy as your regular email inbox (ಠ_ಠ)", sender_id, interface)
        update_user_state(sender_id, None)

    elif step == 5:
        subject = message
        send_message("Send your message. You can send it in multiple messages if it's too long.\nSend a message with 'END' when you're done", sender_id, interface)
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
            notification_message = f"You have new mail from {sender_short_name}. Check now by responding to this message with M."
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
    response = "📚 CHANNEL DIRECTORY 📚\n\n[0]View\n[1]Post\n[2]Exit"
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
